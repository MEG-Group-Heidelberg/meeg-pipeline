from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from meeg_pipeline.bids import list_bids_entities, make_events_path
from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.paths import bids_path_to_path

EntitySelection = str | Sequence[str] | set[str] | None
Recording = dict[str, str | None]
ExistingOutputPolicy = Literal["skip", "overwrite"]
ManualDecisionPolicy = Literal["load", "overwrite"]


def as_set(value: Any) -> set[Any]:
    """Return *value* as a set.

    This is useful for notebook parameters that may be written as ``None``, a
    single value, or a list/tuple/set of values.
    """
    if value is None:
        return set()

    if isinstance(value, set):
        return value

    if isinstance(value, (list, tuple)):
        return set(value)

    return {value}


def sorted_nonmissing_unique(values: Iterable[Any]) -> list[Any]:
    """Return sorted unique values, excluding missing values.

    Missing means ``None`` or pandas-style ``NA``/``NaN``.
    """
    unique: set[Any] = set()

    for value in values:
        if value is None:
            continue

        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass

        unique.add(value)

    return sorted(unique)


def safe_join(values: Iterable[Any], *, sep: str = ", ", missing: str = "") -> str:
    """Join non-missing values as strings.

    Returns ``missing`` when no non-missing values are present.
    """
    clean_values = sorted_nonmissing_unique(values)

    if not clean_values:
        return missing

    return sep.join(str(value) for value in clean_values)


def resolve_entity_values(
    config: PipelineConfig,
    entity: str,
    selection: EntitySelection,
) -> list[str | None]:
    """Resolve a notebook selection for one BIDS entity.

    Allowed selections are:
    - ``None``: entity is not used, returns ``[None]``
    - ``"all"``: all detected values for the entity
    - ``["all"]``: same as ``"all"``
    - one value, e.g. ``"01"``
    - multiple values, e.g. ``["01", "02"]``

    If no values are available for ``"all"``, ``[None]`` is returned. This keeps
    partially acquired or not-yet-converted projects usable in notebooks.
    """
    if selection is None:
        return [None]

    available_values = list_bids_entities(config, entity)

    if selection == "all":
        return available_values if available_values else [None]

    if isinstance(selection, (list, tuple, set)):
        values = list(selection)

        if "all" in values:
            return available_values if available_values else [None]

        return [None if value is None else str(value) for value in values]

    return [str(selection)]


def iter_recordings(
    config: PipelineConfig,
    *,
    subjects: EntitySelection,
    sessions: EntitySelection = None,
    tasks: EntitySelection = None,
    runs: EntitySelection = None,
) -> Iterable[Recording]:
    """Yield concrete subject/session/task/run combinations.

    The yielded dictionaries are accepted by high-level pipeline functions that
    expect ``subject``, ``session``, ``task``, and ``run`` keys.
    """
    for subject in resolve_entity_values(config, "subject", subjects):
        if subject is None:
            continue

        for session in resolve_entity_values(config, "session", sessions):
            for task in resolve_entity_values(config, "task", tasks):
                for run in resolve_entity_values(config, "run", runs):
                    yield {
                        "subject": subject,
                        "session": session,
                        "task": task,
                        "run": run,
                    }


def recording_label(recording: Recording) -> str:
    """Return a compact BIDS-like label for one recording dictionary."""
    subject = recording.get("subject")

    if subject is None:
        raise ValueError("recording must contain a non-missing 'subject'.")

    parts = [f"sub-{str(subject).removeprefix('sub-')}"]

    session = recording.get("session")
    task = recording.get("task")
    run = recording.get("run")

    if session is not None:
        parts.append(f"ses-{session}")
    if task is not None:
        parts.append(f"task-{task}")
    if run is not None:
        parts.append(f"run-{run}")

    return "_".join(parts)


def recordings_to_dataframe(
    recordings: Iterable[Recording],
    *,
    include_index: bool = False,
) -> pd.DataFrame:
    """Convert recording dictionaries to a notebook-friendly table."""
    rows = []

    for index, recording in enumerate(recordings):
        row = {
            "recording": recording_label(recording),
            "subject": recording.get("subject"),
            "session": recording.get("session"),
            "task": recording.get("task"),
            "run": recording.get("run"),
        }

        if include_index:
            row = {"index": index, **row}

        rows.append(row)

    columns = ["recording", "subject", "session", "task", "run"]
    if include_index:
        columns = ["index", *columns]

    return pd.DataFrame(rows, columns=columns)


def selected_recordings_to_dataframe(recordings: Iterable[Recording]) -> pd.DataFrame:
    """Convert selected recordings to a table with stable inspection indices.

    This is a readable alias for ``recordings_to_dataframe(..., include_index=True)``.
    """
    return recordings_to_dataframe(recordings, include_index=True)


