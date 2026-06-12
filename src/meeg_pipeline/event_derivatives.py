from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from meeg_pipeline.config import PipelineConfig


ExistingOutputPolicy = Literal["skip", "overwrite"]


@dataclass(frozen=True)
class AnalysisEventsWriteResult:
    events_path: str
    sidecar_path: str
    status: str
    n_events: int = 0
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


def make_analysis_events_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "analysis",
) -> Path:
    """Create derivative path for project-specific analysis events TSV."""
    parts = _recording_parts(
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    basename = "_".join(parts + [f"desc-{desc}", "events.tsv"])

    return _derivative_directory(
        config,
        subject=subject,
        session=session,
    ) / basename


def make_analysis_events_sidecar_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "analysis",
) -> Path:
    """Create derivative path for project-specific analysis events JSON sidecar."""
    events_path = make_analysis_events_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=desc,
    )

    return events_path.with_suffix(".json")


def default_analysis_events_sidecar(
    *,
    description: str = (
        "Project-specific analysis events derived from acquisition-level "
        "trigger anchors and optional stimulus metadata."
    ),
    source_events: str = (
        "Raw BIDS events.tsv or another trigger-derived events table."
    ),
    additional_columns: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a generic JSON sidecar for derivative analysis events.

    The returned structure follows the BIDS style of describing tabular columns.
    Project-specific columns can be added or overridden via additional_columns.
    """
    columns: dict[str, dict[str, Any]] = {
        "onset": {
            "Description": "Event onset in seconds relative to the beginning of the recording.",
            "Units": "s",
        },
        "duration": {
            "Description": "Event duration in seconds.",
            "Units": "s",
        },
        "trial_type": {
            "Description": "Analysis event category used for epoching or later condition definitions.",
        },
        "value": {
            "Description": "Integer event value. For derived analysis events this may correspond to a note ID or another project-specific event identifier.",
        },
        "sample": {
            "Description": "Event sample index in the raw data coordinate system.",
        },
        "anchor_sample": {
            "Description": "Sample index of the trigger anchor from which the analysis event was derived.",
        },
        "anchor_index": {
            "Description": "Index of the trigger anchor used for deriving this event.",
        },
        "anchor_trial_type": {
            "Description": "Trial type of the trigger anchor used for deriving this event.",
        },
        "anchor_value": {
            "Description": "Integer value of the trigger anchor used for deriving this event.",
        },
        "note_id": {
            "Description": "Project-specific note identifier from the stimulus metadata table.",
        },
        "note_index": {
            "Description": "Position of the note within a block or sequence.",
        },
        "block_index": {
            "Description": "Index of the block or sequence to which the note belongs.",
        },
        "position_in_block": {
            "Description": "Position of the note relative to the corresponding trigger anchor.",
        },
        "note_degree": {
            "Description": "Musical note degree from the stimulus metadata table.",
        },
        "key_signature": {
            "Description": "Key signature identifier from the stimulus metadata table.",
        },
        "scale_degree": {
            "Description": "Scale degree of the note within the current key.",
        },
        "non_diatonic": {
            "Description": "Project-specific non-diatonic note category.",
        },
        "steps": {
            "Description": "Step size or direction value from the stimulus metadata table.",
        },
        "direction_change": {
            "Description": "Direction-change category from the stimulus metadata table.",
        },
        "circle_of_fifths": {
            "Description": "Project-specific circle-of-fifths jump measure.",
        },
        "certainty": {
            "Description": "Project-specific certainty rating or category.",
        },
        "part_of_chord": {
            "Description": "Indicator whether the note is part of a chord, if available.",
        },
        "diatonic": {
            "Description": "Indicator whether the note is diatonic, if available.",
        },
        "new_information": {
            "Description": "Project-specific new-information flag or category, if available.",
        },
        "selection_labels": {
            "Description": "Comma-separated labels of event-selection rules that matched this event.",
        },
    }

    if additional_columns is not None:
        columns.update(additional_columns)

    return {
        "Description": description,
        "Sources": [source_events],
        "GeneratedBy": [
            {
                "Name": "meeg-pipeline",
                "Description": "Project-specific event derivation workflow.",
            }
        ],
        "Columns": columns,
    }


def sidecar_for_events_table(
    events: pd.DataFrame,
    *,
    description: str | None = None,
    source_events: str | None = None,
    additional_columns: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a sidecar and keep only column descriptions present in events.

    Unknown columns are retained with a generic description, so project-specific
    metadata is not silently undocumented.
    """
    sidecar = default_analysis_events_sidecar(
        description=description
        or (
            "Project-specific analysis events derived from acquisition-level "
            "trigger anchors and optional stimulus metadata."
        ),
        source_events=source_events
        or "Raw BIDS events.tsv or another trigger-derived events table.",
        additional_columns=additional_columns,
    )

    known_columns = sidecar["Columns"]
    filtered_columns: dict[str, dict[str, Any]] = {}

    for column in events.columns:
        if column in known_columns:
            filtered_columns[column] = known_columns[column]
        else:
            filtered_columns[column] = {
                "Description": (
                    "Project-specific analysis-event metadata column. "
                    "Please refine this description for the concrete project."
                )
            }

    sidecar["Columns"] = filtered_columns

    return sidecar


def write_analysis_events(
    config: PipelineConfig,
    events: pd.DataFrame,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "analysis",
    on_existing: ExistingOutputPolicy = "skip",
    sidecar: dict[str, Any] | None = None,
    sidecar_description: str | None = None,
    source_events: str | None = None,
    additional_columns: dict[str, dict[str, Any]] | None = None,
) -> AnalysisEventsWriteResult:
    """Write derivative analysis events TSV plus JSON sidecar.

    Missing or existing outputs are reported as status values to support
    notebook-friendly batch workflows.
    """
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    events_path = make_analysis_events_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=desc,
    )
    sidecar_path = make_analysis_events_sidecar_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=desc,
    )

    if events_path.exists() and sidecar_path.exists() and on_existing == "skip":
        return AnalysisEventsWriteResult(
            events_path=str(events_path),
            sidecar_path=str(sidecar_path),
            status="skipped_existing",
            n_events=0,
            message="Analysis events TSV and JSON sidecar already exist.",
        )

    if sidecar is None:
        sidecar = sidecar_for_events_table(
            events,
            description=sidecar_description,
            source_events=source_events,
            additional_columns=additional_columns,
        )

    events_path.parent.mkdir(parents=True, exist_ok=True)

    events.to_csv(events_path, sep="\t", index=False)
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return AnalysisEventsWriteResult(
        events_path=str(events_path),
        sidecar_path=str(sidecar_path),
        status="written",
        n_events=len(events),
    )
