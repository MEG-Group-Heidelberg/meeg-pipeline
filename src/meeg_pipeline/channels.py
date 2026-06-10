from __future__ import annotations

import pandas as pd

from collections import Counter
from dataclasses import dataclass

from mne.io import BaseRaw


@dataclass(frozen=True)
class ChannelSummary:
    n_channels: int
    channel_types: dict[str, int]
    bad_channels: list[str]
    stim_channels: list[str]
    eog_channels: list[str]
    ecg_channels: list[str]


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


def print_channel_summary(summary: ChannelSummary) -> None:
    """Print a simple channel summary."""
    print(f"Channels: {summary.n_channels}")
    print(f"Channel types: {summary.channel_types}")
    print(f"Bad channels: {summary.bad_channels}")
    print(f"Stim channels: {summary.stim_channels}")
    print(f"EOG channels: {summary.eog_channels}")
    print(f"ECG channels: {summary.ecg_channels}")