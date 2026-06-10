from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from itertools import combinations
from pathlib import Path

import mne
import numpy as np
import pandas as pd
from mne.io import BaseRaw

from meeg_pipeline.config import PipelineConfig


@dataclass(frozen=True)
class BinaryChannelEventConfig:
    """Configuration for binary event extraction across multiple stim channels.

    This is useful for lab setups where event IDs are encoded as binary
    combinations across several digital trigger channels.

    Example with six channels:
        STI 001 -> 1
        STI 002 -> 2
        STI 003 -> 4
        STI 004 -> 8
        STI 005 -> 16
        STI 006 -> 32

    If STI 001 and STI 003 are active at the same event onset, the resulting
    event value is 1 + 4 = 5.
    """

    stim_channels: tuple[str, ...]
    min_duration: float = 0.0
    shortest_event: int = 1
    min_gap: int = 0
    adjust_timeline_by_msec: float = 0.0
    tolerance_samples: int = 1
    mute_bad_annotations: bool = True


@dataclass(frozen=True)
class EventSummary:
    n_events: int
    unique_ids: list[int]
    min_sample_distance: int | None
    max_sample_distance: int | None
    first_events: list[list[int]]


def _validate_stim_channels(raw: BaseRaw, stim_channels: tuple[str, ...]) -> None:
    missing = [ch for ch in stim_channels if ch not in raw.ch_names]
    if missing:
        raise ValueError(
            "The following stim channels were not found in raw.ch_names: "
            f"{missing}"
        )


def _mute_bad_annotation_spans(raw: BaseRaw, picks: np.ndarray) -> None:
    """Set stim channels to zero during BAD annotations.

    This operates on a copy in find_binary_channel_events(), so the original Raw
    object is not modified.
    """
    if raw.annotations is None:
        return

    for annotation in raw.annotations:
        if "BAD" not in annotation["description"]:
            continue

        start = raw.time_as_index(annotation["onset"])[0]
        stop = raw.time_as_index(annotation["onset"] + annotation["duration"])[0]
        raw._data[picks, start:stop] = 0.0


def _drop_events_too_close_within_channel(
    samples: np.ndarray,
    *,
    min_distance_samples: int,
) -> np.ndarray:
    """Drop repeated events within one channel that are too close together."""
    if len(samples) < 2:
        return samples

    keep = np.ones(len(samples), dtype=bool)
    too_close = np.where(np.diff(samples) <= min_distance_samples)[0]

    # Drop the first of each too-close pair, matching the older behavior.
    keep[too_close] = False

    return samples[keep]


def _samples_with_tolerance(samples: np.ndarray, tolerance_samples: int) -> np.ndarray:
    """Expand event samples by +/- tolerance."""
    if tolerance_samples < 0:
        raise ValueError("tolerance_samples must be >= 0")

    if len(samples) == 0:
        return np.array([], dtype=np.int64)

    offsets = np.arange(-tolerance_samples, tolerance_samples + 1)
    expanded = samples[:, np.newaxis] + offsets[np.newaxis, :]
    return np.unique(expanded.ravel()).astype(np.int64)


def _already_has_nearby_event(
    events: list[tuple[int, int]],
    sample: int,
    *,
    tolerance_samples: int,
) -> bool:
    return any(abs(existing_sample - sample) <= tolerance_samples for existing_sample, _ in events)


def find_binary_channel_events(
    raw: BaseRaw,
    config: BinaryChannelEventConfig,
) -> np.ndarray:
    """Find binary-coded events across multiple stim channels.

    Parameters
    ----------
    raw
        MNE Raw object.
    config
        Event extraction configuration.

    Returns
    -------
    events
        MNE-style events array of shape (n_events, 3), with columns:
        sample, previous_value, event_id.
    """
    _validate_stim_channels(raw, config.stim_channels)

    work_raw = raw.copy()

    if config.mute_bad_annotations:
        work_raw.load_data()
        picks = mne.pick_channels(work_raw.ch_names, list(config.stim_channels))
        _mute_bad_annotation_spans(work_raw, picks)

    events_per_channel: list[np.ndarray] = []
    tolerated_events_per_channel: list[np.ndarray] = []

    for stim_channel in config.stim_channels:
        channel_events = mne.find_events(
            work_raw,
            min_duration=config.min_duration,
            shortest_event=config.shortest_event,
            stim_channel=[stim_channel],
            verbose=False,
        )

        samples = channel_events[:, 0].astype(np.int64)
        samples = _drop_events_too_close_within_channel(
            samples,
            min_distance_samples=1,
        )

        events_per_channel.append(samples)
        tolerated_events_per_channel.append(
            _samples_with_tolerance(samples, config.tolerance_samples)
        )

    found_events: list[tuple[int, int]] = []
    n_channels = len(config.stim_channels)

    # Start with combinations using all channels, then fewer channels.
    # This gives priority to larger binary combinations.
    for combination_size in range(n_channels, 1, -1):
        for channel_indices in combinations(range(n_channels), combination_size):
            equal_samples = reduce(
                np.intersect1d,
                (tolerated_events_per_channel[idx] for idx in channel_indices),
            )

            if len(equal_samples) == 0:
                continue

            equal_samples = _drop_events_too_close_within_channel(
                equal_samples,
                min_distance_samples=1,
            )

            event_id = int(sum(2**idx for idx in channel_indices))

            for sample in equal_samples:
                sample = int(sample)

                if not _already_has_nearby_event(
                    found_events,
                    sample,
                    tolerance_samples=config.tolerance_samples,
                ):
                    found_events.append((sample, event_id))

    # Add single-channel events.
    for channel_index, samples in enumerate(events_per_channel):
        event_id = int(2**channel_index)

        for sample in samples:
            sample = int(sample)

            if not _already_has_nearby_event(
                found_events,
                sample,
                tolerance_samples=config.tolerance_samples,
            ):
                found_events.append((sample, event_id))

    if not found_events:
        return np.empty((0, 3), dtype=np.int32)

    found_events = sorted(found_events, key=lambda item: item[0])

    events = np.array(
        [[sample, 0, event_id] for sample, event_id in found_events],
        dtype=np.int32,
    )

    if config.adjust_timeline_by_msec != 0:
        sample_shift = int(
            round(config.adjust_timeline_by_msec * 1e-3 * raw.info["sfreq"])
        )
        events[:, 0] += sample_shift

    if config.min_gap > 0 and len(events) > 1:
        kept = [events[0]]
        last_sample = events[0, 0]

        for event in events[1:]:
            if event[0] - last_sample >= config.min_gap:
                kept.append(event)
                last_sample = event[0]

        events = np.array(kept, dtype=np.int32)

    return events


