from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import mne
from mne_bids import write_raw_bids

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.io import ensure_output_does_not_exist
from meeg_pipeline.sourcedata import SourceRecording, make_target_bids_path


ExistingOutputPolicy = Literal["error", "skip", "overwrite"]


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
    """Convert one source FIF recording to raw BIDS using MNE-BIDS.

    This function is strict: if the output exists and overwrite=False, it raises
    FileExistsError. For notebook/batch workflows, use
    convert_source_recordings_to_bids(..., on_existing="skip").
    """
    target_bids_path = make_target_bids_path(config, recording)

    ensure_output_does_not_exist(target_bids_path.fpath, overwrite=overwrite)

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
        status="converted",
    )


def convert_source_recordings_to_bids(
    config: PipelineConfig,
    recordings: list[SourceRecording],
    *,
    on_existing: ExistingOutputPolicy = "error",
) -> list[ConversionResult]:
    """Convert multiple source recordings to raw BIDS.

    Parameters
    ----------
    config
        Pipeline config.
    recordings
        Source recordings discovered from sourcedata/.
    on_existing
        What to do if the target raw BIDS file already exists.

        - "error": raise FileExistsError
        - "skip": keep existing output and return status "skipped_existing"
        - "overwrite": overwrite existing output
    """
    if on_existing not in {"error", "skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'error', 'skip', or 'overwrite'."
        )

    results: list[ConversionResult] = []

    for recording in recordings:
        target_bids_path = make_target_bids_path(config, recording)
        target_path = target_bids_path.fpath

        if target_path.exists() and on_existing == "skip":
            results.append(
                ConversionResult(
                    source_path=str(recording.source_path),
                    target_path=str(target_path),
                    status="skipped_existing",
                    message="Target already exists.",
                )
            )
            continue

        result = convert_source_recording_to_bids(
            config,
            recording,
            overwrite=on_existing == "overwrite",
        )
        results.append(result)

    return results