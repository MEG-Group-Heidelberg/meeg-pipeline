from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mne
import numpy as np
from mne import Annotations
from mne.io import BaseRaw

from meeg_pipeline.config import PipelineConfig


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


def clean_bad_segment_annotations(
    annotations: Annotations,
    *,
    remove_templates: bool = True,
    keep_bad_only: bool = True,
    template_descriptions: tuple[str, ...] = BAD_ANNOTATION_DESCRIPTIONS,
) -> Annotations:
    """Return annotations suitable for saving as bad-segment annotations.

    By default this keeps only BAD-like annotations and removes zero-duration
    template annotations that are only used to pre-populate the MNE annotation
    dropdown.
    """
    if len(annotations) == 0:
        return mne.Annotations([], [], [], orig_time=annotations.orig_time)

    keep: list[bool] = []

    for onset, duration, description in zip(
        annotations.onset,
        annotations.duration,
        annotations.description,
        strict=True,
    ):
        description = str(description)

        if keep_bad_only and not is_bad_annotation_description(description):
            keep.append(False)
            continue

        is_template = (
            remove_templates
            and float(duration) == 0.0
            and description in template_descriptions
        )
        keep.append(not is_template)

    if not any(keep):
        return mne.Annotations([], [], [], orig_time=annotations.orig_time)

    keep_array = np.asarray(keep, dtype=bool)

    return mne.Annotations(
        onset=np.asarray(annotations.onset)[keep_array],
        duration=np.asarray(annotations.duration)[keep_array],
        description=np.asarray(annotations.description, dtype=str)[keep_array],
        orig_time=annotations.orig_time,
    )


def prepare_raw_for_bad_segment_annotation(
    raw: BaseRaw,
    *,
    descriptions: tuple[str, ...] = BAD_ANNOTATION_DESCRIPTIONS,
    keep_existing_bad_annotations: bool = True,
    add_description_templates: bool = True,
) -> BaseRaw:
    """Prepare a Raw object for interactive bad-segment annotation.

    This removes non-BAD annotations such as trigger_1, trigger_2, ... from the
    annotation object used in the browser, and adds zero-duration BAD_* template
    annotations so the descriptions are already available in the MNE annotation
    dropdown.

    The Raw object is modified in-place and returned.
    """
    current = raw.annotations

    if keep_existing_bad_annotations:
        prepared = clean_bad_segment_annotations(
            current,
            remove_templates=True,
            keep_bad_only=True,
            template_descriptions=descriptions,
        )
    else:
        prepared = mne.Annotations([], [], [], orig_time=current.orig_time)

    if add_description_templates:
        existing_descriptions = set(str(desc) for desc in prepared.description)
        missing_descriptions = [
            description
            for description in descriptions
            if description not in existing_descriptions
        ]

        if missing_descriptions:
            templates = mne.Annotations(
                onset=[0.0] * len(missing_descriptions),
                duration=[0.0] * len(missing_descriptions),
                description=missing_descriptions,
                orig_time=prepared.orig_time,
            )
            prepared = prepared + templates

    raw.set_annotations(prepared)

    return raw


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
    """Save annotations or load an existing annotation decision."""
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

    cleaned = clean_bad_segment_annotations(annotations)

    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.save(path, overwrite=on_existing == "overwrite")

    return _annotation_result(
        annotations=cleaned,
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