def _recording_matches(
    recording: Recording,
    *,
    subject: str,
    session: str | None,
    task: str | None,
    run: str | None,
) -> bool:
    """Return whether one recording matches the requested BIDS entities."""
    return (
        str(recording.get("subject", "")).removeprefix("sub-")
        == subject.removeprefix("sub-")
        and recording.get("session") == session
        and recording.get("task") == task
        and recording.get("run") == run
    )


def find_recording(
    recordings: Iterable[Recording],
    *,
    subject: str,
    session: str | None = None,
    task: str | None = None,
    run: str | None = None,
    require: bool = False,
) -> Recording | None:
    """Find one recording matching the requested BIDS entities.

    The subject can be passed with or without the ``sub-`` prefix.

    Returns ``None`` when no matching recording is found, unless ``require=True``.
    Raises ``ValueError`` if more than one recording matches.
    """
    matches = [
        recording
        for recording in recordings
        if _recording_matches(
            recording,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )
    ]

    if len(matches) == 1:
        return matches[0]

    requested = recording_label(
        {
            "subject": subject,
            "session": session,
            "task": task,
            "run": run,
        }
    )

    if len(matches) > 1:
        raise ValueError(
            f"Expected at most one recording matching {requested!r}, "
            f"found {len(matches)}."
        )

    if require:
        raise ValueError(f"No recording matching {requested!r} was found.")

    return None


def should_overwrite(step_name: str, overwrite_steps: Sequence[str] | str) -> bool:
    """Return whether a workflow step should overwrite existing outputs.

    ``overwrite_steps`` is intended for notebook-level settings such as::

        OVERWRITE_STEPS = []
        OVERWRITE_STEPS = ["events"]
        OVERWRITE_STEPS = "all"
    """
    if overwrite_steps == "all":
        return True

    if isinstance(overwrite_steps, str):
        raise ValueError(
            f"Invalid overwrite_steps value: {overwrite_steps!r}. "
            "Use 'all' or a list/tuple/set of step names."
        )

    if isinstance(overwrite_steps, (list, tuple, set)):
        return step_name in overwrite_steps

    raise ValueError(
        f"Invalid overwrite_steps value: {overwrite_steps!r}. "
        "Use 'all' or a list/tuple/set of step names."
    )


def existing_output_policy_for_step(
    step_name: str,
    overwrite_steps: Sequence[str] | str,
) -> ExistingOutputPolicy:
    """Return ``'overwrite'`` or ``'skip'`` for file-producing steps."""
    return "overwrite" if should_overwrite(step_name, overwrite_steps) else "skip"


def decision_policy_for_step(
    step_name: str,
    overwrite_steps: Sequence[str] | str,
) -> ManualDecisionPolicy:
    """Return ``'overwrite'`` or ``'load'`` for manual decision steps.

    This is suitable for outputs such as manually reviewed bad-channel or
    bad-segment decisions, where existing files should normally be loaded rather
    than skipped.
    """
    return "overwrite" if should_overwrite(step_name, overwrite_steps) else "load"


def bad_channels_policy_for_step(
    step_name: str,
    overwrite_steps: Sequence[str] | str,
) -> ManualDecisionPolicy:
    """Return policy for manual bad-channel decisions.

    This is a readable alias for ``decision_policy_for_step``.
    """
    return decision_policy_for_step(step_name, overwrite_steps)


def raw_events_path(
    config: PipelineConfig,
    recording: Recording | None = None,
    *,
    subject: str | None = None,
    session: str | None = None,
    task: str | None = None,
    run: str | None = None,
) -> Path:
    """Return the raw BIDS ``events.tsv`` path for one recording."""
    if recording is not None:
        subject = recording.get("subject")
        session = recording.get("session")
        task = recording.get("task")
        run = recording.get("run")

    if subject is None:
        raise ValueError("subject is required.")

    return bids_path_to_path(
        make_events_path(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )
    )


def read_raw_events(
    config: PipelineConfig,
    recording: Recording | None = None,
    *,
    subject: str | None = None,
    session: str | None = None,
    task: str | None = None,
    run: str | None = None,
) -> pd.DataFrame | None:
    """Read a raw BIDS ``events.tsv`` file if it exists.

    Missing files return ``None`` instead of raising ``FileNotFoundError`` so
    batch notebook workflows can report missing recordings without stopping.
    """
    path = raw_events_path(
        config,
        recording,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return None

    return pd.read_csv(path, sep="\t")


def _recording_entities(recording: Recording) -> dict[str, str | None]:
    """Return BIDS entity keyword arguments for one recording."""
    return {
        "subject": recording.get("subject"),
        "session": recording.get("session"),
        "task": recording.get("task"),
        "run": recording.get("run"),
    }


def recording_path_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    path_func: Callable[..., Path],
    *,
    exists_column: str = "exists",
    path_column: str = "path",
) -> pd.DataFrame:
    """Summarize expected paths for recordings.

    ``path_func`` must accept ``config`` plus ``subject``, ``session``, ``task``,
    and ``run`` keyword arguments. This works with helpers such as
    ``make_filtered_raw_path`` or ``make_bad_channels_path``.
    """
    rows = []

    for recording in recordings:
        path = path_func(config, **_recording_entities(recording))

        rows.append(
            {
                "recording": recording_label(recording),
                exists_column: path.exists(),
                path_column: str(path),
            }
        )

    return pd.DataFrame(rows)


