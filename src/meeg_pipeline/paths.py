from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from meeg_pipeline.config import PipelineConfig


DerivativeKind = Literal[
    "qc",
    "preprocessing",
    "cleaning",
    "events",
    "epochs",
    "evokeds",
    "arlog",
    "cov",
    "forward",
    "inverse",
    "morph",
    "psd",
    "source_estimates",
    "label_time_course",
    "reports",
]


def recording_parts(
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> list[str]:
    """Return BIDS-like filename entities for one recording."""
    subject = subject.removeprefix("sub-")

    parts = [f"sub-{subject}"]

    if session is not None:
        parts.append(f"ses-{session}")

    if task is not None:
        parts.append(f"task-{task}")

    if run is not None:
        parts.append(f"run-{run}")

    return parts


def derivative_directory(
    config: PipelineConfig,
    *,
    subject: str,
    session: str | None = None,
    kind: DerivativeKind | None = None,
) -> Path:
    """Return derivative directory for one subject/session/datatype.

    Examples
    --------
    kind=None:
        derivatives/meeg-pipeline/sub-0001/meg/

    kind="epochs":
        derivatives/meeg-pipeline/sub-0001/meg/epochs/
    """
    subject = subject.removeprefix("sub-")

    if session is None:
        directory = (
            config.paths.derivatives_root
            / f"sub-{subject}"
            / config.bids.datatype
        )
    else:
        directory = (
            config.paths.derivatives_root
            / f"sub-{subject}"
            / f"ses-{session}"
            / config.bids.datatype
        )

    if kind is not None:
        directory = directory / kind

    return directory


def derivative_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    kind: DerivativeKind | None = None,
    suffix: str,
) -> Path:
    """Create a derivative file path with BIDS-like entities.

    Parameters
    ----------
    suffix
        Non-entity filename part, for example ``"desc-cleaned_epo.fif"``.
    """
    parts = recording_parts(
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    basename = "_".join(parts + [suffix])

    return (
        derivative_directory(
            config,
            subject=subject,
            session=session,
            kind=kind,
        )
        / basename
    )


def bids_path_to_path(path_like: Any) -> Path:
    """Convert pathlib Path or MNE-BIDS BIDSPath to pathlib Path."""
    if hasattr(path_like, "fpath"):
        return Path(path_like.fpath)

    return Path(path_like)


def sanitize_bids_label(label: str) -> str:
    """Return an alphanumeric BIDS-style label for desc/entity values.

    The result is suitable for the free-value part of BIDS entities such as
    ``desc-...``.

    Examples
    --------
    "non_diatonic_1st_excl_1_2" -> "nonDiatonic1stExcl12"
    "key changes all" -> "keyChangesAll"
    """
    label = str(label).strip()

    if not label:
        return "unnamed"

    tokens = re.findall(r"[A-Za-z0-9]+", label)

    if not tokens:
        return "unnamed"

    first = tokens[0].lower()
    rest = [token[:1].upper() + token[1:] for token in tokens[1:]]
    sanitized = first + "".join(rest)

    if sanitized[0].isdigit():
        sanitized = f"cond{sanitized}"

    return sanitized
