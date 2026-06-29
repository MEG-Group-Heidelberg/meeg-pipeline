from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

ConditionDefinition = str | list[int] | tuple[int, ...] | set[int]


def normalize_condition_label(value: object) -> str:
    """Normalize condition/event labels for tolerant string matching."""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def condition_definitions_from_config(config: Any) -> dict[str, ConditionDefinition]:
    """Return named project-specific condition definitions from PipelineConfig."""
    conditions = getattr(config, "conditions", None)
    definitions = getattr(conditions, "definitions", {}) if conditions is not None else {}
    return dict(definitions or {})


def resolve_condition_definition(
    condition: str,
    definitions: Mapping[str, ConditionDefinition] | None = None,
) -> ConditionDefinition | None:
    """Return the definition for a named condition, if one is configured.

    Exact names are preferred. If that fails, a normalized match is attempted so
    labels such as ``1st_non_diatonic`` and ``1stNonDiatonic`` can refer to the
    same configured condition.
    """
    if not definitions:
        return None

    if condition in definitions:
        return definitions[condition]

    target = normalize_condition_label(condition)
    for name, definition in definitions.items():
        if normalize_condition_label(name) == target:
            return definition

    return None


def _metadata_query_indices(metadata: pd.DataFrame, query: str) -> np.ndarray:
    """Return row indices matching a pandas metadata query."""
    selected = metadata.reset_index(drop=True).query(query, engine="python")
    return selected.index.to_numpy(dtype=int)


def _event_value_indices_from_dataframe(
    metadata: pd.DataFrame,
    values: Sequence[int] | set[int],
) -> np.ndarray:
    """Return row indices whose event-code-like column is in values."""
    value_set = {int(value) for value in values}
    candidate_columns = [
        col
        for col in ("event_code", "value", "event_id")
        if col in metadata.columns
    ]
    if not candidate_columns:
        raise ValueError(
            "Integer condition definitions require an event-code-like column "
            "in epoch metadata (event_code, value, or event_id)."
        )

    mask = np.zeros(len(metadata), dtype=bool)
    for column in candidate_columns:
        numeric = pd.to_numeric(metadata[column], errors="coerce")
        mask |= numeric.isin(value_set).to_numpy()
    return np.flatnonzero(mask)


def condition_candidate_columns(metadata: pd.DataFrame) -> list[str]:
    """Return metadata columns that may carry trigger/condition/event labels."""
    preferred = [
        "selection_labels",
        "event_name",
        "trial_type",
        "condition",
        "event_type",
        "description",
        "trial",
    ]
    cols = [col for col in preferred if col in metadata.columns]
    for col in metadata.columns:
        if col in cols:
            continue
        if pd.api.types.is_object_dtype(metadata[col]) or pd.api.types.is_string_dtype(metadata[col]):
            cols.append(col)
    return cols


def _label_match_indices(metadata: pd.DataFrame, condition: str) -> np.ndarray:
    """Select rows by tolerant string matching against event/condition columns."""
    candidate_columns = condition_candidate_columns(metadata)
    if not candidate_columns:
        raise ValueError(
            "Epoch metadata does not contain a suitable condition column. "
            "Expected one of selection_labels, event_name, trial_type, "
            "condition, event_type, description, or trial."
        )

    target_raw = str(condition)
    target_norm = normalize_condition_label(target_raw)

    exact_mask = np.zeros(len(metadata), dtype=bool)
    normalized_mask = np.zeros(len(metadata), dtype=bool)
    contains_mask = np.zeros(len(metadata), dtype=bool)

    for column in candidate_columns:
        values = metadata[column].astype(str)
        exact_mask |= (values == target_raw).to_numpy()
        norm_values = values.map(normalize_condition_label)
        normalized_mask |= (norm_values == target_norm).to_numpy()
        contains_mask |= norm_values.map(
            lambda value: bool(target_norm) and (target_norm in value or value in target_norm)
        ).to_numpy()

    for mask in (exact_mask, normalized_mask, contains_mask):
        idx = np.flatnonzero(mask)
        if idx.size > 0:
            return idx

    available: list[str] = []
    for column in candidate_columns[:5]:
        vals = metadata[column].dropna().astype(str).unique().tolist()[:20]
        available.append(f"{column}: {vals}")
    raise ValueError(
        f"Condition {condition!r} selected no epochs. Available examples: "
        + " | ".join(available)
    )


def select_epoch_indices_from_metadata(
    metadata: pd.DataFrame,
    condition: str,
    *,
    definitions: Mapping[str, ConditionDefinition] | None = None,
) -> np.ndarray:
    """Select row indices for a condition from epoch metadata.

    Supported cases:
    - ``condition == 'all'``: all rows.
    - ``condition`` names a configured definition: use that pandas query or list
      of event codes.
    - ``condition`` itself is a pandas query: use it directly.
    - otherwise: tolerant string match against event_name/trial_type/etc.
    """
    if condition == "all":
        return np.arange(len(metadata), dtype=int)

    definition = resolve_condition_definition(condition, definitions)
    if definition is not None:
        if isinstance(definition, str):
            return _metadata_query_indices(metadata, definition)
        if isinstance(definition, (list, tuple, set)):
            return _event_value_indices_from_dataframe(metadata, definition)
        raise TypeError(
            "Condition definitions must be metadata query strings or collections "
            f"of integer event IDs, got {type(definition)!r}."
        )

    # If the condition string looks like a pandas query, try it before falling
    # back to label matching. This keeps simple trigger workflows intact while
    # allowing ad-hoc query strings such as ``non_diatonic == 1``.
    looks_like_query = bool(re.search(r"\b(and|or|not|in)\b|==|!=|<=|>=|<|>|\.isin\(", str(condition)))
    if looks_like_query:
        try:
            idx = _metadata_query_indices(metadata, str(condition))
        except Exception as exc:
            raise ValueError(f"Invalid condition query {condition!r}: {exc}") from exc
        if idx.size == 0:
            raise ValueError(f"Condition query {condition!r} selected no epochs.")
        return idx

    return _label_match_indices(metadata, condition)


def event_value_indices_from_mne_epochs(epochs: Any, values: Sequence[int] | set[int]) -> list[int]:
    value_set = {int(value) for value in values}
    event_codes = epochs.events[:, 2]
    return [int(index) for index, code in enumerate(event_codes) if int(code) in value_set]


def condition_indices_from_mne_epochs(
    epochs: Any,
    condition: ConditionDefinition,
) -> list[int]:
    """Return integer MNE epoch indices for a query or event-code condition."""
    if isinstance(condition, str):
        if epochs.metadata is None:
            return []
        return _metadata_query_indices(epochs.metadata, condition).astype(int).tolist()

    if isinstance(condition, (list, tuple, set)):
        return event_value_indices_from_mne_epochs(epochs, condition)

    raise TypeError(
        "Condition definitions must be metadata query strings or collections "
        f"of integer event IDs, got {type(condition)!r}."
    )