def bad_channels_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
) -> pd.DataFrame:
    """Summarize saved bad-channel decisions for selected recordings."""
    from meeg_pipeline.qc import load_bad_channels, make_bad_channels_path

    rows = []

    for recording in recordings:
        entities = _recording_entities(recording)
        path = make_bad_channels_path(config, **entities)

        if path.exists():
            bad_channels = load_bad_channels(config, **entities)
            bads = ", ".join(bad_channels.bads)
            n_bad_channels = len(bad_channels.bads)
            method = bad_channels.method
        else:
            bads = ""
            n_bad_channels = None
            method = ""

        rows.append(
            {
                "recording": recording_label(recording),
                "badchannels_exists": path.exists(),
                "n_bad_channels": n_bad_channels,
                "bad_channels": bads,
                "method": method,
                "path": str(path),
            }
        )

    return pd.DataFrame(rows)


def annotation_policy_for_step(
    step_name: str,
    overwrite_steps: Sequence[str] | str,
) -> ManualDecisionPolicy:
    """Return policy for manual bad-segment annotation decisions.

    This is a readable alias for ``decision_policy_for_step``. Existing
    annotation derivatives are normally loaded; selected steps can be
    overwritten via notebook-level ``OVERWRITE_STEPS``.
    """
    return decision_policy_for_step(step_name, overwrite_steps)


def bad_annotations_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
) -> pd.DataFrame:
    """Summarize saved bad-segment annotation decisions for recordings."""
    from meeg_pipeline.annotations import load_bad_annotations

    rows = []

    for recording in recordings:
        result = load_bad_annotations(config, **_recording_entities(recording))

        rows.append(
            {
                "recording": recording_label(recording),
                "annotations_status": result.status,
                "annotations_exists": result.annotations is not None,
                "n_annotations": result.n_annotations,
                "n_bad_annotations": result.n_bad_annotations,
                "descriptions": safe_join(result.descriptions or []),
                "message": result.message,
                "path": result.path,
            }
        )

    return pd.DataFrame(rows)


def applied_bad_annotations_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    preload: bool = False,
) -> pd.DataFrame:
    """Check whether bad-segment annotations can be applied to filtered raws.

    This helper is intended for notebook QC tables. It loads each filtered raw
    derivative, applies saved bad-segment annotations when available, and returns
    one status row per recording. Missing filtered inputs or missing annotation
    derivatives are reported in the table instead of raising an exception.
    """
    from meeg_pipeline.annotations import apply_bad_annotations
    from meeg_pipeline.preprocessing import load_filtered_raw

    rows = []

    for recording in recordings:
        entities = _recording_entities(recording)
        filtered_result = load_filtered_raw(config, **entities, preload=preload)

        if filtered_result.raw is None:
            rows.append(
                {
                    "recording": recording_label(recording),
                    "filtered_status": filtered_result.status,
                    "annotation_status": "skipped",
                    "message": filtered_result.message,
                    "n_annotations": None,
                    "n_bad_annotations": None,
                }
            )
            continue

        annotation_result = apply_bad_annotations(
            filtered_result.raw,
            config,
            **entities,
        )

        rows.append(
            {
                "recording": recording_label(recording),
                "filtered_status": filtered_result.status,
                "annotation_status": annotation_result.status,
                "message": annotation_result.message,
                "n_annotations": annotation_result.n_annotations,
                "n_bad_annotations": annotation_result.n_bad_annotations,
            }
        )

    return pd.DataFrame(rows)


def recording_results_to_dataframe(
    recordings: Iterable[Recording],
    results: Iterable[Any],
    *,
    include_index: bool = False,
    fields: Sequence[str] = ("status", "message", "path"),
) -> pd.DataFrame:
    """Convert per-recording result objects to a notebook-friendly table.

    ``results`` may contain dataclass instances, simple objects, or dictionaries.
    The requested ``fields`` are read from each result and paired with the
    corresponding recording label.
    """
    rows = []

    for index, (recording, result) in enumerate(zip(recordings, results, strict=True)):
        row = {"recording": recording_label(recording)}

        if include_index:
            row = {"index": index, **row}

        for field in fields:
            if isinstance(result, dict):
                value = result.get(field)
            else:
                value = getattr(result, field, None)

            row[field] = value

        rows.append(row)

    columns = ["recording", *fields]
    if include_index:
        columns = ["index", *columns]

    return pd.DataFrame(rows, columns=columns)


