from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mne
import pandas as pd
from mne.io import BaseRaw

from meeg_pipeline.config import PipelineConfig


ANALYSIS_CHANNEL_TYPES = ("meg", "eeg", "eog", "ecg", "stim", "misc")
MEG_MNE_CHANNEL_TYPES = {"mag", "grad", "ref_meg"}


@dataclass(frozen=True)
class ChannelSummary:
    n_channels: int
    channel_types: dict[str, int]
    bad_channels: list[str]
    stim_channels: list[str]
    eog_channels: list[str]
    ecg_channels: list[str]


@dataclass(frozen=True)
class ChannelSidecarSummary:
    """Summary of a raw BIDS channels.tsv sidecar without opening raw data."""

    path: Path
    status: str
    message: str
    n_channels: int | None
    channel_types: dict[str, int]
    bad_channels: list[str]


@dataclass(frozen=True)
class ChannelSelectionSummary:
    """Status-oriented summary of configured analysis-channel availability."""

    status: str
    message: str
    requested_channel_types: tuple[str, ...]
    available_channel_types: dict[str, int]
    selected_channel_types: dict[str, int]
    selected_channels: list[str]
    missing_channel_types: tuple[str, ...]



def _analysis_type_from_mne_type(channel_type: str) -> str:
    if channel_type in MEG_MNE_CHANNEL_TYPES:
        return "meg"
    return channel_type


def _analysis_type_counts(channel_types: list[str]) -> dict[str, int]:
    return dict(Counter(_analysis_type_from_mne_type(t) for t in channel_types))


def get_analysis_channel_types(config: PipelineConfig) -> tuple[str, ...]:
    """Return channel types enabled for analysis in ``channels.analysis``.

    Defaults are intentionally MEG-only for backward compatibility.
    """
    analysis = config.channels.analysis
    return tuple(
        channel_type
        for channel_type in ANALYSIS_CHANNEL_TYPES
        if bool(getattr(analysis, channel_type))
    )



def analysis_pick_kwargs_from_config(config: PipelineConfig) -> dict[str, Any]:
    """Return MNE ``pick_types`` keyword arguments from channel config."""
    analysis = config.channels.analysis
    return {
        "meg": bool(analysis.meg),
        "eeg": bool(analysis.eeg),
        "eog": bool(analysis.eog),
        "ecg": bool(analysis.ecg),
        "stim": bool(analysis.stim),
        "misc": bool(analysis.misc),
    }



def pick_analysis_channels(
    raw: BaseRaw,
    config: PipelineConfig,
    *,
    exclude: str | list[str] | tuple[str, ...] = "bads",
) -> list[int]:
    """Return MNE channel indices selected by ``channels.analysis``.

    The function returns an empty list when the configured channel types are not
    present, so batch workflows can decide whether to report a status or raise.
    """
    return list(
        mne.pick_types(
            raw.info,
            **analysis_pick_kwargs_from_config(config),
            exclude=exclude,
        )
    )



def channel_selection_summary(
    raw: BaseRaw,
    config: PipelineConfig,
    *,
    exclude: str | list[str] | tuple[str, ...] = "bads",
) -> ChannelSelectionSummary:
    """Summarize configured analysis-channel selection for one Raw object."""
    requested = get_analysis_channel_types(config)
    raw_types = raw.get_channel_types()
    available = _analysis_type_counts(raw_types)
    picks = pick_analysis_channels(raw, config, exclude=exclude)
    selected_names = [raw.ch_names[pick] for pick in picks]
    selected_types = [raw_types[pick] for pick in picks]
    selected = _analysis_type_counts(selected_types)
    missing = tuple(
        channel_type
        for channel_type in requested
        if available.get(channel_type, 0) == 0
    )

    if not requested:
        status = "no_channel_types_configured"
        message = "No analysis channel types are enabled in channels.analysis."
    elif not picks:
        status = "no_analysis_channels"
        message = "No channels match the configured analysis channel selection."
    elif missing:
        status = "partial"
        message = "Some requested analysis channel types are not present."
    else:
        status = "ok"
        message = ""

    return ChannelSelectionSummary(
        status=status,
        message=message,
        requested_channel_types=requested,
        available_channel_types=available,
        selected_channel_types=selected,
        selected_channels=selected_names,
        missing_channel_types=missing,
    )



