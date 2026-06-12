from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
from mne.io import BaseRaw
from mne.preprocessing import find_bad_channels_maxwell

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.paths import derivative_path


ExistingBadChannelsPolicy = Literal["load", "overwrite"]


@dataclass(frozen=True)
class BadChannelCandidates:
    noisy: list[str]
    flat: list[str]
    existing_bads: list[str]

    @property
    def combined(self) -> list[str]:
        return normalize_channel_names(self.noisy + self.flat + self.existing_bads)


@dataclass(frozen=True)
class BadChannelsResult:
    bads: list[str]
    path: str
    status: str
    method: str = ""
    notes: str = ""
    message: str = ""


@dataclass(frozen=True)
class ApplyBadChannelsResult:
    raw: BaseRaw
    path: str
    status: str
    bads: list[str]
    message: str = ""


@dataclass(frozen=True)
class ChannelsTSVResult:
    path: str
    status: str
    n_bad_channels: int = 0
    message: str = ""




def normalize_channel_names(ch_names) -> list[str]:
    """Return sorted unique channel names as plain Python strings."""
    if ch_names is None:
        return []

    return sorted({str(channel) for channel in ch_names})


def _format_status_description(method: str, notes: str) -> str:
    """Create a compact status_description string for channels.tsv."""
    if notes:
        return f"{method}: {notes}"

    return method


def make_bad_channels_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create the derivative path for manually marked bad channels."""
    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="qc",
        suffix="desc-badchannels.json",
    )

def make_channels_tsv_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create the raw BIDS channels.tsv path for a recording."""
    subject = subject.removeprefix("sub-")

    parts = [f"sub-{subject}"]

    if session is not None:
        parts.append(f"ses-{session}")

    if task is not None:
        parts.append(f"task-{task}")

    if run is not None:
        parts.append(f"run-{run}")

    basename = "_".join(parts + ["channels.tsv"])

    if session is None:
        directory = config.paths.bids_root / f"sub-{subject}" / config.bids.datatype
    else:
        directory = (
            config.paths.bids_root
            / f"sub-{subject}"
            / f"ses-{session}"
            / config.bids.datatype
        )

    return directory / basename


def detect_bad_channel_candidates_maxwell(
    raw: BaseRaw,
    *,
    coord_frame: str | None = None,
    n_jobs: int = 1,
    verbose: bool | str | int | None = True,
    **kwargs,
) -> BadChannelCandidates:
    """Detect bad-channel candidates using MNE Maxwell-based heuristics."""
    if coord_frame is None:
        coord_frame = "meg" if raw.info["dev_head_t"] is None else "head"

    os.environ["OMP_NUM_THREADS"] = str(n_jobs)

    noisy_chs, flat_chs = find_bad_channels_maxwell(
        raw,
        coord_frame=coord_frame,
        verbose=verbose,
        **kwargs,
    )

    return BadChannelCandidates(
        noisy=normalize_channel_names(noisy_chs),
        flat=normalize_channel_names(flat_chs),
        existing_bads=normalize_channel_names(raw.info["bads"]),
    )


def bad_channel_candidates_to_dataframe(
    candidates: BadChannelCandidates,
) -> pd.DataFrame:
    """Convert bad-channel candidates to a notebook-friendly table."""
    rows = []

    for kind, channels in [
        ("noisy", candidates.noisy),
        ("flat", candidates.flat),
        ("existing", candidates.existing_bads),
    ]:
        for channel in channels:
            rows.append(
                {
                    "candidate_type": kind,
                    "channel": channel,
                }
            )

    return pd.DataFrame(rows, columns=["candidate_type", "channel"])


def bad_channel_candidates_summary_to_dataframe(
    candidates: BadChannelCandidates,
) -> pd.DataFrame:
    """Summarize automatic bad-channel candidates."""
    return pd.DataFrame(
        [
            {
                "n_noisy": len(candidates.noisy),
                "n_flat": len(candidates.flat),
                "n_existing": len(candidates.existing_bads),
                "n_combined": len(candidates.combined),
                "combined": ", ".join(candidates.combined),
            }
        ]
    )


