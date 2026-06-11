from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mne
from mne import Annotations
from mne.io import BaseRaw

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.io import ensure_output_does_not_exist


ExistingAnnotationsPolicy = Literal["error", "load", "overwrite"]


@dataclass(frozen=True)
class AnnotationResult:
    path: str
    status: str
    n_annotations: int
    n_bad_annotations: int
    descriptions: list[str]
    message: str = ""


def make_bad_annotations_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create derivative path for manually marked bad time segments."""
    subject = subject.removeprefix("sub-")

    parts = [f"sub-{subject}"]

    if session is not None:
        parts.append(f"ses-{session}")

    if task is not None:
        parts.append(f"task-{task}")

    if run is not None:
        parts.append(f"run-{run}")

    basename = "_".join(parts + ["desc-badsegments_annotations.fif"])

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


def count_bad_annotations(annotations: Annotations) -> int:
    """Count annotations whose description starts with BAD."""
    return sum(
        str(description).upper().startswith("BAD")
        for description in annotations.description
    )


def save_bad_annotations(
    config: PipelineConfig,
    *,
    subject: str,
    annotations: Annotations,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Save annotations as a derivative FIF file."""
    output_path = make_bad_annotations_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    ensure_output_does_not_exist(output_path, overwrite=overwrite)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    annotations.save(output_path, overwrite=overwrite)

    return output_path


def load_bad_annotations(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Annotations:
    """Load saved bad-segment annotations."""
    path = make_bad_annotations_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        raise FileNotFoundError(f"Bad-annotation file does not exist: {path}")

    return mne.read_annotations(path)


def save_or_load_bad_annotations(
    config: PipelineConfig,
    *,
    subject: str,
    annotations: Annotations,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingAnnotationsPolicy = "error",
) -> AnnotationResult:
    """Save annotations, or load an existing annotation decision."""
    if on_existing not in {"error", "load", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'error', 'load', or 'overwrite'."
        )

    path = make_bad_annotations_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if path.exists() and on_existing == "load":
        existing = load_bad_annotations(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )

        return AnnotationResult(
            path=str(path),
            status="loaded_existing",
            n_annotations=len(existing),
            n_bad_annotations=count_bad_annotations(existing),
            descriptions=sorted(set(str(desc) for desc in existing.description)),
            message="Bad-annotation file already exists; loaded existing decision.",
        )

    output_path = save_bad_annotations(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        annotations=annotations,
        overwrite=on_existing == "overwrite",
    )

    return AnnotationResult(
        path=str(output_path),
        status="saved",
        n_annotations=len(annotations),
        n_bad_annotations=count_bad_annotations(annotations),
        descriptions=sorted(set(str(desc) for desc in annotations.description)),
    )


def apply_bad_annotations(
    raw: BaseRaw,
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> BaseRaw:
    """Apply saved bad-segment annotations to a Raw object in-place."""
    annotations = load_bad_annotations(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    raw.set_annotations(annotations)

    return raw