def ica_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
) -> pd.DataFrame:
    """Summarize ICA-cleaning inputs, decisions, and outputs.

    This is intended for notebook overview tables before and after ICA cleaning.
    It checks filtered raw inputs, saved bad-channel decisions, saved
    bad-segment annotations, fitted ICA files, ICA decisions, and cleaned raw
    outputs without modifying any files.
    """
    from meeg_pipeline.annotations import load_bad_annotations
    from meeg_pipeline.cleaning import (
        load_ica_decision,
        make_cleaned_raw_path,
        make_ica_path,
    )
    from meeg_pipeline.preprocessing import make_filtered_raw_path
    from meeg_pipeline.qc import load_bad_channels

    rows = []

    for recording in recordings:
        entities = _recording_entities(recording)

        filtered_path = make_filtered_raw_path(config, **entities)
        bad_channels = load_bad_channels(config, **entities)
        annotations = load_bad_annotations(config, **entities)
        ica_path = make_ica_path(config, **entities)
        decision = load_ica_decision(config, **entities)
        cleaned_path = make_cleaned_raw_path(config, **entities)

        rows.append(
            {
                "recording": recording_label(recording),
                "filtered_exists": filtered_path.exists(),
                "badchannels_status": bad_channels.status,
                "n_bad_channels": len(bad_channels.bads),
                "annotations_status": annotations.status,
                "n_bad_annotations": annotations.n_bad_annotations,
                "ica_exists": ica_path.exists(),
                "decision_status": decision.status,
                "exclude": safe_join(decision.exclude),
                "cleaned_raw_exists": cleaned_path.exists(),
                "filtered_path": str(filtered_path),
                "ica_path": str(ica_path),
                "decision_path": decision.path,
                "cleaned_path": str(cleaned_path),
            }
        )

    return pd.DataFrame(rows)


def ica_decisions_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
) -> pd.DataFrame:
    """Summarize saved manual ICA exclusion decisions for recordings."""
    from meeg_pipeline.cleaning import load_ica_decision

    rows = []

    for recording in recordings:
        result = load_ica_decision(config, **_recording_entities(recording))

        rows.append(
            {
                "recording": recording_label(recording),
                "status": result.status,
                "exclude": safe_join(result.exclude),
                "n_excluded": len(result.exclude),
                "method": result.method,
                "notes": result.notes,
                "message": result.message,
                "path": result.path,
            }
        )

    return pd.DataFrame(rows)


def epoching_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    preload_raw: bool = False,
) -> pd.DataFrame:
    """Summarize epoching inputs and expected epoch outputs.

    Event priority is handled by ``load_events_for_epoching``:
    analysis-event derivatives are preferred when present, otherwise raw BIDS
    ``events.tsv`` files are used.
    """
    from meeg_pipeline.epoching import (
        load_cleaned_raw_for_epoching,
        load_events_for_epoching,
        make_epochs_path,
    )

    rows = []

    for recording in recordings:
        entities = _recording_entities(recording)

        raw_result = load_cleaned_raw_for_epoching(
            config,
            **entities,
            preload=preload_raw,
        )
        events_result = load_events_for_epoching(config, **entities)
        epochs_path = make_epochs_path(config, **entities)

        n_events = 0 if events_result.events is None else len(events_result.events)

        rows.append(
            {
                "recording": recording_label(recording),
                "cleaned_raw_status": raw_result.status,
                "events_status": events_result.status,
                "events_kind": events_result.kind,
                "n_events": n_events,
                "epochs_exists": epochs_path.exists(),
                "cleaned_raw_path": raw_result.path,
                "events_path": events_result.path,
                "epochs_path": str(epochs_path),
                "message": raw_result.message or events_result.message,
            }
        )

    return pd.DataFrame(rows)


