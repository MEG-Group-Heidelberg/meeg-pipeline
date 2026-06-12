from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import mne
import pandas as pd
from mne import Epochs, Evoked

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.epoching import make_epochs_path


ExistingOutputPolicy = Literal["skip", "overwrite"]
ConditionDefinition = str | list[int] | tuple[int, ...] | set[int]


@dataclass(frozen=True)
class LoadEpochsResult:
    epochs: Epochs | None
    path: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class EvokedConditionResult:
    condition: str
    status: str
    n_epochs: int = 0
    message: str = ""


@dataclass(frozen=True)
class EvokedResult:
    path: str
    status: str
    n_evokeds: int = 0
    conditions: list[str] | None = None
    condition_results: list[EvokedConditionResult] | None = None
    message: str = ""


def _recording_parts(
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> list[str]:
    subject = subject.removeprefix("sub-")

    parts = [f"sub-{subject}"]

    if session is not None:
        parts.append(f"ses-{session}")

    if task is not None:
        parts.append(f"task-{task}")

    if run is not None:
        parts.append(f"run-{run}")

    return parts


def _derivative_directory(
    config: PipelineConfig,
    *,
    subject: str,
    session: str | None = None,
) -> Path:
    subject = subject.removeprefix("sub-")

    if session is None:
        return config.paths.derivatives_root / f"sub-{subject}" / config.bids.datatype

    return (
        config.paths.derivatives_root
        / f"sub-{subject}"
        / f"ses-{session}"
        / config.bids.datatype
    )


def make_evokeds_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "evoked",
) -> Path:
    """Create derivative path for averaged evoked responses."""
    parts = _recording_parts(
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    basename = "_".join(parts + [f"desc-{desc}", "ave.fif"])

    return _derivative_directory(
        config,
        subject=subject,
        session=session,
    ) / basename


def load_epochs_for_evokeds(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    preload: bool = True,
) -> LoadEpochsResult:
    """Load epochs if they exist."""
    path = make_epochs_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return LoadEpochsResult(
            epochs=None,
            path=str(path),
            status="missing_input",
            message="Epochs file does not exist.",
        )

    epochs = mne.read_epochs(
        path,
        preload=preload,
        verbose="error",
    )

    return LoadEpochsResult(
        epochs=epochs,
        path=str(path),
        status="loaded",
    )


def _metadata_query_indices(
    epochs: Epochs,
    query: str,
) -> list[int]:
    """Return integer epoch indices matching a pandas metadata query."""
    if epochs.metadata is None:
        return []

    metadata = epochs.metadata.reset_index(drop=True)
    selected = metadata.query(query, engine="python")

    return [int(index) for index in selected.index.to_list()]


def _event_value_indices(
    epochs: Epochs,
    values: list[int] | tuple[int, ...] | set[int],
) -> list[int]:
    """Return integer epoch indices whose MNE event code is in values."""
    value_set = {int(value) for value in values}
    event_codes = epochs.events[:, 2]

    return [
        int(index)
        for index, code in enumerate(event_codes)
        if int(code) in value_set
    ]


def condition_indices(
    epochs: Epochs,
    condition: ConditionDefinition,
) -> list[int]:
    """Return epoch indices for a condition definition.

    Supported condition definitions:

    - str:
        pandas query applied to epochs.metadata, e.g.
        "non_diatonic in [1, 2, 3, 4, 5]"

    - list/tuple/set of int:
        MNE event codes to select from epochs.events[:, 2], useful for older
        event-id based workflows.
    """
    if isinstance(condition, str):
        return _metadata_query_indices(epochs, condition)

    if isinstance(condition, (list, tuple, set)):
        return _event_value_indices(epochs, condition)

    raise TypeError(
        "Condition definitions must be metadata query strings or collections "
        f"of integer event IDs, got {type(condition)!r}."
    )


def make_evokeds(
    epochs: Epochs,
    conditions: dict[str, ConditionDefinition],
    *,
    copy_bads_from_epochs: bool = True,
) -> tuple[list[Evoked], list[EvokedConditionResult]]:
    """Create evoked responses from epochs using condition definitions."""
    evokeds: list[Evoked] = []
    condition_results: list[EvokedConditionResult] = []

    for condition_name, condition in conditions.items():
        indices = condition_indices(epochs, condition)

        if not indices:
            condition_results.append(
                EvokedConditionResult(
                    condition=condition_name,
                    status="no_epochs",
                    n_epochs=0,
                    message="No epochs matched this condition.",
                )
            )
            continue

        selected_epochs = epochs[indices]
        evoked = selected_epochs.average()
        evoked.comment = condition_name

        if copy_bads_from_epochs:
            evoked.info["bads"] = [
                ch_name
                for ch_name in epochs.info["bads"]
                if ch_name in evoked.info["ch_names"]
            ]

        evokeds.append(evoked)
        condition_results.append(
            EvokedConditionResult(
                condition=condition_name,
                status="computed",
                n_epochs=len(selected_epochs),
            )
        )

    return evokeds, condition_results


def write_evokeds_for_recording(
    config: PipelineConfig,
    *,
    subject: str,
    conditions: dict[str, ConditionDefinition],
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    desc: str = "evoked",
) -> EvokedResult:
    """Create and write evokeds for one recording."""
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    output_path = make_evokeds_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=desc,
    )

    if output_path.exists() and on_existing == "skip":
        return EvokedResult(
            path=str(output_path),
            status="skipped_existing",
            message="Evokeds file already exists.",
        )

    epochs_result = load_epochs_for_evokeds(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        preload=True,
    )

    if epochs_result.epochs is None:
        return EvokedResult(
            path=str(output_path),
            status=epochs_result.status,
            message=epochs_result.message,
        )

    evokeds, condition_results = make_evokeds(
        epochs_result.epochs,
        conditions,
    )

    if not evokeds:
        return EvokedResult(
            path=str(output_path),
            status="no_evokeds",
            n_evokeds=0,
            conditions=[],
            condition_results=condition_results,
            message="No evokeds were created because no conditions matched epochs.",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mne.write_evokeds(
        output_path,
        evokeds,
        overwrite=on_existing == "overwrite",
        verbose="error",
    )

    return EvokedResult(
        path=str(output_path),
        status="written",
        n_evokeds=len(evokeds),
        conditions=[evoked.comment for evoked in evokeds],
        condition_results=condition_results,
    )


def write_evokeds_for_recordings(
    config: PipelineConfig,
    recordings: list[dict[str, str | None]],
    *,
    conditions: dict[str, ConditionDefinition],
    on_existing: ExistingOutputPolicy = "skip",
    desc: str = "evoked",
) -> list[EvokedResult]:
    """Create and write evokeds for multiple recordings."""
    return [
        write_evokeds_for_recording(
            config,
            subject=recording["subject"],
            session=recording.get("session"),
            task=recording.get("task"),
            run=recording.get("run"),
            conditions=conditions,
            on_existing=on_existing,
            desc=desc,
        )
        for recording in recordings
    ]
