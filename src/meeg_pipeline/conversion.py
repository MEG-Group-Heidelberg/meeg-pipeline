from __future__ import annotations

from dataclasses import dataclass

import mne
from mne_bids import write_raw_bids

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.io import ensure_output_does_not_exist
from meeg_pipeline.sourcedata import SourceRecording, make_target_bids_path


@dataclass(frozen=True)
class ConversionResult:
    source_path: str
    target_path: str
    status: str


def convert_source_recording_to_bids(
    config: PipelineConfig,
    recording: SourceRecording,
    *,
    overwrite: bool = False,
) -> ConversionResult:
    """Convert one source FIF recording to raw BIDS using MNE-BIDS."""
    target_bids_path = make_target_bids_path(config, recording)

    ensure_output_does_not_exist(target_bids_path.fpath, overwrite=overwrite)

    raw = mne.io.read_raw_fif(
        recording.source_path,
        preload=False,
        verbose=True,
    )

    write_raw_bids(
        raw=raw,
        bids_path=target_bids_path,
        overwrite=overwrite,
        verbose=True,
    )

    return ConversionResult(
        source_path=str(recording.source_path),
        target_path=str(target_bids_path.fpath),
        status="converted",
    )