def event_coding_preview_to_dataframe(
    config: PipelineConfig,
    recording: Recording,
    *,
    event_code_mode: str = "trial_type",
) -> pd.DataFrame:
    """Preview MNE event coding for one recording.

    This helper loads the event table chosen by ``load_events_for_epoching`` and
    reports how many MNE events and event IDs would be created. The full event
    table is not returned; notebooks should call ``load_events_for_epoching``
    directly when they need to inspect or modify project-specific events.
    """
    from meeg_pipeline.epoching import (
        events_table_to_mne_events,
        load_events_for_epoching,
    )

    events_result = load_events_for_epoching(config, **_recording_entities(recording))

    if events_result.events is None:
        return pd.DataFrame(
            [
                {
                    "recording": recording_label(recording),
                    "status": events_result.status,
                    "message": events_result.message,
                    "events_path": events_result.path,
                }
            ]
        )

    mne_events, event_id, metadata = events_table_to_mne_events(
        events_result.events,
        event_code_mode=event_code_mode,
    )

    return pd.DataFrame(
        [
            {
                "recording": recording_label(recording),
                "status": events_result.status,
                "events_kind": events_result.kind,
                "n_events": len(mne_events),
                "n_event_ids": len(event_id),
                "event_id": event_id,
                "events_path": events_result.path,
            }
        ]
    )


def epoching_results_to_dataframe(
    recordings: Iterable[Recording],
    results: Iterable[Any],
) -> pd.DataFrame:
    """Convert epoch-writing results to a notebook-friendly table."""
    return recording_results_to_dataframe(
        recordings,
        results,
        fields=(
            "status",
            "n_epochs",
            "n_events",
            "n_event_ids",
            "events_kind",
            "message",
            "path",
        ),
    )


def evokeds_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    conditions: dict[str, Any],
    *,
    preload: bool = False,
) -> pd.DataFrame:
    """Summarize evoked-generation inputs and expected condition outputs.

    Condition definitions are intentionally passed in by the notebook or project
    code. This keeps project-specific experimental logic outside the library
    while making the repeated input/output checks reusable.
    """
    from meeg_pipeline.evokeds import (
        condition_indices,
        load_epochs_for_evokeds,
        make_evoked_path,
    )

    rows = []

    for recording in recordings:
        entities = _recording_entities(recording)
        epochs_result = load_epochs_for_evokeds(
            config,
            **entities,
            preload=preload,
        )

        evoked_paths = {
            condition_name: make_evoked_path(
                config,
                **entities,
                condition=condition_name,
            )
            for condition_name in conditions
        }

        if epochs_result.epochs is None:
            n_epochs = 0
            metadata_columns = ""
            condition_counts = {}
        else:
            n_epochs = len(epochs_result.epochs)
            metadata_columns = (
                safe_join(list(epochs_result.epochs.metadata.columns))
                if epochs_result.epochs.metadata is not None
                else ""
            )
            condition_counts = {
                name: len(condition_indices(epochs_result.epochs, definition))
                for name, definition in conditions.items()
            }

        rows.append(
            {
                "recording": recording_label(recording),
                "epochs_status": epochs_result.status,
                "n_epochs": n_epochs,
                "condition_counts": condition_counts,
                "n_evoked_files_existing": sum(
                    path.exists() for path in evoked_paths.values()
                ),
                "metadata_columns": metadata_columns,
                "epochs_path": epochs_result.path,
                "evokeds_paths": {
                    name: str(path) for name, path in evoked_paths.items()
                },
                "message": epochs_result.message,
            }
        )

    return pd.DataFrame(rows)


def evoked_metadata_preview_to_dataframe(
    config: PipelineConfig,
    recording: Recording,
    *,
    n_rows: int = 30,
) -> pd.DataFrame:
    """Return a short epochs.metadata preview for one recording.

    Missing epochs or missing metadata yield an empty dataframe so notebooks can
    display the result without additional boilerplate.
    """
    from meeg_pipeline.evokeds import load_epochs_for_evokeds

    epochs_result = load_epochs_for_evokeds(
        config,
        **_recording_entities(recording),
        preload=False,
    )

    if epochs_result.epochs is None or epochs_result.epochs.metadata is None:
        return pd.DataFrame()

    return epochs_result.epochs.metadata.head(n_rows)


def evoked_condition_counts_to_dataframe(
    config: PipelineConfig,
    recording: Recording,
    conditions: dict[str, Any],
) -> pd.DataFrame:
    """Count epochs matching each evoked condition for one recording."""
    from meeg_pipeline.evokeds import condition_indices, load_epochs_for_evokeds

    epochs_result = load_epochs_for_evokeds(
        config,
        **_recording_entities(recording),
        preload=False,
    )

    if epochs_result.epochs is None:
        return pd.DataFrame(
            [
                {
                    "condition": "",
                    "definition": "",
                    "n_epochs": 0,
                    "message": epochs_result.message,
                }
            ]
        )

    return pd.DataFrame(
        [
            {
                "condition": name,
                "definition": definition,
                "n_epochs": len(condition_indices(epochs_result.epochs, definition)),
                "message": "",
            }
            for name, definition in conditions.items()
        ]
    )


