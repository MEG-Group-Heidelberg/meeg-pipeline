from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mne
from mne import Annotations
from mne.io import BaseRaw

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.paths import derivative_path


ExistingAnnotationsPolicy = Literal["load", "overwrite"]

BAD_ANNOTATION_DESCRIPTIONS: tuple[str, ...] = (
    "BAD_artifact",
    "BAD_jump",
    "BAD_movement",
    "BAD_noise",
    "BAD_muscle",
    "BAD_other",
)


@dataclass(frozen=True)
class AnnotationResult:
    annotations: Annotations | None
    path: str
    status: str
    n_annotations: int = 0
    n_bad_annotations: int = 0
    descriptions: list[str] | None = None
    message: str = ""


@dataclass(frozen=True)
class ApplyAnnotationsResult:
    raw: BaseRaw
    path: str
    status: str
    n_annotations: int = 0
    n_bad_annotations: int = 0
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
    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="qc",
        suffix="desc-badsegments_annotations.fif",
    )

def is_bad_annotation_description(description: str) -> bool:
    """Return whether an annotation description follows MNE's BAD convention."""
    return str(description).upper().startswith("BAD")


def count_bad_annotations(annotations: Annotations) -> int:
    """Count annotations whose description starts with BAD."""
    return sum(
        is_bad_annotation_description(str(description))
        for description in annotations.description
    )


def annotation_descriptions(annotations: Annotations) -> list[str]:
    """Return sorted unique annotation descriptions."""
    return sorted(set(str(description) for description in annotations.description))


def keep_only_bad_annotations(annotations: Annotations) -> Annotations:
    """Return a copy containing only BAD-like annotations.

    Event-like annotations such as trigger_1, trigger_2, ... are not bad-segment
    annotations and should not be saved in the bad-segment derivative.
    """
    if len(annotations) == 0:
        return mne.Annotations([], [], [], orig_time=annotations.orig_time)

    bad_indices = [
        is_bad_annotation_description(str(description))
        for description in annotations.description
    ]

    if not any(bad_indices):
        return mne.Annotations([], [], [], orig_time=annotations.orig_time)

    return annotations[bad_indices]


def _annotation_result(
    *,
    annotations: Annotations | None,
    path: Path,
    status: str,
    message: str = "",
) -> AnnotationResult:
    if annotations is None:
        return AnnotationResult(
            annotations=None,
            path=str(path),
            status=status,
            message=message,
            descriptions=[],
        )

    return AnnotationResult(
        annotations=annotations,
        path=str(path),
        status=status,
        n_annotations=len(annotations),
        n_bad_annotations=count_bad_annotations(annotations),
        descriptions=annotation_descriptions(annotations),
        message=message,
    )


def load_bad_annotations(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> AnnotationResult:
    """Load saved bad-segment annotations if they exist."""
    path = make_bad_annotations_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return _annotation_result(
            annotations=None,
            path=path,
            status="missing_input",
            message="Bad-segment annotation file does not exist.",
        )

    return _annotation_result(
        annotations=mne.read_annotations(path),
        path=path,
        status="loaded",
    )


def save_or_load_bad_annotations(
    config: PipelineConfig,
    *,
    subject: str,
    annotations: Annotations,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingAnnotationsPolicy = "load",
) -> AnnotationResult:
    """Save BAD annotations or load an existing annotation decision.

    Only annotations whose description starts with BAD are saved. This prevents
    event-like annotations such as trigger_1 from becoming part of the
    bad-segment derivative.
    """
    if on_existing not in {"load", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'load' or 'overwrite'."
        )

    path = make_bad_annotations_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if path.exists() and on_existing == "load":
        existing = mne.read_annotations(path)
        return _annotation_result(
            annotations=existing,
            path=path,
            status="loaded_existing",
            message="Annotation file already exists; loaded existing decision.",
        )

    bad_annotations = keep_only_bad_annotations(annotations)

    path.parent.mkdir(parents=True, exist_ok=True)
    bad_annotations.save(path, overwrite=on_existing == "overwrite")

    return _annotation_result(
        annotations=bad_annotations,
        path=path,
        status="written",
    )


def apply_bad_annotations(
    raw: BaseRaw,
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> ApplyAnnotationsResult:
    """Apply saved bad-segment annotations if they exist.

    Missing annotations leave the Raw object unchanged.
    """
    result = load_bad_annotations(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if result.annotations is None:
        return ApplyAnnotationsResult(
            raw=raw,
            path=result.path,
            status=result.status,
            message=result.message,
        )

    raw.set_annotations(result.annotations)

    return ApplyAnnotationsResult(
        raw=raw,
        path=result.path,
        status="applied",
        n_annotations=result.n_annotations,
        n_bad_annotations=result.n_bad_annotations,
    )
