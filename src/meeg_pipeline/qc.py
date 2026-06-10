from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mne.io import BaseRaw

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.io import ensure_output_does_not_exist


@dataclass(frozen=True)
class BadChannels:
    bads: list[str]
    method: str
    notes: str


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