def evoked_results_to_dataframe(
    recordings: Iterable[Recording],
    results: Iterable[Any],
) -> pd.DataFrame:
    """Convert evoked-writing results to a notebook-friendly table."""
    rows = []

    for recording, result in zip(recordings, results, strict=True):
        rows.append(
            {
                "recording": recording_label(recording),
                "status": getattr(result, "status", None),
                "n_evokeds": getattr(result, "n_evokeds", None),
                "conditions": safe_join(getattr(result, "conditions", None) or []),
                "message": getattr(result, "message", ""),
                "directory": getattr(result, "directory", None),
            }
        )

    return pd.DataFrame(rows)


def evoked_condition_results_to_dataframe(
    recordings: Iterable[Recording],
    results: Iterable[Any],
) -> pd.DataFrame:
    """Flatten condition-level evoked-writing results into a dataframe."""
    rows = []

    for recording, result in zip(recordings, results, strict=True):
        condition_results = getattr(result, "condition_results", None) or []

        for condition_result in condition_results:
            rows.append(
                {
                    "recording": recording_label(recording),
                    "condition": getattr(condition_result, "condition", None),
                    "status": getattr(condition_result, "status", None),
                    "n_epochs": getattr(condition_result, "n_epochs", None),
                    "desc": getattr(condition_result, "desc", None),
                    "path": getattr(condition_result, "path", None),
                    "message": getattr(condition_result, "message", ""),
                }
            )

    return pd.DataFrame(rows)


def analysis_events_file_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    desc: str = "analysis",
) -> pd.DataFrame:
    """Summarize derivative analysis-event TSV files for selected recordings.

    This helper is intentionally generic: it only checks whether analysis-event
    files exist and reports basic event-table properties. Project-specific event
    derivation logic should stay in project notebooks or project modules.
    """
    from meeg_pipeline.event_derivatives import make_analysis_events_path

    rows = []

    for recording in recordings:
        path = make_analysis_events_path(
            config,
            **_recording_entities(recording),
            desc=desc,
        )

        if path.exists():
            table = pd.read_csv(path, sep="\t")
            rows.append(
                {
                    "recording": recording_label(recording),
                    "exists": True,
                    "n_events": len(table),
                    "trial_types": safe_join(table["trial_type"].unique())
                    if "trial_type" in table
                    else "",
                    "min_onset": float(table["onset"].min())
                    if len(table) and "onset" in table
                    else None,
                    "max_onset": float(table["onset"].max())
                    if len(table) and "onset" in table
                    else None,
                    "path": str(path),
                }
            )
        else:
            rows.append(
                {
                    "recording": recording_label(recording),
                    "exists": False,
                    "n_events": 0,
                    "trial_types": "",
                    "min_onset": None,
                    "max_onset": None,
                    "path": str(path),
                }
            )

    return pd.DataFrame(rows)

def bids_entities_to_dataframe(
    config: PipelineConfig,
    entities: Sequence[str] = ("subject", "session", "task", "run"),
) -> pd.DataFrame:
    """Summarize available values for common BIDS entities."""
    rows = []

    for entity in entities:
        values = list_bids_entities(config, entity)
        rows.append(
            {
                "entity": entity,
                "n": len(values),
                "values": safe_join(values),
            }
        )

    return pd.DataFrame(rows, columns=["entity", "n", "values"])


def source_recordings_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """Summarize source recordings discovered in the configured sourcedata root."""
    from meeg_pipeline.sourcedata import (
        discover_source_recordings,
        make_target_bids_path,
    )

    rows = []

    for recording in discover_source_recordings(config):
        target_bids_path = make_target_bids_path(config, recording)

        rows.append(
            {
                "subject": recording.subject,
                "source_session": getattr(recording, "source_session", None),
                "session": recording.session,
                "task": recording.task,
                "run": recording.run,
                "source_path": str(recording.source_path),
                "target_path": str(bids_path_to_path(target_bids_path)),
                "target_exists": bids_path_to_path(target_bids_path).exists(),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "subject",
            "source_session",
            "session",
            "task",
            "run",
            "source_path",
            "target_path",
            "target_exists",
        ],
    )


def event_file_summary(events_path: Path) -> dict[str, Any]:
    """Summarize an existing BIDS-style events.tsv file.

    The helper is intentionally generic: it only reports basic file, count,
    value, trial-type, and timing-difference information.
    """
    events_path = Path(events_path)

    if not events_path.exists():
        return {
            "events_exists": False,
            "n_events": None,
            "trial_types": "",
            "values": "",
            "min_onset_diff_s": None,
            "median_onset_diff_s": None,
            "max_onset_diff_s": None,
        }

    events_df = pd.read_csv(events_path, sep="\t")

    if len(events_df) > 1 and "onset" in events_df.columns:
        onset_diffs = events_df["onset"].diff().dropna()
        min_onset_diff_s = float(onset_diffs.min())
        median_onset_diff_s = float(onset_diffs.median())
        max_onset_diff_s = float(onset_diffs.max())
    else:
        min_onset_diff_s = None
        median_onset_diff_s = None
        max_onset_diff_s = None

    return {
        "events_exists": True,
        "n_events": len(events_df),
        "trial_types": safe_join(events_df["trial_type"].unique())
        if "trial_type" in events_df.columns
        else "",
        "values": safe_join(events_df["value"].unique())
        if "value" in events_df.columns
        else "",
        "min_onset_diff_s": min_onset_diff_s,
        "median_onset_diff_s": median_onset_diff_s,
        "max_onset_diff_s": max_onset_diff_s,
    }


