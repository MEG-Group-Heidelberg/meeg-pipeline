from __future__ import annotations

import json
import pandas as pd
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mne.io import BaseRaw

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.io import ensure_output_does_not_exist


@dataclass(frozen=True)
class BadChannels:
    bads: list[str]
    method: str
    notes: str


ExistingBadChannelsPolicy = Literal["error", "load", "overwrite"]


@dataclass(frozen=True)
class SaveBadChannelsResult:
    path: str
    status: str
    bads: list[str]
    method: str
    notes: str
    message: str = ""


def make_bad_channels_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create the derivative path for manually marked bad channels."""
    subject = subject.removeprefix("sub-")

    parts = [f"sub-{subject}"]

    if session is not None:
        parts.append(f"ses-{session}")

    if task is not None:
        parts.append(f"task-{task}")

    if run is not None:
        parts.append(f"run-{run}")

    basename = "_".join(parts + ["desc-badchannels.json"])

    if session is None:
        directory = config.paths.derivatives_root / f"sub-{subject}" / config.bids.datatype
    else:
        directory = (
            config.paths.derivatives_root
            / f"sub-{subject}"
            / f"ses-{session}"
            / config.bids.datatype
        )

    return directory / basename


def save_bad_channels(
    config: PipelineConfig,
    *,
    subject: str,
    bads: list[str],
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    method: str = "manual_mne_gui",
    notes: str = "",
    overwrite: bool = False,
) -> Path:
    """Save manually marked bad channels as a JSON derivative."""
    output_path = make_bad_channels_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    ensure_output_does_not_exist(output_path, overwrite=overwrite)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "subject": subject.removeprefix("sub-"),
        "session": session,
        "task": task,
        "run": run,
        "bads": list(bads),
        "method": method,
        "notes": notes,
    }

    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return output_path


def load_bad_channels(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> BadChannels:
    """Load manually marked bad channels from a JSON derivative."""
    path = make_bad_channels_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        raise FileNotFoundError(f"Bad-channel file does not exist: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))

    return BadChannels(
        bads=list(payload.get("bads", [])),
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
    method: str = "manual_mne_gui",
    notes: str = "",
    on_existing: ExistingBadChannelsPolicy = "error",
    update_channels_tsv: bool = True,
) -> SaveBadChannelsResult:
    """Save bad channels, or load an existing bad-channel decision.

    Parameters
    ----------
    on_existing
        What to do if the bad-channel JSON already exists.

        - "error": raise FileExistsError
        - "load": load and return the existing decision
        - "overwrite": replace the existing decision
    """
    if on_existing not in {"error", "load", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'error', 'load', or 'overwrite'."
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
                status_description=f"{existing.method}: {existing.notes}".strip(": "),
            )

        return SaveBadChannelsResult(
            path=str(path),
            status="loaded_existing",
            bads=existing.bads,
            method=existing.method,
            notes=existing.notes,
            message="Bad-channel file already exists; loaded existing decision.",
        )

    output_path = save_bad_channels(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        bads=bads,
        method=method,
        notes=notes,
        overwrite=on_existing == "overwrite",
    )

    if update_channels_tsv:
        update_channels_tsv_with_bads(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
            bads=bads,
            status_description=f"{method}: {notes}".strip(": "),
        )

    return SaveBadChannelsResult(
        path=str(output_path),
        status="saved",
        bads=list(bads),
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
) -> BaseRaw:
    """Apply saved bad-channel markings to a Raw object in-place."""
    bad_channels = load_bad_channels(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    raw.info["bads"] = bad_channels.bads

    return raw


def update_channels_tsv_with_bads(
    config: PipelineConfig,
    *,
    subject: str,
    bads: list[str],
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    status_description: str = "Marked as bad during manual MNE GUI inspection.",
) -> Path:
    """Update the raw BIDS channels.tsv file with bad-channel markings.

    This modifies only the BIDS sidecar metadata file, not the raw FIF file.
    """
    from meeg_pipeline.bids import make_bids_path

    channels_path = make_bids_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        suffix="channels",
        extension=".tsv",
    ).fpath

    if not channels_path.exists():
        raise FileNotFoundError(f"channels.tsv file does not exist: {channels_path}")

    channels = pd.read_csv(channels_path, sep="\t")

    if "name" not in channels.columns:
        raise ValueError(f"channels.tsv has no 'name' column: {channels_path}")

    if "status" not in channels.columns:
        channels["status"] = "good"

    if "status_description" not in channels.columns:
        channels["status_description"] = ""

    bads = list(bads)

    unknown_bads = sorted(set(bads) - set(channels["name"]))
    if unknown_bads:
        raise ValueError(
            "Some bad channels were not found in channels.tsv: "
            f"{unknown_bads}"
        )

    channels["status"] = "good"
    channels["status_description"] = ""

    is_bad = channels["name"].isin(bads)
    channels.loc[is_bad, "status"] = "bad"
    channels.loc[is_bad, "status_description"] = status_description

    channels.to_csv(channels_path, sep="\t", index=False)

    return channels_path