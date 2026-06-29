from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mne
from mne import Epochs, Evoked

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.conditions import (
    ConditionDefinition,
    condition_definitions_from_config,
    condition_indices_from_mne_epochs,
)
from meeg_pipeline.epoching import make_epochs_path
from meeg_pipeline.paths import derivative_path, sanitize_bids_label


ExistingOutputPolicy = Literal["skip", "overwrite"]


@dataclass(frozen=True)
class LoadEpochsResult:
    epochs: Epochs | None
    path: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class EvokedConditionResult:
    condition: str
    path: str
    status: str
    n_epochs: int = 0
    desc: str = ""
    message: str = ""


@dataclass(frozen=True)
class EvokedResult:
    directory: str
    status: str
    n_evokeds: int = 0
    conditions: list[str] | None = None
    condition_results: list[EvokedConditionResult] | None = None
    message: str = ""


def make_evoked_path(
    config: PipelineConfig,
    *,
    subject: str,
    condition: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create derivative path for one condition-specific evoked response.

    One evoked file is written per condition to keep downstream source-analysis
    and reporting workflows simple.
    """
    desc = sanitize_bids_label(condition)

    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="evokeds",
        suffix=f"desc-{desc}_ave.fif",
    )


def make_evokeds_directory(
    config: PipelineConfig,
    *,
    subject: str,
    session: str | None = None,
) -> Path:
    """Return the evokeds derivative directory for one subject/session."""
    return derivative_path(
        config,
        subject=subject,
        session=session,
        kind="evokeds",
        suffix="dummy",
    ).parent


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



def configured_conditions(config: PipelineConfig) -> dict[str, ConditionDefinition]:
    """Return project-specific condition definitions from config.

    Most projects do not need this and can keep using trigger labels directly.
    Project-specific derived selections can be defined once under
    ``conditions.definitions`` in the project config and reused here.
    """
    return condition_definitions_from_config(config)


def condition_indices(
    epochs: Epochs,
    condition: ConditionDefinition,
) -> list[int]:
    """Return epoch indices for a condition definition.

    Supported condition definitions:

    - str: pandas query applied to epochs.metadata, e.g.
      ``"non_diatonic == 1"``
    - list/tuple/set of int: MNE event codes selected from epochs.events[:, 2].
    """
    return condition_indices_from_mne_epochs(epochs, condition)


def make_evoked_for_condition(
    epochs: Epochs,
    *,
    condition_name: str,
    condition: ConditionDefinition,
    copy_bads_from_epochs: bool = True,
) -> tuple[Evoked | None, EvokedConditionResult]:
    """Create one Evoked object from epochs for a condition definition."""
    indices = condition_indices(epochs, condition)

    if not indices:
        return None, EvokedConditionResult(
            condition=condition_name,
            path="",
            status="no_epochs",
            n_epochs=0,
            desc=sanitize_bids_label(condition_name),
            message="No epochs matched this condition.",
        )

    selected_epochs = epochs[indices]
    evoked = selected_epochs.average()
    evoked.comment = condition_name

    if copy_bads_from_epochs:
        evoked.info["bads"] = [
            ch_name
            for ch_name in epochs.info["bads"]
            if ch_name in evoked.info["ch_names"]
        ]

    return evoked, EvokedConditionResult(
        condition=condition_name,
        path="",
        status="computed",
        n_epochs=len(selected_epochs),
        desc=sanitize_bids_label(condition_name),
    )


def write_evoked_for_condition(
    config: PipelineConfig,
    epochs: Epochs,
    *,
    subject: str,
    condition_name: str,
    condition: ConditionDefinition,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingOutputPolicy = "skip",
) -> EvokedConditionResult:
    """Create and write one condition-specific evoked file."""
    output_path = make_evoked_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        condition=condition_name,
    )

    if output_path.exists() and on_existing == "skip":
        return EvokedConditionResult(
            condition=condition_name,
            path=str(output_path),
            status="skipped_existing",
            n_epochs=0,
            desc=sanitize_bids_label(condition_name),
            message="Evoked file already exists.",
        )

    evoked, result = make_evoked_for_condition(
        epochs,
        condition_name=condition_name,
        condition=condition,
    )

    if evoked is None:
        return EvokedConditionResult(
            condition=result.condition,
            path=str(output_path),
            status=result.status,
            n_epochs=result.n_epochs,
            desc=result.desc,
            message=result.message,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mne.write_evokeds(
        output_path,
        [evoked],
        overwrite=on_existing == "overwrite",
        verbose="error",
    )

    return EvokedConditionResult(
        condition=condition_name,
        path=str(output_path),
        status="written",
        n_epochs=result.n_epochs,
        desc=sanitize_bids_label(condition_name),
    )


def write_evokeds_for_recording(
    config: PipelineConfig,
    *,
    subject: str,
    conditions: dict[str, ConditionDefinition],
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingOutputPolicy = "skip",
) -> EvokedResult:
    """Create and write one evoked file per condition for one recording."""
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    output_directory = make_evokeds_directory(
        config,
        subject=subject,
        session=session,
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
            directory=str(output_directory),
            status=epochs_result.status,
            message=epochs_result.message,
        )

    condition_results: list[EvokedConditionResult] = []

    for condition_name, condition in conditions.items():
        condition_results.append(
            write_evoked_for_condition(
                config,
                epochs_result.epochs,
                subject=subject,
                session=session,
                task=task,
                run=run,
                condition_name=condition_name,
                condition=condition,
                on_existing=on_existing,
            )
        )

    written_or_existing = [
        result
        for result in condition_results
        if result.status in {"written", "skipped_existing"}
    ]

    written = [
        result
        for result in condition_results
        if result.status == "written"
    ]

    if not written_or_existing:
        return EvokedResult(
            directory=str(output_directory),
            status="no_evokeds",
            n_evokeds=0,
            conditions=[],
            condition_results=condition_results,
            message="No evokeds were created because no conditions matched epochs.",
        )

    if len(written_or_existing) == len(condition_results):
        status = "written" if written else "skipped_existing"
    else:
        status = "partial"

    return EvokedResult(
        directory=str(output_directory),
        status=status,
        n_evokeds=len(written_or_existing),
        conditions=[result.condition for result in written_or_existing],
        condition_results=condition_results,
    )


def write_evokeds_for_recordings(
    config: PipelineConfig,
    recordings: list[dict[str, str | None]],
    *,
    conditions: dict[str, ConditionDefinition],
    on_existing: ExistingOutputPolicy = "skip",
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
        )
        for recording in recordings
    ]