def raw_events_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
) -> pd.DataFrame:
    """Summarize raw BIDS files and raw events.tsv files for recordings."""
    from meeg_pipeline.bids import make_bids_path

    rows = []

    for recording in recordings:
        entities = _recording_entities(recording)

        raw_path = bids_path_to_path(
            make_bids_path(
                config,
                **entities,
                extension=".fif",
            )
        )
        events_path = raw_events_path(config, recording)
        event_summary = event_file_summary(events_path)

        rows.append(
            {
                "recording": recording_label(recording),
                "raw_exists": raw_path.exists(),
                "events_exists": event_summary["events_exists"],
                "n_events": event_summary["n_events"],
                "raw_path": str(raw_path),
                "events_path": str(events_path),
            }
        )

    return pd.DataFrame(rows)


def event_qc_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
) -> pd.DataFrame:
    """Summarize generic event timing and coding information for recordings."""
    rows = []

    for recording in recordings:
        events_path = raw_events_path(config, recording)
        summary = event_file_summary(events_path)

        rows.append(
            {
                "recording": recording_label(recording),
                "events_exists": summary["events_exists"],
                "n_events": summary["n_events"],
                "values": summary["values"],
                "trial_types": summary["trial_types"],
                "min_onset_diff_s": summary["min_onset_diff_s"],
                "median_onset_diff_s": summary["median_onset_diff_s"],
                "max_onset_diff_s": summary["max_onset_diff_s"],
            }
        )

    return pd.DataFrame(rows)


def default_summary_derivative_steps() -> list[dict[str, str]]:
    """Return generic derivative steps used by the project summary dashboard."""
    return [
        {"step": "bad_channels", "kind": "bad_channels"},
        {"step": "filtered_raw", "kind": "filtered_raw"},
        {"step": "bad_segment_annotations", "kind": "bad_annotations"},
        {"step": "ica", "kind": "ica"},
        {"step": "ica_decision", "kind": "ica_decision"},
        {"step": "cleaned_raw", "kind": "cleaned_raw"},
        {"step": "analysis_events", "kind": "analysis_events"},
        {"step": "epochs", "kind": "epochs"},
        {"step": "evokeds", "kind": "evokeds"},
    ]


def _summary_derivative_path(
    config: PipelineConfig,
    recording: Recording,
    *,
    kind: str,
) -> Path | None:
    entities = _recording_entities(recording)

    if kind == "bad_channels":
        from meeg_pipeline.qc import make_bad_channels_path

        return make_bad_channels_path(config, **entities)

    if kind == "filtered_raw":
        from meeg_pipeline.preprocessing import make_filtered_raw_path

        return make_filtered_raw_path(config, **entities)

    if kind == "bad_annotations":
        from meeg_pipeline.annotations import make_bad_annotations_path

        return make_bad_annotations_path(config, **entities)

    if kind == "ica":
        from meeg_pipeline.cleaning import make_ica_path

        return make_ica_path(config, **entities)

    if kind == "ica_decision":
        from meeg_pipeline.cleaning import make_ica_decision_path

        return make_ica_decision_path(config, **entities)

    if kind == "cleaned_raw":
        from meeg_pipeline.cleaning import make_cleaned_raw_path

        return make_cleaned_raw_path(config, **entities)

    if kind == "analysis_events":
        from meeg_pipeline.event_derivatives import make_analysis_events_path

        return make_analysis_events_path(config, **entities, desc="analysis")

    if kind == "epochs":
        from meeg_pipeline.epoching import make_epochs_path

        return make_epochs_path(config, **entities)

    if kind == "evokeds":
        return None

    raise ValueError(f"Unknown summary derivative kind: {kind!r}.")


def _recording_derivative_glob(
    config: PipelineConfig,
    recording: Recording,
    *,
    kind: str,
    pattern: str,
) -> list[Path]:
    from meeg_pipeline.paths import derivative_directory

    directory = derivative_directory(
        config,
        subject=recording["subject"],
        session=recording.get("session"),
        kind=kind,
    )
    prefix = recording_label(recording)

    if not directory.exists():
        return []

    return sorted(directory.glob(f"{prefix}{pattern}"))


