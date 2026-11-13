from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np
import pandas as pd

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.paths import derivative_path
from meeg_pipeline.workflow import Recording, raw_events_path, read_raw_events


ExistingOutputPolicy = Literal["skip", "overwrite"]
StimulusLogMatch = Literal["code", "order"]


@dataclass(frozen=True)
class AnalysisEventsWriteResult:
    events_path: str
    sidecar_path: str
    status: str
    n_events: int = 0
    message: str = ""


@dataclass(frozen=True)
class StimulusLogJoinQC:
    n_triggers: int
    n_log: int
    n_mismatches: int
    # Fit trigger_onset = intercept_s + slope * stimulus_onset.
    slope: float | None = None
    intercept_s: float | None = None
    residual_sd_s: float | None = None
    max_abs_residual_s: float | None = None


def join_stimulus_log(
    trigger_events: pd.DataFrame,
    stimulus_log: pd.DataFrame,
    *,
    match: StimulusLogMatch = "code",
    code_column: str = "value",
    onset_column: str = "onset",
) -> tuple[pd.DataFrame, StimulusLogJoinQC]:
    """Join trigger events with a stimulus log, row by row in presentation order.

    With ``match="code"``, the trigger ``value`` must equal ``code_column`` of
    the log in every row. With ``match="order"``, only the counts must agree.
    Any disagreement raises instead of being repaired.

    Log columns that already exist in ``trigger_events`` get the suffix
    ``_stim``. The returned QC fits the trigger onsets against the log onsets;
    the slope is the clock ratio and the residuals show jitter and drift.
    """
    if match not in {"code", "order"}:
        raise ValueError(f"Invalid match value: {match!r}. Use 'code' or 'order'.")

    if len(trigger_events) != len(stimulus_log):
        raise ValueError(
            f"Trigger events ({len(trigger_events)}) and stimulus log "
            f"({len(stimulus_log)}) differ in length."
        )

    trigger_events = trigger_events.reset_index(drop=True)
    stimulus_log = stimulus_log.reset_index(drop=True)

    n_mismatches = 0
    if match == "code":
        mismatch = trigger_events["value"].to_numpy() != stimulus_log[code_column].to_numpy()
        n_mismatches = int(mismatch.sum())
        if n_mismatches:
            first = int(np.flatnonzero(mismatch)[0])
            raise ValueError(
                f"{n_mismatches} trigger values differ from the stimulus log "
                f"column {code_column!r}; first at row {first} "
                f"(trigger {trigger_events['value'].iloc[first]}, "
                f"log {stimulus_log[code_column].iloc[first]})."
            )

    renamed = {
        column: f"{column}_stim"
        for column in stimulus_log.columns
        if column in trigger_events.columns
    }
    joined = pd.concat([trigger_events, stimulus_log.rename(columns=renamed)], axis=1)

    qc = StimulusLogJoinQC(
        n_triggers=len(trigger_events),
        n_log=len(stimulus_log),
        n_mismatches=n_mismatches,
    )

    if onset_column in stimulus_log.columns and len(stimulus_log) > 1:
        stimulus_onsets = stimulus_log[onset_column].to_numpy(dtype=float)
        trigger_onsets = trigger_events["onset"].to_numpy(dtype=float)
        slope, intercept = np.polyfit(stimulus_onsets, trigger_onsets, 1)
        residuals = trigger_onsets - (intercept + slope * stimulus_onsets)
        qc = StimulusLogJoinQC(
            n_triggers=qc.n_triggers,
            n_log=qc.n_log,
            n_mismatches=qc.n_mismatches,
            slope=float(slope),
            intercept_s=float(intercept),
            residual_sd_s=float(residuals.std(ddof=1)),
            max_abs_residual_s=float(np.abs(residuals).max()),
        )

    return joined, qc


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
    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="events",
        suffix=f"desc-{desc}_events.tsv",
    )


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

    Unknown columns are retained with a generic description so project-specific
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
    """Write derivative analysis events TSV plus JSON sidecar."""
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


@dataclass(frozen=True)
class StimulusLogJoinResult:
    subject: str
    session: str | None
    task: str | None
    run: str | None
    status: str
    n_events: int = 0
    slope: float | None = None
    residual_sd_s: float | None = None
    max_abs_residual_s: float | None = None
    stimulus_log_path: str = ""
    events_path: str = ""
    message: str = ""


def stimulus_log_path(config: PipelineConfig, recording: Recording) -> Path | None:
    """Return the stimulus-log path of one recording, or None if none is configured."""
    template = config.events.stimulus_log.path
    if template is None:
        return None

    return Path(
        template.format(
            subject=recording["subject"],
            session=recording.get("session") or "",
            task=recording.get("task") or "",
            run=recording.get("run") or "",
        )
    )


def join_stimulus_log_for_recordings(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
) -> list[StimulusLogJoinResult]:
    """Join the trigger events of each recording with its stimulus log.

    Writes ``desc-<events.stimulus_log.desc>_events.tsv`` next to the other
    analysis events. Missing inputs and mismatches are returned as status rows.
    """
    settings = config.events.stimulus_log
    results: list[StimulusLogJoinResult] = []

    for recording in recordings:
        entities = {
            "subject": str(recording["subject"]),
            "session": recording.get("session"),
            "task": recording.get("task"),
            "run": recording.get("run"),
        }
        log_path = stimulus_log_path(config, recording)
        events_path = make_analysis_events_path(config, **entities, desc=settings.desc)

        def result(status: str, message: str = "", **fields: Any) -> StimulusLogJoinResult:
            return StimulusLogJoinResult(
                **entities,
                status=status,
                stimulus_log_path=str(log_path or ""),
                events_path=str(events_path),
                message=message,
                **fields,
            )

        if log_path is None:
            results.append(result("missing_config", "events.stimulus_log.path is not set."))
            continue

        trigger_events = read_raw_events(config, recording)
        if trigger_events is None:
            results.append(result("missing_events_tsv", "Raw BIDS events.tsv does not exist."))
            continue

        if not log_path.exists():
            results.append(result("missing_stimulus_log", "Stimulus log does not exist."))
            continue

        stimulus_log = pd.read_csv(log_path, sep="," if log_path.suffix == ".csv" else "\t")

        try:
            joined, qc = join_stimulus_log(
                trigger_events,
                stimulus_log,
                match=settings.match,
                code_column=settings.code_column,
                onset_column=settings.onset_column,
            )
        except ValueError as exc:
            results.append(result("mismatch", str(exc)))
            continue

        write_result = write_analysis_events(
            config,
            joined,
            **entities,
            desc=settings.desc,
            on_existing=on_existing,
            sidecar_description=(
                f"Trigger events joined with the stimulus log {log_path.name}."
            ),
            source_events=str(raw_events_path(config, recording)),
        )
        results.append(
            result(
                write_result.status,
                write_result.message,
                n_events=len(joined),
                slope=qc.slope,
                residual_sd_s=qc.residual_sd_s,
                max_abs_residual_s=qc.max_abs_residual_s,
            )
        )

    return results


def stimulus_log_join_results_to_dataframe(
    results: Iterable[StimulusLogJoinResult],
) -> pd.DataFrame:
    """Convert stimulus-log join results to a status table."""
    return pd.DataFrame([result.__dict__ for result in results])