def binary_event_config_from_pipeline_config(
    config: PipelineConfig,
) -> BinaryChannelEventConfig:
    """Create a binary-channel event config from the project config."""
    extraction = config.events.extraction

    if extraction.method != "binary_channels":
        raise ValueError(
            f"Unsupported event extraction method for this function: "
            f"{extraction.method}"
        )

    return BinaryChannelEventConfig(
        stim_channels=extraction.stim_channels,
        min_duration=extraction.min_duration,
        shortest_event=extraction.shortest_event,
        min_gap=extraction.min_gap,
        adjust_timeline_by_msec=extraction.adjust_timeline_by_msec,
        tolerance_samples=extraction.tolerance_samples,
        mute_bad_annotations=extraction.mute_bad_annotations,
    )


def summarize_events(events: np.ndarray, *, n_first: int = 10) -> EventSummary:
    """Summarize an MNE-style events array."""
    if len(events) == 0:
        return EventSummary(
            n_events=0,
            unique_ids=[],
            min_sample_distance=None,
            max_sample_distance=None,
            first_events=[],
        )

    sample_diffs = np.diff(events[:, 0])

    return EventSummary(
        n_events=int(len(events)),
        unique_ids=[int(value) for value in np.unique(events[:, 2])],
        min_sample_distance=int(sample_diffs.min()) if len(sample_diffs) else None,
        max_sample_distance=int(sample_diffs.max()) if len(sample_diffs) else None,
        first_events=events[:n_first].astype(int).tolist(),
    )


def event_summary_to_dataframe(summary: EventSummary) -> pd.DataFrame:
    """Convert an EventSummary to a notebook-friendly DataFrame."""
    return pd.DataFrame(
        [
            {
                "n_events": summary.n_events,
                "unique_ids": ", ".join(str(value) for value in summary.unique_ids),
                "min_sample_distance": summary.min_sample_distance,
                "max_sample_distance": summary.max_sample_distance,
            }
        ]
    )


def first_events_to_dataframe(summary: EventSummary) -> pd.DataFrame:
    """Convert the first events from an EventSummary to a DataFrame."""
    return pd.DataFrame(
        summary.first_events,
        columns=["sample", "previous_value", "event_id"],
    )


def print_event_summary(summary: EventSummary) -> None:
    """Print a simple event summary."""
    print(f"Events: {summary.n_events}")
    print(f"Unique IDs: {summary.unique_ids}")
    print(f"Min. sample distance: {summary.min_sample_distance}")
    print(f"Max. sample distance: {summary.max_sample_distance}")
    print(f"First events: {summary.first_events}")


def events_to_dataframe(
    events: np.ndarray,
    raw: BaseRaw,
    *,
    trial_type_prefix: str = "trigger",
) -> pd.DataFrame:
    """Convert an MNE-style events array to a BIDS-like events table.

    The BIDS-required columns are:
    - onset
    - duration
    - trial_type

    Additional useful columns:
    - value
    - sample
    """
    if len(events) == 0:
        return pd.DataFrame(
            columns=["onset", "duration", "trial_type", "value", "sample"]
        )

    first_samp = int(raw.first_samp)
    sfreq = float(raw.info["sfreq"])

    samples = events[:, 0].astype(int)
    values = events[:, 2].astype(int)
    onset = (samples - first_samp) / sfreq

    return pd.DataFrame(
        {
            "onset": onset,
            "duration": 0.0,
            "trial_type": [f"{trial_type_prefix}_{value}" for value in values],
            "value": values,
            "sample": samples,
        }
    )


def write_events_tsv(
    events_table: pd.DataFrame,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write an events table to TSV."""
    from meeg_pipeline.io import ensure_output_does_not_exist

    ensure_output_does_not_exist(output_path, overwrite=overwrite)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    events_table.to_csv(output_path, sep="\t", index=False)

    return output_path