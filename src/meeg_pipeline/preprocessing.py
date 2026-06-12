from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mne
from mne.io import BaseRaw

from meeg_pipeline.bids import read_raw_bids_recording_if_exists
from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.paths import derivative_path
from meeg_pipeline.qc import apply_bad_channels


ExistingOutputPolicy = Literal["skip", "overwrite"]


@dataclass(frozen=True)
class PreprocessingResult:
    output_path: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class LoadRawResult:
    raw: BaseRaw | None
    path: str
    status: str
    message: str = ""


def make_filtered_raw_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create derivative path for filtered continuous raw data."""
    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="preprocessing",
        suffix="desc-filtered_meg.fif",
    )

def load_filtered_raw(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    preload: bool = False,
) -> LoadRawResult:
    """Load a filtered raw derivative if it exists."""
    path = make_filtered_raw_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return LoadRawResult(
            raw=None,
            path=str(path),
            status="missing_input",
            message="Filtered raw derivative does not exist.",
        )

    raw = mne.io.read_raw_fif(
        path,
        preload=preload,
        verbose="error",
    )

    return LoadRawResult(
        raw=raw,
        path=str(path),
        status="loaded",
    )


def filter_raw(
    raw: BaseRaw,
    config: PipelineConfig,
    *,
    verbose: bool | str | int | None = True,    
) -> BaseRaw:
    """Apply configured notch and bandpass filters to a Raw object."""
    filtered = raw.copy().load_data()
    filtering = config.preprocessing.filtering

    if filtering.notch_freqs:
        filtered.notch_filter(
            freqs=list(filtering.notch_freqs),
            picks="meg",
            method=filtering.method,
            verbose=verbose,
        )

    if filtering.l_freq is not None or filtering.h_freq is not None:
        filtered.filter(
            l_freq=filtering.l_freq,
            h_freq=filtering.h_freq,
            picks="meg",
            method=filtering.method,
            verbose=verbose,
        )

    return filtered


def write_filtered_raw_for_recording(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    verbose: bool | str | int | None = True,
) -> PreprocessingResult:
    """Load raw BIDS, apply bad channels, filter, and write derivative."""
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    output_path = make_filtered_raw_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if output_path.exists() and on_existing == "skip":
        return PreprocessingResult(
            output_path=str(output_path),
            status="skipped_existing",
            message="Target already exists.",
        )

    raw_result = read_raw_bids_recording_if_exists(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        preload=False,
    )

    if raw_result.raw is None:
        return PreprocessingResult(
            output_path=str(output_path),
            status="missing_input",
            message=raw_result.message,
        )

    apply_bad_channels(
        raw_result.raw,
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    filtered = filter_raw(
        raw_result.raw,
        config,
        verbose=verbose,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtered.save(output_path, overwrite=on_existing == "overwrite")

    return PreprocessingResult(
        output_path=str(output_path),
        status="written",
    )


def write_filtered_raw_for_recordings(
    config: PipelineConfig,
    recordings: list[dict[str, str | None]],
    *,
    on_existing: ExistingOutputPolicy = "skip",
) -> list[PreprocessingResult]:
    """Write filtered raw derivatives for multiple recordings."""
    return [
        write_filtered_raw_for_recording(
            config,
            subject=recording["subject"],
            session=recording.get("session"),
            task=recording.get("task"),
            run=recording.get("run"),
            on_existing=on_existing,
        )
        for recording in recordings
    ]


# Backward-compatible alias.
load_filtered_raw_if_exists = load_filtered_raw