def load_bad_channels(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> BadChannelsResult:
    """Load manually marked bad channels if they exist."""
    path = make_bad_channels_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return BadChannelsResult(
            bads=[],
            path=str(path),
            status="missing_input",
            message="Bad-channel file does not exist.",
        )

    payload = json.loads(path.read_text(encoding="utf-8"))

    return BadChannelsResult(
        bads=normalize_channel_names(payload.get("bads", [])),
        path=str(path),
        status="loaded",
        method=str(payload.get("method", "")),
        notes=str(payload.get("notes", "")),
    )


def save_or_load_bad_channels(
    config: PipelineConfig,
    *,
    subject: str,
    bads: list[str],
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    method: str = "manual_mne_gui_with_maxwell_candidates",
    notes: str = (
        "Automatic Maxwell bad-channel candidates were pre-marked and manually "
        "reviewed with raw.plot(block=True)."
    ),
    on_existing: ExistingBadChannelsPolicy = "load",
    update_channels_tsv: bool = True,
) -> BadChannelsResult:
    """Save bad channels, or load an existing bad-channel decision."""
    if on_existing not in {"load", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'load' or 'overwrite'."
        )

    path = make_bad_channels_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if path.exists() and on_existing == "load":
        existing = load_bad_channels(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )

        if update_channels_tsv:
            update_channels_tsv_with_bads(
                config,
                subject=subject,
                session=session,
                task=task,
                run=run,
                bads=existing.bads,
                status_description=_format_status_description(
                    existing.method,
                    existing.notes,
                ),
            )

        return BadChannelsResult(
            bads=existing.bads,
            path=str(path),
            status="loaded_existing",
            method=existing.method,
            notes=existing.notes,
            message="Bad-channel file already exists; loaded existing decision.",
        )

    path.parent.mkdir(parents=True, exist_ok=True)

    normalized_bads = normalize_channel_names(bads)
    payload = {
        "subject": subject.removeprefix("sub-"),
        "session": session,
        "task": task,
        "run": run,
        "bads": normalized_bads,
        "method": method,
        "notes": notes,
    }

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if update_channels_tsv:
        update_channels_tsv_with_bads(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
            bads=normalized_bads,
            status_description=_format_status_description(method, notes),
        )

    return BadChannelsResult(
        bads=normalized_bads,
        path=str(path),
        status="written",
        method=method,
        notes=notes,
    )


def apply_bad_channels(
    raw: BaseRaw,
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> ApplyBadChannelsResult:
    """Apply saved bad-channel markings if they exist."""
    bad_channels = load_bad_channels(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if bad_channels.status == "missing_input":
        return ApplyBadChannelsResult(
            raw=raw,
            path=bad_channels.path,
            status="missing_input",
            bads=[],
            message=bad_channels.message,
        )

    raw.info["bads"] = normalize_channel_names(bad_channels.bads)

    return ApplyBadChannelsResult(
        raw=raw,
        path=bad_channels.path,
        status="applied",
        bads=normalize_channel_names(bad_channels.bads),
    )


def update_channels_tsv_with_bads(
    config: PipelineConfig,
    *,
    subject: str,
    bads: list[str],
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    status_description: str = "Marked as bad during manual MNE GUI inspection.",
) -> ChannelsTSVResult:
    """Update the raw BIDS channels.tsv file with bad-channel markings."""
    channels_path = make_channels_tsv_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not channels_path.exists():
        return ChannelsTSVResult(
            path=str(channels_path),
            status="missing_input",
            message="channels.tsv file does not exist.",
        )

    channels = pd.read_csv(channels_path, sep="\t")

    if "name" not in channels.columns:
        raise ValueError(f"channels.tsv has no 'name' column: {channels_path}")

    if "status" not in channels.columns:
        channels["status"] = "good"

    if "status_description" not in channels.columns:
        channels["status_description"] = ""

    bads = normalize_channel_names(bads)
    channel_names = normalize_channel_names(channels["name"])
    known_bads = sorted(set(bads).intersection(set(channel_names)))
    unknown_bads = sorted(set(bads) - set(channel_names))

    channels["status"] = "good"
    channels["status_description"] = ""

    is_bad = channels["name"].isin(known_bads)
    channels.loc[is_bad, "status"] = "bad"
    channels.loc[is_bad, "status_description"] = status_description

    channels.to_csv(channels_path, sep="\t", index=False)

    message = ""
    status = "updated"

    if unknown_bads:
        status = "updated_with_unknown_channels"
        message = f"Some bad channels were not found in channels.tsv: {unknown_bads}"

    return ChannelsTSVResult(
        path=str(channels_path),
        status=status,
        n_bad_channels=len(known_bads),
        message=message,
    )