def summary_derivative_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    steps: Sequence[dict[str, str]] | None = None,
) -> pd.DataFrame:
    """Return a compact derivative-exists matrix for selected recordings."""
    if steps is None:
        steps = default_summary_derivative_steps()

    rows = []

    for recording in recordings:
        row = {"recording": recording_label(recording)}

        for step in steps:
            step_name = step["step"]
            kind = step["kind"]

            if kind == "evokeds":
                paths = _recording_derivative_glob(
                    config,
                    recording,
                    kind="evokeds",
                    pattern="*_ave.fif",
                )
                row[step_name] = bool(paths)
            else:
                path = _summary_derivative_path(config, recording, kind=kind)
                row[step_name] = path.exists() if path is not None else False

        rows.append(row)

    return pd.DataFrame(rows)


def summary_derivative_paths_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    steps: Sequence[dict[str, str]] | None = None,
) -> pd.DataFrame:
    """Return paths behind the project-summary derivative status matrix."""
    if steps is None:
        steps = default_summary_derivative_steps()

    rows = []

    for recording in recordings:
        for step in steps:
            step_name = step["step"]
            kind = step["kind"]

            if kind == "evokeds":
                paths = _recording_derivative_glob(
                    config,
                    recording,
                    kind="evokeds",
                    pattern="*_ave.fif",
                )
                if paths:
                    for path in paths:
                        rows.append(
                            {
                                "recording": recording_label(recording),
                                "step": step_name,
                                "exists": True,
                                "path": str(path),
                            }
                        )
                else:
                    rows.append(
                        {
                            "recording": recording_label(recording),
                            "step": step_name,
                            "exists": False,
                            "path": "",
                        }
                    )
                continue

            path = _summary_derivative_path(config, recording, kind=kind)
            rows.append(
                {
                    "recording": recording_label(recording),
                    "step": step_name,
                    "exists": path.exists() if path is not None else False,
                    "path": str(path) if path is not None else "",
                }
            )

    return pd.DataFrame(rows)


def derivative_files_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """List files below the configured derivatives root."""
    derivatives_root = config.paths.derivatives_root

    if not derivatives_root.exists():
        return pd.DataFrame(columns=["path", "size_mb"])

    files = sorted(path for path in derivatives_root.rglob("*") if path.is_file())

    return pd.DataFrame(
        {
            "path": [str(path.relative_to(config.paths.bids_root)) for path in files],
            "size_mb": [round(path.stat().st_size / 1024**2, 4) for path in files],
        }
    )


def project_status_summary_to_dataframe(
    *,
    selected_recordings: Sequence[Recording],
    source_recordings: pd.DataFrame,
    raw_events_status: pd.DataFrame,
    bad_channel_status: pd.DataFrame,
    annotation_status: pd.DataFrame,
    derivative_matrix: pd.DataFrame,
    derivative_files: pd.DataFrame,
) -> pd.DataFrame:
    """Create a compact count summary from project-dashboard tables."""
    def _count_true(table: pd.DataFrame, column: str) -> int:
        if table.empty or column not in table:
            return 0
        return int(table[column].sum())

    rows = [
        {
            "item": "selected_recordings",
            "value": len(selected_recordings),
        },
        {
            "item": "source_recordings_discovered",
            "value": len(source_recordings),
        },
        {
            "item": "raw_bids_files_existing",
            "value": _count_true(raw_events_status, "raw_exists"),
        },
        {
            "item": "raw_events_files_existing",
            "value": _count_true(raw_events_status, "events_exists"),
        },
        {
            "item": "bad_channel_files_existing",
            "value": _count_true(bad_channel_status, "badchannels_exists"),
        },
        {
            "item": "filtered_raw_files_existing",
            "value": _count_true(derivative_matrix, "filtered_raw"),
        },
        {
            "item": "bad_segment_annotation_files_existing",
            "value": _count_true(annotation_status, "annotations_exists"),
        },
        {
            "item": "ica_files_existing",
            "value": _count_true(derivative_matrix, "ica"),
        },
        {
            "item": "ica_decision_files_existing",
            "value": _count_true(derivative_matrix, "ica_decision"),
        },
        {
            "item": "cleaned_raw_files_existing",
            "value": _count_true(derivative_matrix, "cleaned_raw"),
        },
        {
            "item": "analysis_events_files_existing",
            "value": _count_true(derivative_matrix, "analysis_events"),
        },
        {
            "item": "epoch_files_existing",
            "value": _count_true(derivative_matrix, "epochs"),
        },
        {
            "item": "evoked_files_existing",
            "value": _count_true(derivative_matrix, "evokeds"),
        },
        {
            "item": "derivative_files_existing",
            "value": len(derivative_files),
        },
    ]

    return pd.DataFrame(rows)

