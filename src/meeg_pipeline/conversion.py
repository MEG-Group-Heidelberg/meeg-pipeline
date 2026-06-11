from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import mne
from mne_bids import write_raw_bids

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.sourcedata import SourceRecording, make_target_bids_path


ExistingOutputPolicy = Literal["skip", "overwrite"]


@dataclass(frozen=True)
class ConversionResult:
    source_path: str
    target_path: str
    status: str
    message: str = ""


def convert_source_recording_to_bids(
    config: PipelineConfig,
    recording: SourceRecording,
    *,
    overwrite: bool = False,
) -> ConversionResult:
    """Convert one source FIF recording to raw BIDS.

    Existing targets and missing source files are returned as statuses rather
    than exceptions.
    """
    target_bids_path = make_target_bids_path(config, recording)

    if target_bids_path.fpath.exists() and not overwrite:
        return ConversionResult(
            source_path=str(recording.source_path),
            target_path=str(target_bids_path.fpath),
            status="skipped_existing",
            message="Target already exists.",
        )

    if not recording.source_path.exists():
        return ConversionResult(
            source_path=str(recording.source_path),
            target_path=str(target_bids_path.fpath),
            status="missing_input",
            message="Source FIF file does not exist.",
        )

    raw = mne.io.read_raw_fif(
        recording.source_path,
        preload=False,
        verbose="error",
    )

    write_raw_bids(
        raw=raw,
        bids_path=target_bids_path,
        overwrite=overwrite,
        verbose="error",
    )

    return ConversionResult(
        source_path=str(recording.source_path),
        target_path=str(target_bids_path.fpath),
        status="written",
    )


def convert_source_recordings_to_bids(
    config: PipelineConfig,
    recordings: list[SourceRecording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
) -> list[ConversionResult]:
    """Convert multiple source recordings to raw BIDS."""
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    return [
        convert_source_recording_to_bids(
            config,
            recording,
            overwrite=on_existing == "overwrite",
        )
        for recording in recordings
    ]
