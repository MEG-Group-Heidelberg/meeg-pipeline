from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import mne
from mne_bids import write_raw_bids

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.sourcedata import (
    EmptyRoomSourceRecording,
    SourceRecording,
    make_empty_room_target_bids_path,
    make_target_bids_path,
)


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
    """Convert multiple source recordings to raw BIDS.

    If multiple source recordings map to the same target BIDS path, none of the
    colliding recordings are converted. This prevents accidental overwrites when
    sourcedata session folders are ignored or when run folders are missing.
    """
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    target_to_recordings: dict[str, list[SourceRecording]] = defaultdict(list)

    for recording in recordings:
        target_to_recordings[str(make_target_bids_path(config, recording).fpath)].append(
            recording
        )

    results: list[ConversionResult] = []

    for recording in recordings:
        target_path = str(make_target_bids_path(config, recording).fpath)
        colliding_recordings = target_to_recordings[target_path]

        if len(colliding_recordings) > 1:
            results.append(
                ConversionResult(
                    source_path=str(recording.source_path),
                    target_path=target_path,
                    status="duplicate_target",
                    message=(
                        "Multiple source recordings map to the same BIDS "
                        "target. Use sourcedata.sessions: 'include', add "
                        "run-* folders, or remove duplicate inputs."
                    ),
                )
            )
            continue

        results.append(
            convert_source_recording_to_bids(
                config,
                recording,
                overwrite=on_existing == "overwrite",
            )
        )

    return results


def convert_empty_room_source_recording_to_bids(
    config: PipelineConfig,
    recording: EmptyRoomSourceRecording,
    *,
    overwrite: bool = False,
) -> ConversionResult:
    """Convert one empty-room source FIF recording to raw BIDS.

    Empty-room recordings are converted to a dedicated BIDS subject such as
    ``sub-emptyroom`` and do not require events.tsv files.
    """
    target_bids_path = make_empty_room_target_bids_path(config, recording)

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
            message="Empty-room source FIF file does not exist.",
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


def convert_empty_room_source_recordings_to_bids(
    config: PipelineConfig,
    recordings: list[EmptyRoomSourceRecording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
) -> list[ConversionResult]:
    """Convert multiple empty-room source recordings to raw BIDS."""
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    target_to_recordings: dict[str, list[EmptyRoomSourceRecording]] = defaultdict(list)
    for recording in recordings:
        target_to_recordings[
            str(make_empty_room_target_bids_path(config, recording).fpath)
        ].append(recording)

    results: list[ConversionResult] = []
    for recording in recordings:
        target_path = str(make_empty_room_target_bids_path(config, recording).fpath)
        colliding_recordings = target_to_recordings[target_path]

        if len(colliding_recordings) > 1:
            results.append(
                ConversionResult(
                    source_path=str(recording.source_path),
                    target_path=target_path,
                    status="duplicate_target",
                    message=(
                        "Multiple empty-room source recordings map to the same "
                        "BIDS target. Add run-* folders or filenames."
                    ),
                )
            )
            continue

        results.append(
            convert_empty_room_source_recording_to_bids(
                config,
                recording,
                overwrite=on_existing == "overwrite",
            )
        )

    return results


def conversion_results_to_dataframe(results: list[ConversionResult]):
    """Convert conversion results to a notebook-friendly table."""
    import pandas as pd

    return pd.DataFrame([result.__dict__ for result in results])