def summarize_channels_tsv(path: str | Path) -> ChannelSidecarSummary:
    """Summarize a BIDS channels.tsv sidecar without opening the raw FIF file."""
    path = Path(path)

    if not path.exists():
        return ChannelSidecarSummary(
            path=path,
            status="missing_channels_tsv",
            message="channels.tsv sidecar does not exist.",
            n_channels=None,
            channel_types={},
            bad_channels=[],
        )

    channels = pd.read_csv(path, sep="\t")

    if "type" in channels.columns:
        channel_types = {
            str(channel_type): int(count)
            for channel_type, count in channels["type"]
            .value_counts(dropna=False)
            .items()
        }
    else:
        channel_types = {}

    if {"name", "status"}.issubset(channels.columns):
        bad_mask = channels["status"].astype(str).str.lower().eq("bad")
        bad_channels = channels.loc[bad_mask, "name"].astype(str).tolist()
    else:
        bad_channels = []

    return ChannelSidecarSummary(
        path=path,
        status="loaded_sidecar",
        message="",
        n_channels=len(channels),
        channel_types=channel_types,
        bad_channels=bad_channels,
    )



def summarize_channels(raw: BaseRaw) -> ChannelSummary:
    """Summarize channel information from an MNE Raw object."""
    channel_types = raw.get_channel_types()
    channel_type_counts = dict(Counter(channel_types))

    stim_channels = [
        ch_name
        for ch_name, ch_type in zip(raw.ch_names, channel_types, strict=True)
        if ch_type == "stim"
    ]

    eog_channels = [
        ch_name
        for ch_name, ch_type in zip(raw.ch_names, channel_types, strict=True)
        if ch_type == "eog"
    ]

    ecg_channels = [
        ch_name
        for ch_name, ch_type in zip(raw.ch_names, channel_types, strict=True)
        if ch_type == "ecg"
    ]

    return ChannelSummary(
        n_channels=len(raw.ch_names),
        channel_types=channel_type_counts,
        bad_channels=list(raw.info["bads"]),
        stim_channels=stim_channels,
        eog_channels=eog_channels,
        ecg_channels=ecg_channels,
    )



def channel_summary_to_dataframe(summary: ChannelSummary) -> pd.DataFrame:
    """Convert a ChannelSummary to a notebook-friendly overview table."""
    return pd.DataFrame(
        [
            {
                "n_channels": summary.n_channels,
                "channel_types": ", ".join(
                    f"{channel_type}: {count}"
                    for channel_type, count in summary.channel_types.items()
                ),
                "n_bad_channels": len(summary.bad_channels),
                "n_stim_channels": len(summary.stim_channels),
                "n_eog_channels": len(summary.eog_channels),
                "n_ecg_channels": len(summary.ecg_channels),
            }
        ]
    )



def channel_lists_to_dataframe(summary: ChannelSummary) -> pd.DataFrame:
    """Convert channel lists from a ChannelSummary to a notebook-friendly table."""
    rows = []

    for channel_type, channel_names in [
        ("bad", summary.bad_channels),
        ("stim", summary.stim_channels),
        ("eog", summary.eog_channels),
        ("ecg", summary.ecg_channels),
    ]:
        if channel_names:
            for channel_name in channel_names:
                rows.append(
                    {
                        "channel_type": channel_type,
                        "channel_name": channel_name,
                    }
                )
        else:
            rows.append(
                {
                    "channel_type": channel_type,
                    "channel_name": None,
                }
            )

    return pd.DataFrame(rows)



def channel_selection_summary_to_dataframe(
    summary: ChannelSelectionSummary,
) -> pd.DataFrame:
    """Convert a ChannelSelectionSummary to a notebook-friendly table."""
    return pd.DataFrame(
        [
            {
                "status": summary.status,
                "message": summary.message,
                "requested_channel_types": ", ".join(summary.requested_channel_types),
                "available_channel_types": ", ".join(
                    f"{channel_type}: {count}"
                    for channel_type, count in summary.available_channel_types.items()
                ),
                "selected_channel_types": ", ".join(
                    f"{channel_type}: {count}"
                    for channel_type, count in summary.selected_channel_types.items()
                ),
                "n_selected_channels": len(summary.selected_channels),
                "missing_channel_types": ", ".join(summary.missing_channel_types),
            }
        ]
    )



def print_channel_summary(summary: ChannelSummary) -> None:
    """Print a simple channel summary."""
    print(f"Channels: {summary.n_channels}")
    print(f"Channel types: {summary.channel_types}")
    print(f"Bad channels: {summary.bad_channels}")
    print(f"Stim channels: {summary.stim_channels}")
    print(f"EOG channels: {summary.eog_channels}")
    print(f"ECG channels: {summary.ecg_channels}")
