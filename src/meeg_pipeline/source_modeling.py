from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable, Literal

import mne
import numpy as np
import pandas as pd

from meeg_pipeline.anatomy import (
    bem_solution_path,
    coregistration_trans_path,
    source_space_path,
)
from meeg_pipeline.cleaning import make_cleaned_raw_path
from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.epoching import make_epochs_path
from meeg_pipeline.paths import derivative_directory, derivative_path, sanitize_bids_label
from meeg_pipeline.workflow import ExistingOutputPolicy, Recording

InfoInputKind = Literal["epochs", "cleaned_raw", "evoked"]


@dataclass(frozen=True)
class SourceModelingPathResult:
    """Resolved source-modeling path with status metadata."""

    path: str
    kind: str
    status: str
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ForwardSolutionResult:
    """Result row for one forward-solution job."""

    subject: str
    session: str | None
    task: str | None
    run: str | None
    path: str
    status: str
    info_input: str = ""
    info_input_kind: str = ""
    trans_path: str = ""
    src_path: str = ""
    bem_path: str = ""
    message: str = ""


@dataclass(frozen=True)
class NoiseCovarianceResult:
    """Result row for one noise-covariance job."""

    subject: str
    session: str | None
    task: str | None
    run: str | None
    path: str
    status: str
    mode: str = ""
    data_input: str = ""
    message: str = ""


def _subject_label(subject: str) -> str:
    """Return a subject label with the ``sub-`` prefix."""
    return str(subject) if str(subject).startswith("sub-") else f"sub-{subject}"


def _recording_entities(recording: Recording) -> dict[str, str | None]:
    """Extract BIDS entities from a recording dictionary."""
    subject = recording.get("subject")
    if subject is None:
        raise ValueError("Recording must contain a non-missing 'subject'.")

    return {
        "subject": str(subject),
        "session": recording.get("session"),
        "task": recording.get("task"),
        "run": recording.get("run"),
    }


def _source_spacing(config: PipelineConfig, spacing: str | None = None) -> str:
    """Return the effective source-space spacing for source modeling."""
    if spacing is not None:
        return str(spacing)

    source_spacing = getattr(config.source, "spacing", None)
    if source_spacing:
        return str(source_spacing)

    return str(config.anatomy.source_space.spacing)


def _subjects_dir(config: PipelineConfig) -> Path:
    """Return the configured FreeSurfer subjects directory."""
    if config.freesurfer.subjects_dir is None:
        raise ValueError("freesurfer.subjects_dir must be configured for source modeling.")

    return Path(config.freesurfer.subjects_dir).expanduser().resolve()


def make_forward_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    spacing: str | None = None,
    desc: str = "meg",
) -> Path:
    """Create the derivative path for a forward solution."""
    spacing_label = sanitize_bids_label(_source_spacing(config, spacing))
    desc_label = sanitize_bids_label(desc)

    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="forward",
        suffix=f"space-{spacing_label}_desc-{desc_label}-fwd.fif",
    )


def make_noise_covariance_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    mode: str | None = None,
) -> Path:
    """Create the derivative path for a noise covariance matrix."""
    mode_label = sanitize_bids_label(mode or config.source.noise_cov_mode)

    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="cov",
        suffix=f"desc-{mode_label}-cov.fif",
    )


def make_inverse_operator_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    inverse_method: str | None = None,
) -> Path:
    """Create the derivative path for an inverse operator."""
    spacing_label = sanitize_bids_label(_source_spacing(config, spacing))
    cov_label = sanitize_bids_label(noise_cov_mode or config.source.noise_cov_mode)
    method_label = sanitize_bids_label(inverse_method or config.source.inverse_method)

    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="inverse",
        suffix=f"space-{spacing_label}_desc-{cov_label}{method_label}-inv.fif",
    )


def make_evoked_source_estimate_path(
    config: PipelineConfig,
    *,
    subject: str,
    condition: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    inverse_method: str | None = None,
) -> Path:
    """Create the HDF5 path for one evoked source estimate."""
    condition_label = sanitize_bids_label(condition)
    method_label = sanitize_bids_label(inverse_method or config.source.inverse_method)

    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="source_estimates",
        suffix=f"space-source_desc-{condition_label}{method_label}-stc.h5",
    )


def make_evoked_label_time_course_path(
    config: PipelineConfig,
    *,
    subject: str,
    condition: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    parcellation: str | None = None,
    inverse_method: str | None = None,
    extension: str = ".tsv",
) -> Path:
    """Create the path for one evoked label-time-course table."""
    condition_label = sanitize_bids_label(condition)
    parc_label = sanitize_bids_label(parcellation or config.source.parcellation)
    method_label = sanitize_bids_label(inverse_method or config.source.inverse_method)
    extension = extension if extension.startswith(".") else f".{extension}"

    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="label_time_course",
        suffix=f"space-label_parc-{parc_label}_desc-{condition_label}{method_label}-ltc{extension}",
    )


def make_epoch_label_time_course_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    parcellation: str | None = None,
    inverse_method: str | None = None,
    decim: int | None = None,
    extension: str = ".npy",
) -> Path:
    """Create the path for epoch-level label time courses."""
    parc_label = sanitize_bids_label(parcellation or config.source.parcellation)
    method_label = sanitize_bids_label(inverse_method or config.source.inverse_method)
    decim_label = f"decim{decim}" if decim not in {None, 1} else ""
    extension = extension if extension.startswith(".") else f".{extension}"

    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="label_time_course_epochs",
        suffix=f"space-label_parc-{parc_label}_desc-epoch{method_label}{decim_label}-ltc{extension}",
    )


def find_source_space_path(
    config: PipelineConfig,
    subject: str,
    *,
    spacing: str | None = None,
) -> Path:
    """Return the expected FreeSurfer source-space path."""
    return source_space_path(
        _subjects_dir(config),
        _subject_label(subject),
        spacing=_source_spacing(config, spacing),
    )


def find_bem_solution_path(config: PipelineConfig, subject: str) -> Path:
    """Return the expected FreeSurfer BEM solution path."""
    return bem_solution_path(
        _subjects_dir(config),
        _subject_label(subject),
        ico=config.anatomy.bem.ico,
        conductivity=config.anatomy.bem.conductivity,
    )


def _coregistration_transform_scope(
    config: PipelineConfig,
    transform_scope: str | None = None,
) -> str:
    """Return the effective configured coregistration transform scope."""
    if transform_scope is not None:
        scope = str(transform_scope)
    else:
        scope = str(
            getattr(
                getattr(config.anatomy, "coregistration", None),
                "transform_scope",
                "recording",
            )
        )

    if scope not in {"recording", "session", "subject"}:
        raise ValueError(
            "Coregistration transform scope must be one of "
            "'recording', 'session', or 'subject', "
            f"got {scope!r}."
        )

    return scope


def _allow_compatible_trans_fallback(config: PipelineConfig) -> bool:
    """Return whether compatible legacy transforms may be reused."""
    return bool(
        getattr(
            getattr(config.anatomy, "coregistration", None),
            "allow_compatible_fallback",
            True,
        )
    )


def _unique(items: Iterable[str]) -> list[str]:
    """Return unique strings while preserving input order."""
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _parse_session_from_bids_like_path(path: Path) -> str | None:
    """Parse a BIDS-like session label from a filename or parent folders."""
    for part in path.parts:
        if part.startswith("ses-"):
            return part.removeprefix("ses-")

    session = _parse_entity_from_filename(path, "ses")
    if session is not None:
        return session.removeprefix("ses-")

    return None


def _compatible_trans_candidates(
    config: PipelineConfig,
    *,
    subject: str,
    session: str | None = None,
    desc: str = "coreg",
) -> list[Path]:
    """Find existing subject/session-compatible coregistration transforms.

    This supports legacy project states where one task-specific transform, e.g.
    ``task-chords``, was saved and should be reused for another task, e.g.
    ``task-nochords``.
    """
    subject_label = _subject_label(subject)
    subject_dir = config.paths.derivatives_root / subject_label

    if not subject_dir.exists():
        return []

    pattern = f"{subject_label}*_desc-{sanitize_bids_label(desc)}_trans.fif"
    candidates = sorted(subject_dir.glob(f"**/{config.bids.datatype}/coregistration/{pattern}"))

    if session is None:
        return [path for path in candidates if path.is_file()]

    session_label = str(session).removeprefix("ses-")
    return [
        path
        for path in candidates
        if path.is_file() and _parse_session_from_bids_like_path(path) == session_label
    ]


def find_trans_path_result(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "coreg",
    transform_scope: str | None = None,
) -> SourceModelingPathResult:
    """Resolve a usable coregistration transform for a recording.

    The canonical output path is governed by
    ``anatomy.coregistration.transform_scope``. If it is missing and compatible
    fallback is enabled, this function can reuse existing subject/session-
    compatible transforms, including task-specific legacy transforms.
    """
    scope = _coregistration_transform_scope(config, transform_scope)
    canonical_path = coregistration_trans_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=desc,
        transform_scope=scope,
    )

    metadata = {
        "trans_scope": scope,
        "canonical_trans_path": str(canonical_path),
        "trans_match": "canonical",
    }

    if canonical_path.exists():
        return SourceModelingPathResult(
            path=str(canonical_path),
            kind="trans",
            status="found",
            metadata=metadata,
        )

    if not _allow_compatible_trans_fallback(config):
        return SourceModelingPathResult(
            path=str(canonical_path),
            kind="trans",
            status="missing",
            message="Canonical coregistration transform is missing.",
            metadata=metadata,
        )

    # Try exact paths under alternative scopes first. This covers projects that
    # changed transform_scope after some transforms had already been saved.
    for fallback_scope in _unique([scope, "recording", "session", "subject"]):
        fallback_path = coregistration_trans_path(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
            desc=desc,
            transform_scope=fallback_scope,
        )
        if fallback_path.exists():
            fallback_metadata = dict(metadata)
            fallback_metadata.update(
                {
                    "trans_scope": fallback_scope,
                    "trans_match": "fallback_exact_scope",
                }
            )
            return SourceModelingPathResult(
                path=str(fallback_path),
                kind="trans",
                status="found",
                message=(
                    "Using existing transform from fallback scope "
                    f"{fallback_scope!r}."
                ),
                metadata=fallback_metadata,
            )

    candidates = _compatible_trans_candidates(
        config,
        subject=subject,
        session=session,
        desc=desc,
    )

    if len(candidates) == 1:
        fallback_metadata = dict(metadata)
        fallback_metadata.update(
            {
                "trans_scope": "compatible",
                "trans_match": "fallback_compatible",
            }
        )
        return SourceModelingPathResult(
            path=str(candidates[0]),
            kind="trans",
            status="found",
            message=(
                "Using one compatible existing coregistration transform: "
                f"{candidates[0].name}"
            ),
            metadata=fallback_metadata,
        )

    if len(candidates) > 1:
        return SourceModelingPathResult(
            path=str(canonical_path),
            kind="trans",
            status="ambiguous",
            message=(
                "Canonical coregistration transform is missing and multiple "
                "compatible fallback transforms exist: "
                + ", ".join(path.name for path in candidates)
            ),
            metadata=metadata | {"trans_match": "ambiguous_fallback"},
        )

    return SourceModelingPathResult(
        path=str(canonical_path),
        kind="trans",
        status="missing",
        message="No canonical or compatible coregistration transform was found.",
        metadata=metadata,
    )


def find_trans_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "coreg",
) -> Path:
    """Return a usable coregistration transform path for backward compatibility."""
    result = find_trans_path_result(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=desc,
    )
    return Path(result.path)


def _evoked_candidates(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> list[Path]:
    """Return matching condition-specific evoked files for one recording."""
    directory = derivative_directory(
        config,
        subject=subject,
        session=session,
        kind="evokeds",
    )

    subject_label = _subject_label(subject)
    parts = [subject_label]
    if session is not None:
        parts.append(f"ses-{session}")
    if task is not None:
        parts.append(f"task-{task}")
    if run is not None:
        parts.append(f"run-{run}")

    pattern = "_".join(parts + ["desc-*_ave.fif"])
    return sorted(directory.glob(pattern))


def find_info_input_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> SourceModelingPathResult:
    """Find the preferred derivative from which to read measurement info.

    Preference order:
    1. cleaned epochs
    2. ICA-cleaned continuous raw
    3. condition-specific evoked files
    """
    epochs_path = make_epochs_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )
    if epochs_path.exists():
        return SourceModelingPathResult(
            path=str(epochs_path),
            kind="epochs",
            status="found",
        )

    cleaned_raw_path = make_cleaned_raw_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )
    if cleaned_raw_path.exists():
        return SourceModelingPathResult(
            path=str(cleaned_raw_path),
            kind="cleaned_raw",
            status="found",
        )

    evoked_candidates = _evoked_candidates(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )
    if evoked_candidates:
        return SourceModelingPathResult(
            path=str(evoked_candidates[0]),
            kind="evoked",
            status="found",
            message=(
                "Using first matching evoked file as info input: "
                f"{evoked_candidates[0].name}"
            ),
        )

    return SourceModelingPathResult(
        path="",
        kind="",
        status="missing",
        message="No cleaned epochs, cleaned raw, or evoked derivative was found.",
    )


def _read_info_from_input(path: str | Path, kind: str) -> mne.Info:
    """Read MNE Info from an epochs, raw, or evoked derivative."""
    path = Path(path)

    if kind == "epochs":
        epochs = mne.read_epochs(path, preload=False, verbose="error")
        return epochs.info

    if kind == "cleaned_raw":
        raw = mne.io.read_raw_fif(path, preload=False, verbose="error")
        return raw.info

    if kind == "evoked":
        evoked = mne.read_evokeds(path, condition=0, verbose="error")
        return evoked.info

    raise ValueError(f"Unsupported info input kind: {kind!r}.")


def forward_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    spacing: str | None = None,
    trans_desc: str = "coreg",
) -> pd.DataFrame:
    """Summarize forward-solution inputs and output status for recordings."""
    rows: list[dict[str, Any]] = []

    for recording in recordings:
        entities = _recording_entities(recording)
        subject = entities["subject"]
        session = entities["session"]
        task = entities["task"]
        run = entities["run"]

        info_input = find_info_input_path(config, **entities)
        trans_input = find_trans_path_result(config, **entities, desc=trans_desc)
        trans_path = Path(trans_input.path)
        src_path = find_source_space_path(config, subject, spacing=spacing)
        bem_path = find_bem_solution_path(config, subject)
        fwd_path = make_forward_path(config, **entities, spacing=spacing)

        missing = []
        if info_input.status != "found":
            missing.append("info")
        if trans_input.status != "found":
            missing.append("trans")
        if not src_path.exists():
            missing.append("source_space")
        if not bem_path.exists():
            missing.append("bem_solution")

        if fwd_path.exists() and on_existing == "skip":
            status = "exists"
            message = "Forward solution already exists."
        elif missing:
            status = "missing_" + "_".join(missing)
            message = "Missing required input(s): " + ", ".join(missing)
        else:
            status = "ready"
            message = info_input.message

        rows.append(
            {
                "subject": _subject_label(subject),
                "session": session,
                "task": task,
                "run": run,
                "status": status,
                "message": message,
                "info_input_kind": info_input.kind,
                "info_input_exists": info_input.status == "found",
                "info_input": info_input.path,
                "trans_status": trans_input.status,
                "trans_message": trans_input.message,
                "trans_scope": trans_input.metadata.get("trans_scope", ""),
                "trans_match": trans_input.metadata.get("trans_match", ""),
                "canonical_trans_path": trans_input.metadata.get("canonical_trans_path", ""),
                "trans_exists": trans_input.status == "found",
                "trans_path": str(trans_path),
                "src_exists": src_path.exists(),
                "src_path": str(src_path),
                "bem_exists": bem_path.exists(),
                "bem_path": str(bem_path),
                "fwd_exists": fwd_path.exists(),
                "fwd_path": str(fwd_path),
                "overwrite": on_existing == "overwrite",
            }
        )

    return pd.DataFrame(rows)


def write_forward_solution_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    on_existing: ExistingOutputPolicy = "skip",
    spacing: str | None = None,
    trans_desc: str = "coreg",
    meg: bool = True,
    eeg: bool = False,
    mindist: float = 5.0,
    n_jobs: int | None = None,
    verbose: bool | str | int | None = True,
) -> ForwardSolutionResult:
    """Create and write a forward solution for one recording.

    Missing inputs are returned as status values instead of raising, so callers
    can use this function safely in batch notebooks.
    """
    entities = _recording_entities(recording)
    subject = entities["subject"]
    session = entities["session"]
    task = entities["task"]
    run = entities["run"]

    fwd_path = make_forward_path(config, **entities, spacing=spacing)

    if fwd_path.exists() and on_existing == "skip":
        return ForwardSolutionResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(fwd_path),
            status="skipped_existing",
            message="Forward solution already exists.",
        )

    overview = forward_input_overview_to_dataframe(
        config,
        [recording],
        on_existing="overwrite",
        spacing=spacing,
        trans_desc=trans_desc,
    ).iloc[0]

    if overview["status"] != "ready":
        return ForwardSolutionResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(fwd_path),
            status=str(overview["status"]),
            info_input=str(overview["info_input"]),
            info_input_kind=str(overview["info_input_kind"]),
            trans_path=str(overview["trans_path"]),
            src_path=str(overview["src_path"]),
            bem_path=str(overview["bem_path"]),
            message=str(overview["message"]),
        )

    info = _read_info_from_input(
        overview["info_input"],
        str(overview["info_input_kind"]),
    )

    src = mne.read_source_spaces(overview["src_path"], verbose=verbose)

    fwd = mne.make_forward_solution(
        info=info,
        trans=overview["trans_path"],
        src=src,
        bem=overview["bem_path"],
        meg=meg,
        eeg=eeg,
        mindist=mindist,
        n_jobs=config.runtime.n_jobs if n_jobs is None else n_jobs,
        verbose=verbose,
    )

    fwd_path.parent.mkdir(parents=True, exist_ok=True)
    mne.write_forward_solution(
        fwd_path,
        fwd,
        overwrite=on_existing == "overwrite",
        verbose=verbose,
    )

    return ForwardSolutionResult(
        subject=_subject_label(subject),
        session=session,
        task=task,
        run=run,
        path=str(fwd_path),
        status="written",
        info_input=str(overview["info_input"]),
        info_input_kind=str(overview["info_input_kind"]),
        trans_path=str(overview["trans_path"]),
        src_path=str(overview["src_path"]),
        bem_path=str(overview["bem_path"]),
    )


def write_forward_solutions_for_recordings(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    spacing: str | None = None,
    trans_desc: str = "coreg",
    meg: bool = True,
    eeg: bool = False,
    mindist: float = 5.0,
    n_jobs: int | None = None,
    verbose: bool | str | int | None = True,
) -> list[ForwardSolutionResult]:
    """Create forward solutions for multiple recordings."""
    results = []

    for recording in recordings:
        try:
            result = write_forward_solution_for_recording(
                config,
                recording,
                on_existing=on_existing,
                spacing=spacing,
                trans_desc=trans_desc,
                meg=meg,
                eeg=eeg,
                mindist=mindist,
                n_jobs=n_jobs,
                verbose=verbose,
            )
        except Exception as exc:  # noqa: BLE001 - batch notebooks should continue.
            entities = _recording_entities(recording)
            result = ForwardSolutionResult(
                subject=_subject_label(str(entities["subject"])),
                session=entities["session"],
                task=entities["task"],
                run=entities["run"],
                path=str(make_forward_path(config, **entities, spacing=spacing)),
                status="failed",
                message=f"{type(exc).__name__}: {exc}",
            )

        results.append(result)

    return results


def forward_results_to_dataframe(
    results: Iterable[ForwardSolutionResult],
) -> pd.DataFrame:
    """Convert forward-solution results to a status table."""
    return pd.DataFrame([result.__dict__ for result in results])


def _noise_cov_mode(config: PipelineConfig, mode: str | None = None) -> str:
    """Return the effective noise-covariance mode."""
    return str(mode or config.source.noise_cov_mode)


def _covariance_baseline(config: PipelineConfig) -> tuple[float | None, float | None]:
    """Return the epoch baseline interval used for covariance estimation.

    The current config does not yet expose a dedicated source.noise_cov baseline.
    For now, use all pre-stimulus samples up to time zero.
    """
    return (None, 0.0)


def find_epochs_baseline_noise_input_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> SourceModelingPathResult:
    """Find cleaned epochs for baseline covariance estimation."""
    epochs_path = make_epochs_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if epochs_path.exists():
        return SourceModelingPathResult(
            path=str(epochs_path),
            kind="epochs_baseline",
            status="found",
        )

    return SourceModelingPathResult(
        path="",
        kind="epochs_baseline",
        status="missing",
        message="No cleaned epochs derivative was found for baseline covariance.",
    )


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _datetime_from_info(info: mne.Info) -> datetime | None:
    """Return measurement datetime from MNE info if available."""
    meas_date = info.get("meas_date")
    if meas_date is None:
        return None
    if isinstance(meas_date, datetime):
        return meas_date if meas_date.tzinfo is not None else meas_date.replace(tzinfo=timezone.utc)
    return None


def _recording_datetime(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> datetime | None:
    """Read the measurement datetime from the preferred recording info input."""
    info_input = find_info_input_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )
    if info_input.status != "found":
        return None
    try:
        info = _read_info_from_input(info_input.path, info_input.kind)
    except Exception:  # noqa: BLE001 - matching should remain status-based.
        return None
    return _datetime_from_info(info)


def _session_date(session: str | None) -> datetime | None:
    """Parse BIDS session labels such as 20250313 or ses-20250313."""
    if session is None:
        return None
    match = re.fullmatch(r"(?:ses-)?(\d{8})", str(session))
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _bids_empty_room_subject(config: PipelineConfig) -> str:
    return str(getattr(config.empty_room, "subject", "emptyroom")).removeprefix("sub-")


def _bids_empty_room_task(config: PipelineConfig) -> str:
    return str(getattr(config.empty_room, "task", "noise"))


def _parse_entity_from_filename(path: Path, entity: str) -> str | None:
    prefix = f"{entity}-"
    for part in path.name.split("_"):
        if part.startswith(prefix):
            value = part.removeprefix(prefix)
            if entity == "run":
                value = value.split("_")[0]
            return value.split(".")[0]
    return None


def _parse_session_from_empty_room_path(path: Path) -> str | None:
    for part in path.parts:
        if part.startswith("ses-"):
            return part.removeprefix("ses-")
    return _parse_entity_from_filename(path, "ses")


def _parse_run_from_empty_room_path(path: Path) -> str | None:
    return _parse_entity_from_filename(path, "run")


def _empty_room_bids_candidates(config: PipelineConfig) -> list[dict[str, Any]]:
    """Find BIDS empty-room FIF candidates under the raw BIDS root."""
    root = config.paths.bids_root
    subject = _bids_empty_room_subject(config)
    task = _bids_empty_room_task(config)
    subject_dir = root / f"sub-{subject}"

    if not subject_dir.exists():
        return []

    files = sorted(subject_dir.glob("**/meg/*.fif*"))
    candidates: list[dict[str, Any]] = []

    for path in files:
        if not path.is_file():
            continue
        filename_task = _parse_entity_from_filename(path, "task")
        if filename_task is not None and filename_task != task:
            continue
        if filename_task is None and f"task-{task}" not in path.name:
            # Be tolerant but prefer task-noise files in BIDS-like trees.
            continue

        session = _parse_session_from_empty_room_path(path)
        run = _parse_run_from_empty_room_path(path)
        meas_date = None
        try:
            raw = mne.io.read_raw_fif(path, preload=False, verbose="error")
            meas_date = _datetime_from_info(raw.info)
        except Exception:  # noqa: BLE001 - candidate discovery should continue.
            meas_date = None

        candidates.append(
            {
                "path": path,
                "subject": subject,
                "session": session,
                "task": task,
                "run": run,
                "meas_date": meas_date,
                "session_date": _session_date(session),
            }
        )

    return candidates


def _candidate_date(candidate: dict[str, Any]) -> datetime | None:
    return candidate.get("meas_date") or candidate.get("session_date")


def _format_time_diff_hours(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _result_from_empty_room_candidate(
    candidate: dict[str, Any],
    *,
    status: str,
    message: str,
    strategy: str,
    recording_meas_date: datetime | None,
    time_diff_hours: float | None,
) -> SourceModelingPathResult:
    return SourceModelingPathResult(
        path=str(candidate["path"]),
        kind="erm",
        status=status,
        message=message,
        metadata={
            "match_strategy": strategy,
            "recording_meas_date": _datetime_to_iso(recording_meas_date),
            "selected_erm_session": candidate.get("session"),
            "selected_erm_run": candidate.get("run"),
            "selected_erm_meas_date": _datetime_to_iso(candidate.get("meas_date")),
            "selected_erm_session_date": _datetime_to_iso(candidate.get("session_date")),
            "time_diff_hours": _format_time_diff_hours(time_diff_hours),
        },
    )


def _check_max_time_diff(
    config: PipelineConfig,
    time_diff_hours: float | None,
) -> str | None:
    max_hours = getattr(config.empty_room.matching, "max_time_diff_hours", None)
    if max_hours is None or time_diff_hours is None:
        return None
    if time_diff_hours > float(max_hours):
        return (
            f"Nearest empty-room recording is {time_diff_hours:.2f} h away, "
            f"which exceeds max_time_diff_hours={float(max_hours):.2f}."
        )
    return None


def _match_empty_room_by_meas_date(
    config: PipelineConfig,
    candidates: list[dict[str, Any]],
    *,
    recording_meas_date: datetime | None,
) -> SourceModelingPathResult | None:
    if recording_meas_date is None:
        return None

    dated = [candidate for candidate in candidates if _candidate_date(candidate) is not None]
    if not dated:
        return None

    selected = min(
        dated,
        key=lambda candidate: abs(_candidate_date(candidate) - recording_meas_date),
    )
    selected_date = _candidate_date(selected)
    diff_hours = abs((selected_date - recording_meas_date).total_seconds()) / 3600.0
    max_message = _check_max_time_diff(config, diff_hours)
    if max_message is not None:
        return SourceModelingPathResult(
            path="",
            kind="erm",
            status="missing",
            message=max_message,
            metadata={
                "match_strategy": "meas_date_nearest",
                "recording_meas_date": _datetime_to_iso(recording_meas_date),
                "selected_erm_session": selected.get("session"),
                "selected_erm_run": selected.get("run"),
                "selected_erm_meas_date": _datetime_to_iso(selected.get("meas_date")),
                "selected_erm_session_date": _datetime_to_iso(selected.get("session_date")),
                "time_diff_hours": _format_time_diff_hours(diff_hours),
            },
        )

    return _result_from_empty_room_candidate(
        selected,
        status="found",
        message=f"Selected nearest empty-room recording by measurement date ({diff_hours:.2f} h).",
        strategy="meas_date_nearest",
        recording_meas_date=recording_meas_date,
        time_diff_hours=diff_hours,
    )


def _match_empty_room_by_session_exact(
    candidates: list[dict[str, Any]],
    *,
    recording_session: str | None,
    recording_meas_date: datetime | None,
) -> SourceModelingPathResult | None:
    if recording_session is None:
        return None

    matching = [candidate for candidate in candidates if candidate.get("session") == recording_session]
    if not matching:
        return None

    selected = sorted(matching, key=lambda candidate: str(candidate["path"]))[0]
    diff_hours = None
    if recording_meas_date is not None and _candidate_date(selected) is not None:
        diff_hours = abs((_candidate_date(selected) - recording_meas_date).total_seconds()) / 3600.0

    return _result_from_empty_room_candidate(
        selected,
        status="found",
        message="Selected empty-room recording by exact BIDS session match.",
        strategy="session_exact",
        recording_meas_date=recording_meas_date,
        time_diff_hours=diff_hours,
    )


def _match_empty_room_by_session_date(
    candidates: list[dict[str, Any]],
    *,
    recording_session: str | None,
    recording_meas_date: datetime | None,
) -> SourceModelingPathResult | None:
    recording_session_date = _session_date(recording_session)
    if recording_session_date is None:
        return None

    dated = [candidate for candidate in candidates if candidate.get("session_date") is not None]
    if not dated:
        return None

    selected = min(
        dated,
        key=lambda candidate: abs(candidate["session_date"] - recording_session_date),
    )
    diff_hours = abs((selected["session_date"] - recording_session_date).total_seconds()) / 3600.0

    return _result_from_empty_room_candidate(
        selected,
        status="found",
        message="Selected nearest empty-room recording by date-like session label.",
        strategy="session_date_nearest",
        recording_meas_date=recording_meas_date,
        time_diff_hours=diff_hours,
    )


def find_empty_room_noise_input_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> SourceModelingPathResult:
    """Find the BIDS empty-room recording matched to one recording.

    Supported matching strategies are configured under
    ``empty_room.matching.strategy``:

    - ``meas_date_nearest``: nearest empty-room measurement datetime
    - ``session_exact``: identical BIDS session label
    - ``session_date_nearest``: nearest date-like session label
    - ``auto``: try measurement date, exact session, then session date
    """
    if not getattr(config.empty_room, "enabled", False):
        return SourceModelingPathResult(
            path="",
            kind="erm",
            status="missing",
            message="empty_room.enabled is false in the config.",
        )

    candidates = _empty_room_bids_candidates(config)
    if not candidates:
        return SourceModelingPathResult(
            path="",
            kind="erm",
            status="missing",
            message=(
                "No BIDS empty-room FIF files found. Run the empty-room block "
                "in 1B_meg_preprocessing/01_raw_bids_and_events.ipynb first."
            ),
        )

    recording_meas_date = _recording_datetime(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )
    strategy = getattr(config.empty_room.matching, "strategy", "meas_date_nearest")

    strategies = [strategy]
    if strategy == "auto":
        strategies = ["meas_date_nearest", "session_exact", "session_date_nearest"]
    elif getattr(config.empty_room.matching, "allow_fallback", True):
        fallback = getattr(config.empty_room.matching, "fallback_strategy", None)
        if fallback is not None and fallback not in strategies:
            strategies.append(fallback)

    for current_strategy in strategies:
        if current_strategy == "meas_date_nearest":
            result = _match_empty_room_by_meas_date(
                config,
                candidates,
                recording_meas_date=recording_meas_date,
            )
        elif current_strategy == "session_exact":
            result = _match_empty_room_by_session_exact(
                candidates,
                recording_session=session,
                recording_meas_date=recording_meas_date,
            )
        elif current_strategy == "session_date_nearest":
            result = _match_empty_room_by_session_date(
                candidates,
                recording_session=session,
                recording_meas_date=recording_meas_date,
            )
        else:
            result = None

        if result is not None and result.status == "found":
            return result
        if result is not None and result.status != "found":
            return result

    return SourceModelingPathResult(
        path="",
        kind="erm",
        status="missing",
        message=(
            "No empty-room recording could be matched with strategy "
            f"{strategy!r}."
        ),
        metadata={
            "match_strategy": strategy,
            "recording_meas_date": _datetime_to_iso(recording_meas_date),
        },
    )


def find_noise_input_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    mode: str | None = None,
) -> SourceModelingPathResult:
    """Find the preferred input for one noise-covariance mode."""
    mode = _noise_cov_mode(config, mode)

    if mode == "epochs_baseline":
        return find_epochs_baseline_noise_input_path(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )

    if mode == "erm":
        return find_empty_room_noise_input_path(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )

    if mode == "adhoc":
        info_input = find_info_input_path(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )
        if info_input.status == "found":
            return SourceModelingPathResult(
                path=info_input.path,
                kind="adhoc",
                status="found",
                message="Using info input for ad-hoc covariance.",
            )
        return SourceModelingPathResult(
            path="",
            kind="adhoc",
            status="missing",
            message="No info input found for ad-hoc covariance.",
        )

    return SourceModelingPathResult(
        path="",
        kind=mode,
        status="unsupported",
        message=f"Unsupported noise covariance mode: {mode!r}.",
    )


def noise_covariance_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    mode: str | None = None,
) -> pd.DataFrame:
    """Summarize noise-covariance inputs and output status for recordings."""
    rows: list[dict[str, Any]] = []
    mode = _noise_cov_mode(config, mode)

    for recording in recordings:
        entities = _recording_entities(recording)
        subject = entities["subject"]
        session = entities["session"]
        task = entities["task"]
        run = entities["run"]

        noise_input = find_noise_input_path(config, **entities, mode=mode)
        cov_path = make_noise_covariance_path(config, **entities, mode=mode)

        if cov_path.exists() and on_existing == "skip":
            status = "exists"
            message = "Noise covariance already exists."
        elif noise_input.status == "unsupported":
            status = "unsupported_mode"
            message = noise_input.message
        elif noise_input.status != "found":
            status = f"missing_{mode}"
            message = noise_input.message
        else:
            status = "ready"
            message = noise_input.message

        row = {
            "subject": _subject_label(subject),
            "session": session,
            "task": task,
            "run": run,
            "status": status,
            "message": message,
            "mode": mode,
            "data_input_kind": noise_input.kind,
            "data_input_exists": noise_input.status == "found",
            "data_input": noise_input.path,
            "cov_exists": cov_path.exists(),
            "cov_path": str(cov_path),
            "overwrite": on_existing == "overwrite",
        }
        row.update(noise_input.metadata)
        rows.append(row)

    return pd.DataFrame(rows)


def _compute_epochs_baseline_covariance(
    config: PipelineConfig,
    epochs_path: str | Path,
    *,
    method: str | list[str] | None = "empirical",
    rank: str | dict[str, int] | None = None,
    verbose: bool | str | int | None = True,
) -> mne.Covariance:
    """Compute a noise covariance matrix from the pre-stimulus epoch baseline."""
    epochs = mne.read_epochs(
        epochs_path,
        preload=True,
        verbose=verbose,
    )

    tmin, tmax = _covariance_baseline(config)

    return mne.compute_covariance(
        epochs,
        tmin=tmin,
        tmax=tmax,
        method=method,
        rank=rank,
        verbose=verbose,
    )


def _compute_ad_hoc_covariance(
    info_path: str | Path,
    info_kind: str,
) -> mne.Covariance:
    """Create an ad-hoc covariance matrix from recording info."""
    info = _read_info_from_input(info_path, info_kind)
    return mne.make_ad_hoc_cov(info)



def _apply_configured_empty_room_filtering(
    raw: mne.io.BaseRaw,
    config: PipelineConfig,
    *,
    verbose: bool | str | int | None = True,
) -> mne.io.BaseRaw:
    """Apply project-compatible basic filtering to an empty-room raw object."""
    filtering = config.preprocessing.filtering

    if filtering.notch_freqs:
        raw.notch_filter(
            freqs=list(filtering.notch_freqs),
            method=filtering.method,
            verbose=verbose,
        )

    if filtering.l_freq is not None or filtering.h_freq is not None:
        raw.filter(
            l_freq=filtering.l_freq,
            h_freq=filtering.h_freq,
            method=filtering.method,
            verbose=verbose,
        )

    return raw


def _match_covariance_to_info(cov: mne.Covariance, info: mne.Info) -> mne.Covariance:
    """Restrict and order covariance channels to match recording info."""
    include = [name for name in info["ch_names"] if name in cov["names"]]
    if not include:
        raise ValueError("No overlapping channels between ERM covariance and recording info.")
    return mne.pick_channels_cov(cov, include=include, exclude=[], ordered=True)


def _compute_empty_room_covariance(
    config: PipelineConfig,
    empty_room_path: str | Path,
    info_path: str | Path,
    info_kind: str,
    *,
    method: str | list[str] | None = "empirical",
    rank: str | dict[str, int] | None = None,
    verbose: bool | str | int | None = True,
) -> mne.Covariance:
    """Compute a noise covariance matrix from a BIDS empty-room raw FIF file."""
    raw = mne.io.read_raw_fif(empty_room_path, preload=True, verbose=verbose)
    raw.pick_types(meg=True, eeg=False, stim=False, eog=False, ecg=False, exclude=[])
    raw = _apply_configured_empty_room_filtering(raw, config, verbose=verbose)
    cov = mne.compute_raw_covariance(raw, method=method, rank=rank, verbose=verbose)
    info = _read_info_from_input(info_path, info_kind)
    return _match_covariance_to_info(cov, info)

def write_noise_covariance_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    on_existing: ExistingOutputPolicy = "skip",
    mode: str | None = None,
    method: str | list[str] | None = "empirical",
    rank: str | dict[str, int] | None = None,
    verbose: bool | str | int | None = True,
) -> NoiseCovarianceResult:
    """Create and write a noise covariance matrix for one recording.

    Missing inputs are returned as status values instead of raising, so callers
    can use this function safely in batch notebooks.
    """
    entities = _recording_entities(recording)
    subject = entities["subject"]
    session = entities["session"]
    task = entities["task"]
    run = entities["run"]
    mode = _noise_cov_mode(config, mode)

    cov_path = make_noise_covariance_path(config, **entities, mode=mode)

    if cov_path.exists() and on_existing == "skip":
        return NoiseCovarianceResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(cov_path),
            status="skipped_existing",
            mode=mode,
            message="Noise covariance already exists.",
        )

    overview = noise_covariance_input_overview_to_dataframe(
        config,
        [recording],
        on_existing="overwrite",
        mode=mode,
    ).iloc[0]

    if overview["status"] != "ready":
        return NoiseCovarianceResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(cov_path),
            status=str(overview["status"]),
            mode=mode,
            data_input=str(overview["data_input"]),
            message=str(overview["message"]),
        )

    if mode == "epochs_baseline":
        cov = _compute_epochs_baseline_covariance(
            config,
            overview["data_input"],
            method=method,
            rank=rank,
            verbose=verbose,
        )
    elif mode == "erm":
        info_input = find_info_input_path(config, **entities)
        if info_input.status != "found":
            return NoiseCovarianceResult(
                subject=_subject_label(subject),
                session=session,
                task=task,
                run=run,
                path=str(cov_path),
                status="missing_info",
                mode=mode,
                data_input=str(overview["data_input"]),
                message="No recording info input found for ERM channel matching.",
            )
        cov = _compute_empty_room_covariance(
            config,
            overview["data_input"],
            info_input.path,
            info_input.kind,
            method=method,
            rank=rank,
            verbose=verbose,
        )
    elif mode == "adhoc":
        info_input = find_info_input_path(config, **entities)
        cov = _compute_ad_hoc_covariance(info_input.path, info_input.kind)
    else:
        return NoiseCovarianceResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(cov_path),
            status=f"unsupported_mode_{mode}",
            mode=mode,
            data_input=str(overview["data_input"]),
            message=f"Writing covariance for mode {mode!r} is not implemented yet.",
        )

    cov_path.parent.mkdir(parents=True, exist_ok=True)
    mne.write_cov(
        cov_path,
        cov,
        overwrite=on_existing == "overwrite",
        verbose=verbose,
    )

    return NoiseCovarianceResult(
        subject=_subject_label(subject),
        session=session,
        task=task,
        run=run,
        path=str(cov_path),
        status="written",
        mode=mode,
        data_input=str(overview["data_input"]),
    )


def write_noise_covariances_for_recordings(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    mode: str | None = None,
    method: str | list[str] | None = "empirical",
    rank: str | dict[str, int] | None = None,
    verbose: bool | str | int | None = True,
) -> list[NoiseCovarianceResult]:
    """Create noise covariance matrices for multiple recordings."""
    results = []
    mode = _noise_cov_mode(config, mode)

    for recording in recordings:
        try:
            result = write_noise_covariance_for_recording(
                config,
                recording,
                on_existing=on_existing,
                mode=mode,
                method=method,
                rank=rank,
                verbose=verbose,
            )
        except Exception as exc:  # noqa: BLE001 - batch notebooks should continue.
            entities = _recording_entities(recording)
            result = NoiseCovarianceResult(
                subject=_subject_label(str(entities["subject"])),
                session=entities["session"],
                task=entities["task"],
                run=entities["run"],
                path=str(make_noise_covariance_path(config, **entities, mode=mode)),
                status="failed",
                mode=mode,
                message=f"{type(exc).__name__}: {exc}",
            )

        results.append(result)

    return results


def noise_covariance_results_to_dataframe(
    results: Iterable[NoiseCovarianceResult],
) -> pd.DataFrame:
    """Convert noise-covariance results to a status table."""
    return pd.DataFrame([result.__dict__ for result in results])

@dataclass(frozen=True)
class InverseOperatorResult:
    """Result row for one inverse-operator job."""

    subject: str
    session: str | None
    task: str | None
    run: str | None
    path: str
    status: str
    info_input: str = ""
    info_input_kind: str = ""
    fwd_path: str = ""
    cov_path: str = ""
    message: str = ""


def inverse_operator_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    inverse_method: str | None = None,
) -> pd.DataFrame:
    """Summarize inverse-operator inputs and output status for recordings."""
    rows: list[dict[str, Any]] = []
    mode = _noise_cov_mode(config, noise_cov_mode)

    for recording in recordings:
        entities = _recording_entities(recording)
        subject = entities["subject"]
        session = entities["session"]
        task = entities["task"]
        run = entities["run"]

        info_input = find_info_input_path(config, **entities)
        fwd_path = make_forward_path(config, **entities, spacing=spacing)
        cov_path = make_noise_covariance_path(config, **entities, mode=mode)
        inverse_path = make_inverse_operator_path(
            config,
            **entities,
            spacing=spacing,
            noise_cov_mode=mode,
            inverse_method=inverse_method,
        )

        missing = []
        if info_input.status != "found":
            missing.append("info")
        if not fwd_path.exists():
            missing.append("forward")
        if not cov_path.exists():
            missing.append("covariance")

        if inverse_path.exists() and on_existing == "skip":
            status = "exists"
            message = "Inverse operator already exists."
        elif missing:
            status = "missing_" + "_".join(missing)
            message = "Missing required input(s): " + ", ".join(missing)
        else:
            status = "ready"
            message = info_input.message

        rows.append(
            {
                "subject": _subject_label(subject),
                "session": session,
                "task": task,
                "run": run,
                "status": status,
                "message": message,
                "info_input_kind": info_input.kind,
                "info_input_exists": info_input.status == "found",
                "info_input": info_input.path,
                "fwd_exists": fwd_path.exists(),
                "fwd_path": str(fwd_path),
                "cov_exists": cov_path.exists(),
                "cov_path": str(cov_path),
                "inverse_exists": inverse_path.exists(),
                "inverse_path": str(inverse_path),
                "overwrite": on_existing == "overwrite",
                "spacing": _source_spacing(config, spacing),
                "noise_cov_mode": mode,
                "inverse_method": inverse_method or config.source.inverse_method,
            }
        )

    return pd.DataFrame(rows)


def write_inverse_operator_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    on_existing: ExistingOutputPolicy = "skip",
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    inverse_method: str | None = None,
    loose: float | str | None = 0.2,
    depth: float | None = 0.8,
    rank: str | dict[str, int] | None = None,
    verbose: bool | str | int | None = True,
) -> InverseOperatorResult:
    """Create and write an inverse operator for one recording."""
    entities = _recording_entities(recording)
    subject = entities["subject"]
    session = entities["session"]
    task = entities["task"]
    run = entities["run"]
    mode = _noise_cov_mode(config, noise_cov_mode)

    inverse_path = make_inverse_operator_path(
        config,
        **entities,
        spacing=spacing,
        noise_cov_mode=mode,
        inverse_method=inverse_method,
    )

    if inverse_path.exists() and on_existing == "skip":
        return InverseOperatorResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(inverse_path),
            status="skipped_existing",
            message="Inverse operator already exists.",
        )

    overview = inverse_operator_input_overview_to_dataframe(
        config,
        [recording],
        on_existing="overwrite",
        spacing=spacing,
        noise_cov_mode=mode,
        inverse_method=inverse_method,
    ).iloc[0]

    if overview["status"] != "ready":
        return InverseOperatorResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(inverse_path),
            status=str(overview["status"]),
            info_input=str(overview["info_input"]),
            info_input_kind=str(overview["info_input_kind"]),
            fwd_path=str(overview["fwd_path"]),
            cov_path=str(overview["cov_path"]),
            message=str(overview["message"]),
        )

    info = _read_info_from_input(
        overview["info_input"],
        str(overview["info_input_kind"]),
    )
    fwd = mne.read_forward_solution(overview["fwd_path"], verbose=verbose)
    noise_cov = mne.read_cov(overview["cov_path"], verbose=verbose)

    inverse_operator = mne.minimum_norm.make_inverse_operator(
        info=info,
        forward=fwd,
        noise_cov=noise_cov,
        loose=loose,
        depth=depth,
        rank=rank,
        verbose=verbose,
    )

    inverse_path.parent.mkdir(parents=True, exist_ok=True)
    mne.minimum_norm.write_inverse_operator(
        inverse_path,
        inverse_operator,
        overwrite=on_existing == "overwrite" or not inverse_path.exists(),
        verbose=verbose,
    )

    return InverseOperatorResult(
        subject=_subject_label(subject),
        session=session,
        task=task,
        run=run,
        path=str(inverse_path),
        status="written",
        info_input=str(overview["info_input"]),
        info_input_kind=str(overview["info_input_kind"]),
        fwd_path=str(overview["fwd_path"]),
        cov_path=str(overview["cov_path"]),
    )


def write_inverse_operators_for_recordings(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    inverse_method: str | None = None,
    loose: float | str | None = 0.2,
    depth: float | None = 0.8,
    rank: str | dict[str, int] | None = None,
    verbose: bool | str | int | None = True,
) -> list[InverseOperatorResult]:
    """Create inverse operators for multiple recordings."""
    results = []
    mode = _noise_cov_mode(config, noise_cov_mode)

    for recording in recordings:
        try:
            result = write_inverse_operator_for_recording(
                config,
                recording,
                on_existing=on_existing,
                spacing=spacing,
                noise_cov_mode=mode,
                inverse_method=inverse_method,
                loose=loose,
                depth=depth,
                rank=rank,
                verbose=verbose,
            )
        except Exception as exc:  # noqa: BLE001 - batch notebooks should continue.
            entities = _recording_entities(recording)
            result = InverseOperatorResult(
                subject=_subject_label(str(entities["subject"])),
                session=entities["session"],
                task=entities["task"],
                run=entities["run"],
                path=str(
                    make_inverse_operator_path(
                        config,
                        **entities,
                        spacing=spacing,
                        noise_cov_mode=mode,
                        inverse_method=inverse_method,
                    )
                ),
                status="failed",
                message=f"{type(exc).__name__}: {exc}",
            )

        results.append(result)

    return results


def inverse_operator_results_to_dataframe(
    results: Iterable[InverseOperatorResult],
) -> pd.DataFrame:
    """Convert inverse-operator results to a status table."""
    return pd.DataFrame([result.__dict__ for result in results])


def inverse_operator_qc_to_dataframe(
    inverse_results: pd.DataFrame | Iterable[InverseOperatorResult | dict[str, Any]],
    *,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Read inverse-operator files and summarize basic QC metadata."""
    if isinstance(inverse_results, pd.DataFrame):
        table = inverse_results.copy()
    else:
        rows = []
        for result in inverse_results:
            if isinstance(result, InverseOperatorResult):
                rows.append(result.__dict__)
            else:
                rows.append(dict(result))
        table = pd.DataFrame(rows)

    if table.empty:
        return pd.DataFrame(
            [{"status": "no_results", "message": "No inverse-operator results to inspect."}]
        )

    if "path" not in table.columns:
        raise KeyError(f"inverse_results must contain a 'path' column. Columns: {list(table.columns)}")

    candidate_table = table.copy()
    if max_rows is not None:
        candidate_table = candidate_table.head(max_rows)

    rows: list[dict[str, Any]] = []

    for _, row in candidate_table.iterrows():
        path = Path(row["path"])

        try:
            if not path.exists():
                raise FileNotFoundError(path)

            inverse_operator = mne.minimum_norm.read_inverse_operator(
                path,
                verbose=False,
            )

            rows.append(
                {
                    "subject": row.get("subject"),
                    "session": row.get("session"),
                    "task": row.get("task"),
                    "run": row.get("run"),
                    "status": "ok",
                    "path": str(path),
                    "nsource": inverse_operator.get("nsource"),
                    "nchan": inverse_operator.get("nchan"),
                    "source_ori": inverse_operator.get("source_ori"),
                    "coord_frame": inverse_operator.get("coord_frame"),
                    "noise_cov_dim": inverse_operator.get("noise_cov", {}).get("dim"),
                    "message": "",
                }
            )

        except Exception as exc:  # noqa: BLE001 - QC table should report all rows.
            rows.append(
                {
                    "subject": row.get("subject"),
                    "session": row.get("session"),
                    "task": row.get("task"),
                    "run": row.get("run"),
                    "status": "failed",
                    "path": str(path),
                    "nsource": None,
                    "nchan": None,
                    "source_ori": None,
                    "coord_frame": None,
                    "noise_cov_dim": None,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )

    return pd.DataFrame(rows)



@dataclass(frozen=True)
class SourceEstimateResult:
    """Result row for one source-estimate job."""

    subject: str
    session: str | None
    task: str | None
    run: str | None
    condition: str
    path: str
    status: str
    apply_to: str = ""
    method: str = ""
    lambda2: float | None = None
    evoked_path: str = ""
    inverse_path: str = ""
    message: str = ""


def _apply_inverse_config(config: PipelineConfig) -> Any:
    """Return the apply-inverse config, with backward-compatible defaults."""
    source = getattr(config, "source", None)
    apply_inverse = getattr(source, "apply_inverse", None)

    if apply_inverse is not None:
        return apply_inverse

    # Backward compatibility for old PipelineConfig objects.
    @dataclass(frozen=True)
    class _Defaults:
        apply_to: str = "evoked"
        method: str = str(getattr(source, "inverse_method", "dSPM"))
        snr: float = 3.0
        lambda2: float | None = None
        pick_conditions: tuple[str, ...] | Literal["all"] = "all"
        save_stcs: bool = True
        stc_format: str = "h5"

    return _Defaults()


def apply_inverse_config_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """Return effective apply-inverse settings as a one-row table."""
    apply_config = _apply_inverse_config(config)
    snr = float(getattr(apply_config, "snr", 3.0))
    lambda2 = getattr(apply_config, "lambda2", None)
    if lambda2 is None:
        lambda2 = 1.0 / snr**2

    return pd.DataFrame(
        [
            {
                "apply_to": getattr(apply_config, "apply_to", "evoked"),
                "method": getattr(apply_config, "method", config.source.inverse_method),
                "snr": snr,
                "lambda2": lambda2,
                "pick_conditions": getattr(apply_config, "pick_conditions", "all"),
                "save_stcs": getattr(apply_config, "save_stcs", True),
                "stc_format": getattr(apply_config, "stc_format", "h5"),
            }
        ]
    )


def _effective_apply_inverse_method(
    config: PipelineConfig,
    method: str | None = None,
) -> str:
    """Return the method used when applying an inverse operator."""
    if method is not None:
        return str(method)
    return str(getattr(_apply_inverse_config(config), "method", config.source.inverse_method))


def _effective_apply_inverse_lambda2(
    config: PipelineConfig,
    lambda2: float | None = None,
    snr: float | None = None,
) -> float:
    """Return lambda2, preferring explicit lambda2 over SNR-derived values."""
    if lambda2 is not None:
        return float(lambda2)

    apply_config = _apply_inverse_config(config)
    configured_lambda2 = getattr(apply_config, "lambda2", None)
    if configured_lambda2 is not None:
        return float(configured_lambda2)

    effective_snr = float(snr if snr is not None else getattr(apply_config, "snr", 3.0))
    return 1.0 / effective_snr**2


def _effective_pick_conditions(
    config: PipelineConfig,
    pick_conditions: tuple[str, ...] | list[str] | str | None = None,
) -> tuple[str, ...] | Literal["all"]:
    """Return selected evoked condition descriptions."""
    if pick_conditions is None:
        configured = getattr(_apply_inverse_config(config), "pick_conditions", "all")
    else:
        configured = pick_conditions

    if configured == "all":
        return "all"

    if isinstance(configured, str):
        return (configured,)

    return tuple(str(item) for item in configured)


def _condition_from_evoked_path(path: str | Path) -> str:
    """Parse the desc entity from a condition-specific evoked filename."""
    path = Path(path)
    condition = _parse_entity_from_filename(path, "desc")
    if condition:
        return condition
    return path.stem


def find_evoked_inputs_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    pick_conditions: tuple[str, ...] | list[str] | str | None = None,
) -> list[dict[str, Any]]:
    """Find condition-specific evoked files for one recording."""
    entities = _recording_entities(recording)
    evoked_paths = _evoked_candidates(config, **entities)
    selected_conditions = _effective_pick_conditions(config, pick_conditions)

    rows: list[dict[str, Any]] = []
    for evoked_path in evoked_paths:
        condition = _condition_from_evoked_path(evoked_path)
        if selected_conditions != "all" and condition not in selected_conditions:
            continue
        rows.append({"condition": condition, "evoked_path": str(evoked_path)})

    return rows


def source_estimate_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    apply_to: Literal["evoked"] | None = None,
    method: str | None = None,
    pick_conditions: tuple[str, ...] | list[str] | str | None = None,
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
) -> pd.DataFrame:
    """Summarize apply-inverse inputs and output status for evoked STCs."""
    apply_config = _apply_inverse_config(config)
    effective_apply_to = apply_to or str(getattr(apply_config, "apply_to", "evoked"))
    if effective_apply_to != "evoked":
        raise NotImplementedError("Only apply_to='evoked' is currently implemented.")

    effective_method = _effective_apply_inverse_method(config, method)
    mode = _noise_cov_mode(config, noise_cov_mode)
    rows: list[dict[str, Any]] = []

    for recording in recordings:
        entities = _recording_entities(recording)
        subject = entities["subject"]
        session = entities["session"]
        task = entities["task"]
        run = entities["run"]

        inverse_path = make_inverse_operator_path(
            config,
            **entities,
            spacing=spacing,
            noise_cov_mode=mode,
            inverse_method=effective_method,
        )
        evoked_inputs = find_evoked_inputs_for_recording(
            config,
            recording,
            pick_conditions=pick_conditions,
        )

        if not evoked_inputs:
            rows.append(
                {
                    "subject": _subject_label(subject),
                    "session": session,
                    "task": task,
                    "run": run,
                    "condition": "",
                    "status": "missing_evoked",
                    "message": "No matching condition-specific evoked files were found.",
                    "apply_to": effective_apply_to,
                    "method": effective_method,
                    "evoked_exists": False,
                    "evoked_path": "",
                    "inverse_exists": inverse_path.exists(),
                    "inverse_path": str(inverse_path),
                    "stc_exists": False,
                    "stc_path": "",
                    "overwrite": on_existing == "overwrite",
                }
            )
            continue

        for evoked_input in evoked_inputs:
            condition = evoked_input["condition"]
            evoked_path = Path(evoked_input["evoked_path"])
            stc_path = make_evoked_source_estimate_path(
                config,
                **entities,
                condition=condition,
                inverse_method=effective_method,
            )

            missing = []
            if not evoked_path.exists():
                missing.append("evoked")
            if not inverse_path.exists():
                missing.append("inverse")

            if stc_path.exists() and on_existing == "skip":
                status = "exists"
                message = "Source estimate already exists."
            elif missing:
                status = "missing_" + "_".join(missing)
                message = "Missing required input(s): " + ", ".join(missing)
            else:
                status = "ready"
                message = ""

            rows.append(
                {
                    "subject": _subject_label(subject),
                    "session": session,
                    "task": task,
                    "run": run,
                    "condition": condition,
                    "status": status,
                    "message": message,
                    "apply_to": effective_apply_to,
                    "method": effective_method,
                    "evoked_exists": evoked_path.exists(),
                    "evoked_path": str(evoked_path),
                    "inverse_exists": inverse_path.exists(),
                    "inverse_path": str(inverse_path),
                    "stc_exists": stc_path.exists(),
                    "stc_path": str(stc_path),
                    "overwrite": on_existing == "overwrite",
                }
            )

    return pd.DataFrame(rows)


def apply_inverse_to_evoked_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    condition: str,
    evoked_path: str | Path | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    method: str | None = None,
    lambda2: float | None = None,
    snr: float | None = None,
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    pick_ori: str | None = None,
    save_stc: bool | None = None,
    verbose: bool | str | int | None = True,
) -> SourceEstimateResult:
    """Apply an inverse operator to one condition-specific evoked file."""
    entities = _recording_entities(recording)
    subject = entities["subject"]
    session = entities["session"]
    task = entities["task"]
    run = entities["run"]
    effective_method = _effective_apply_inverse_method(config, method)
    effective_lambda2 = _effective_apply_inverse_lambda2(config, lambda2, snr)
    mode = _noise_cov_mode(config, noise_cov_mode)
    save = bool(getattr(_apply_inverse_config(config), "save_stcs", True) if save_stc is None else save_stc)

    inverse_path = make_inverse_operator_path(
        config,
        **entities,
        spacing=spacing,
        noise_cov_mode=mode,
        inverse_method=effective_method,
    )
    stc_path = make_evoked_source_estimate_path(
        config,
        **entities,
        condition=condition,
        inverse_method=effective_method,
    )

    if evoked_path is None:
        candidates = find_evoked_inputs_for_recording(config, recording, pick_conditions=(condition,))
        if not candidates:
            return SourceEstimateResult(
                subject=_subject_label(subject),
                session=session,
                task=task,
                run=run,
                condition=condition,
                path=str(stc_path),
                status="missing_evoked",
                apply_to="evoked",
                method=effective_method,
                lambda2=effective_lambda2,
                inverse_path=str(inverse_path),
                message="No matching evoked file was found.",
            )
        evoked_path = candidates[0]["evoked_path"]

    evoked_path = Path(evoked_path)

    if stc_path.exists() and on_existing == "skip":
        return SourceEstimateResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            condition=condition,
            path=str(stc_path),
            status="skipped_existing",
            apply_to="evoked",
            method=effective_method,
            lambda2=effective_lambda2,
            evoked_path=str(evoked_path),
            inverse_path=str(inverse_path),
            message="Source estimate already exists.",
        )

    missing = []
    if not evoked_path.exists():
        missing.append("evoked")
    if not inverse_path.exists():
        missing.append("inverse")
    if missing:
        return SourceEstimateResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            condition=condition,
            path=str(stc_path),
            status="missing_" + "_".join(missing),
            apply_to="evoked",
            method=effective_method,
            lambda2=effective_lambda2,
            evoked_path=str(evoked_path),
            inverse_path=str(inverse_path),
            message="Missing required input(s): " + ", ".join(missing),
        )

    evoked = mne.read_evokeds(evoked_path, condition=0, verbose=verbose)
    inverse_operator = mne.minimum_norm.read_inverse_operator(inverse_path, verbose=verbose)

    stc = mne.minimum_norm.apply_inverse(
        evoked,
        inverse_operator,
        lambda2=effective_lambda2,
        method=effective_method,
        pick_ori=pick_ori,
        verbose=verbose,
    )

    if save:
        stc_path.parent.mkdir(parents=True, exist_ok=True)
        stc.save(
            stc_path,
            ftype="h5",
            overwrite=on_existing == "overwrite" or not stc_path.exists(),
        )
        status = "written"
    else:
        status = "computed_not_saved"

    return SourceEstimateResult(
        subject=_subject_label(subject),
        session=session,
        task=task,
        run=run,
        condition=condition,
        path=str(stc_path),
        status=status,
        apply_to="evoked",
        method=effective_method,
        lambda2=effective_lambda2,
        evoked_path=str(evoked_path),
        inverse_path=str(inverse_path),
    )


def apply_inverse_to_evokeds_for_recordings(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    method: str | None = None,
    lambda2: float | None = None,
    snr: float | None = None,
    pick_conditions: tuple[str, ...] | list[str] | str | None = None,
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    pick_ori: str | None = None,
    save_stcs: bool | None = None,
    verbose: bool | str | int | None = True,
) -> list[SourceEstimateResult]:
    """Apply inverse operators to all selected condition-specific evokeds."""
    results: list[SourceEstimateResult] = []
    effective_method = _effective_apply_inverse_method(config, method)

    overview = source_estimate_input_overview_to_dataframe(
        config,
        recordings,
        on_existing=on_existing,
        apply_to="evoked",
        method=effective_method,
        pick_conditions=pick_conditions,
        spacing=spacing,
        noise_cov_mode=noise_cov_mode,
    )

    if overview.empty:
        return results

    ready_or_existing = overview[overview["status"].isin(["ready", "exists"])]

    # Return missing rows as status results too, so batch notebooks can report them.
    for _, row in overview[~overview.index.isin(ready_or_existing.index)].iterrows():
        results.append(
            SourceEstimateResult(
                subject=str(row.get("subject", "")),
                session=row.get("session"),
                task=row.get("task"),
                run=row.get("run"),
                condition=str(row.get("condition", "")),
                path=str(row.get("stc_path", "")),
                status=str(row.get("status", "")),
                apply_to="evoked",
                method=effective_method,
                lambda2=_effective_apply_inverse_lambda2(config, lambda2, snr),
                evoked_path=str(row.get("evoked_path", "")),
                inverse_path=str(row.get("inverse_path", "")),
                message=str(row.get("message", "")),
            )
        )

    for _, row in ready_or_existing.iterrows():
        recording = {
            "subject": str(row["subject"]).removeprefix("sub-"),
            "session": row.get("session") if pd.notna(row.get("session")) else None,
            "task": row.get("task") if pd.notna(row.get("task")) else None,
            "run": row.get("run") if pd.notna(row.get("run")) else None,
        }
        try:
            result = apply_inverse_to_evoked_for_recording(
                config,
                recording,
                condition=str(row["condition"]),
                evoked_path=row["evoked_path"],
                on_existing=on_existing,
                method=effective_method,
                lambda2=lambda2,
                snr=snr,
                spacing=spacing,
                noise_cov_mode=noise_cov_mode,
                pick_ori=pick_ori,
                save_stc=save_stcs,
                verbose=verbose,
            )
        except Exception as exc:  # noqa: BLE001 - batch notebooks should continue.
            result = SourceEstimateResult(
                subject=str(row.get("subject", "")),
                session=row.get("session"),
                task=row.get("task"),
                run=row.get("run"),
                condition=str(row.get("condition", "")),
                path=str(row.get("stc_path", "")),
                status="failed",
                apply_to="evoked",
                method=effective_method,
                lambda2=_effective_apply_inverse_lambda2(config, lambda2, snr),
                evoked_path=str(row.get("evoked_path", "")),
                inverse_path=str(row.get("inverse_path", "")),
                message=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)

    return results


def source_estimate_results_to_dataframe(
    results: Iterable[SourceEstimateResult],
) -> pd.DataFrame:
    """Convert source-estimate results to a status table."""
    return pd.DataFrame([result.__dict__ for result in results])


def source_estimate_qc_to_dataframe(
    source_results: pd.DataFrame | Iterable[SourceEstimateResult | dict[str, Any]],
    *,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Read saved source estimates and summarize basic QC metadata."""
    if isinstance(source_results, pd.DataFrame):
        table = source_results.copy()
    else:
        rows = []
        for result in source_results:
            if isinstance(result, SourceEstimateResult):
                rows.append(result.__dict__)
            else:
                rows.append(dict(result))
        table = pd.DataFrame(rows)

    if table.empty:
        return pd.DataFrame(
            [{"status": "no_results", "message": "No source-estimate results to inspect."}]
        )

    if "path" not in table.columns:
        raise KeyError(f"source_results must contain a 'path' column. Columns: {list(table.columns)}")

    candidate_table = table.copy()
    if max_rows is not None:
        candidate_table = candidate_table.head(max_rows)

    rows: list[dict[str, Any]] = []

    for _, row in candidate_table.iterrows():
        path = Path(row["path"])
        try:
            if not path.exists():
                raise FileNotFoundError(path)

            stc = mne.read_source_estimate(path, subject=_subject_label(str(row.get("subject", ""))))
            data = stc.data

            rows.append(
                {
                    "subject": row.get("subject"),
                    "session": row.get("session"),
                    "task": row.get("task"),
                    "run": row.get("run"),
                    "condition": row.get("condition"),
                    "status": "ok",
                    "path": str(path),
                    "n_vertices_lh": len(stc.vertices[0]) if len(stc.vertices) > 0 else None,
                    "n_vertices_rh": len(stc.vertices[1]) if len(stc.vertices) > 1 else None,
                    "n_times": len(stc.times),
                    "tmin": float(stc.times[0]) if len(stc.times) else None,
                    "tmax": float(stc.times[-1]) if len(stc.times) else None,
                    "max_abs": float(abs(data).max()) if data.size else None,
                    "mean_abs": float(abs(data).mean()) if data.size else None,
                    "message": "",
                }
            )

        except Exception as exc:  # noqa: BLE001 - QC table should report all rows.
            rows.append(
                {
                    "subject": row.get("subject"),
                    "session": row.get("session"),
                    "task": row.get("task"),
                    "run": row.get("run"),
                    "condition": row.get("condition"),
                    "status": "failed",
                    "path": str(path),
                    "n_vertices_lh": None,
                    "n_vertices_rh": None,
                    "n_times": None,
                    "tmin": None,
                    "tmax": None,
                    "max_abs": None,
                    "mean_abs": None,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )

    return pd.DataFrame(rows)


@dataclass(frozen=True)
class LabelTimeCourseResult:
    """Result row for one evoked label-time-course extraction job."""

    subject: str
    session: str | None
    task: str | None
    run: str | None
    condition: str
    path: str
    status: str
    stc_path: str = ""
    labels_path: str = ""
    times_path: str = ""
    parcellation: str = ""
    extract_mode: str = ""
    n_labels: int | None = None
    n_times: int | None = None
    message: str = ""


def label_time_course_config_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """Return effective label-time-course settings as a one-row table."""
    return pd.DataFrame(
        [
            {
                "parcellation": config.source.parcellation,
                "extract_mode": config.source.extract_mode,
                "target_labels": config.source.target_labels,
                "inverse_method": config.source.inverse_method,
                "source_spacing": _source_spacing(config),
                "apply_inverse_method": _effective_apply_inverse_method(config, None),
                "apply_inverse_pick_conditions": _effective_pick_conditions(config, None),
            }
        ]
    )


def _label_sidecar_paths(path: str | Path) -> tuple[Path, Path]:
    """Return labels and times sidecar paths for one label-time-course table."""
    path = Path(path)
    name = path.name
    if name.endswith("-ltc.tsv"):
        labels_name = name.removesuffix("-ltc.tsv") + "-labels.tsv"
        times_name = name.removesuffix("-ltc.tsv") + "-times.tsv"
    else:
        labels_name = path.stem + "_labels.tsv"
        times_name = path.stem + "_times.tsv"
    return path.with_name(labels_name), path.with_name(times_name)


def _source_estimate_candidates(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> list[Path]:
    """Return matching evoked source-estimate files for one recording."""
    directory = derivative_directory(
        config,
        subject=subject,
        session=session,
        kind="source_estimates",
    )

    subject_label = _subject_label(subject)
    parts = [subject_label]
    if session is not None:
        parts.append(f"ses-{session}")
    if task is not None:
        parts.append(f"task-{task}")
    if run is not None:
        parts.append(f"run-{run}")

    pattern = "_".join(parts + ["space-source_desc-*-stc.h5"])
    return sorted(directory.glob(pattern))


def _condition_from_source_estimate_path(
    path: str | Path,
    *,
    inverse_method: str | None = None,
) -> str:
    """Parse the condition from a source-estimate path.

    Source-estimate desc labels are written as ``<condition><method>``. This
    function removes the method suffix when possible so the label-time-course
    output uses the original condition entity.
    """
    desc = _parse_entity_from_filename(Path(path), "desc") or Path(path).stem
    method = sanitize_bids_label(inverse_method or "")
    if method and desc.lower().endswith(method.lower()):
        return desc[: -len(method)]
    return desc


def _effective_target_labels(
    config: PipelineConfig,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
) -> tuple[str, ...] | None:
    """Return effective target-label selection."""
    configured = config.source.target_labels if target_labels is None else target_labels
    if configured is None:
        return None
    if isinstance(configured, str):
        return (configured,)
    return tuple(str(label) for label in configured)


def _load_labels_for_subject(
    config: PipelineConfig,
    *,
    subject: str,
    parcellation: str | None = None,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
) -> list[mne.Label]:
    """Load and optionally filter cortical labels for one subject."""
    subject_label = _subject_label(subject)
    subjects_dir = _subjects_dir(config)
    parc = str(parcellation or config.source.parcellation)

    labels = mne.read_labels_from_annot(
        subject=subject_label,
        parc=parc,
        subjects_dir=subjects_dir,
        verbose=False,
    )

    selected = _effective_target_labels(config, target_labels)
    if selected is None:
        return labels

    selected_set = set(selected)
    filtered = []
    for label in labels:
        name = str(label.name)
        bare = name.rsplit("-", 1)[0]
        if name in selected_set or bare in selected_set:
            filtered.append(label)

    return filtered


def find_source_estimate_inputs_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    method: str | None = None,
    pick_conditions: tuple[str, ...] | list[str] | str | None = None,
) -> list[dict[str, Any]]:
    """Find saved evoked source estimates for one recording."""
    entities = _recording_entities(recording)
    effective_method = _effective_apply_inverse_method(config, method)
    selected_conditions = _effective_pick_conditions(config, pick_conditions)

    rows: list[dict[str, Any]] = []
    for stc_path in _source_estimate_candidates(config, **entities):
        condition = _condition_from_source_estimate_path(
            stc_path,
            inverse_method=effective_method,
        )
        if selected_conditions != "all" and condition not in selected_conditions:
            continue
        rows.append({"condition": condition, "stc_path": str(stc_path)})

    return rows


def label_time_course_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    method: str | None = None,
    pick_conditions: tuple[str, ...] | list[str] | str | None = None,
    parcellation: str | None = None,
    extract_mode: str | None = None,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
) -> pd.DataFrame:
    """Summarize source-estimate inputs and label-time-course outputs."""
    rows: list[dict[str, Any]] = []
    effective_method = _effective_apply_inverse_method(config, method)
    effective_parc = str(parcellation or config.source.parcellation)
    effective_mode = str(extract_mode or config.source.extract_mode)
    effective_targets = _effective_target_labels(config, target_labels)

    for recording in recordings:
        entities = _recording_entities(recording)
        subject = entities["subject"]
        session = entities["session"]
        task = entities["task"]
        run = entities["run"]

        stc_inputs = find_source_estimate_inputs_for_recording(
            config,
            recording,
            method=effective_method,
            pick_conditions=pick_conditions,
        )

        labels_status = "found"
        labels_message = ""
        n_labels: int | None = None
        try:
            labels = _load_labels_for_subject(
                config,
                subject=subject,
                parcellation=effective_parc,
                target_labels=effective_targets,
            )
            n_labels = len(labels)
            if not labels:
                labels_status = "missing"
                labels_message = "No labels remained after filtering."
        except Exception as exc:  # noqa: BLE001 - overview should report missing labels.
            labels_status = "missing"
            labels_message = f"{type(exc).__name__}: {exc}"

        if not stc_inputs:
            rows.append(
                {
                    "subject": _subject_label(subject),
                    "session": session,
                    "task": task,
                    "run": run,
                    "condition": None,
                    "status": "missing_stc",
                    "message": "No matching source-estimate files were found.",
                    "stc_exists": False,
                    "stc_path": "",
                    "labels_status": labels_status,
                    "labels_message": labels_message,
                    "n_labels": n_labels,
                    "ltc_exists": False,
                    "ltc_path": "",
                    "labels_path": "",
                    "times_path": "",
                    "parcellation": effective_parc,
                    "extract_mode": effective_mode,
                    "target_labels": effective_targets,
                    "overwrite": on_existing == "overwrite",
                }
            )
            continue

        for stc_input in stc_inputs:
            condition = str(stc_input["condition"])
            stc_path = Path(stc_input["stc_path"])
            ltc_path = make_evoked_label_time_course_path(
                config,
                **entities,
                condition=condition,
                parcellation=effective_parc,
                inverse_method=effective_method,
                extension=".tsv",
            )
            labels_path, times_path = _label_sidecar_paths(ltc_path)

            missing = []
            if not stc_path.exists():
                missing.append("stc")
            if labels_status != "found":
                missing.append("labels")

            if ltc_path.exists() and on_existing == "skip":
                status = "exists"
                message = "Label time course already exists."
            elif missing:
                status = "missing_" + "_".join(missing)
                message = "Missing required input(s): " + ", ".join(missing)
                if labels_message:
                    message += f"; labels: {labels_message}"
            else:
                status = "ready"
                message = labels_message

            rows.append(
                {
                    "subject": _subject_label(subject),
                    "session": session,
                    "task": task,
                    "run": run,
                    "condition": condition,
                    "status": status,
                    "message": message,
                    "stc_exists": stc_path.exists(),
                    "stc_path": str(stc_path),
                    "labels_status": labels_status,
                    "labels_message": labels_message,
                    "n_labels": n_labels,
                    "ltc_exists": ltc_path.exists(),
                    "ltc_path": str(ltc_path),
                    "labels_path": str(labels_path),
                    "times_path": str(times_path),
                    "parcellation": effective_parc,
                    "extract_mode": effective_mode,
                    "target_labels": effective_targets,
                    "overwrite": on_existing == "overwrite",
                }
            )

    return pd.DataFrame(rows)


def _write_label_time_course_tables(
    *,
    data: np.ndarray,
    times: np.ndarray,
    labels: list[mne.Label],
    ltc_path: Path,
    labels_path: Path,
    times_path: Path,
) -> None:
    """Write label-time-course data and compact sidecar tables."""
    ltc_path.parent.mkdir(parents=True, exist_ok=True)

    time_columns = [f"t={time:.6f}" for time in times]
    label_names = [label.name for label in labels]
    hemis = [getattr(label, "hemi", "") for label in labels]

    table = pd.DataFrame(data, columns=time_columns)
    table.insert(0, "hemi", hemis)
    table.insert(0, "label", label_names)
    table.to_csv(ltc_path, sep="\t", index=False)

    pd.DataFrame(
        {
            "label": label_names,
            "hemi": hemis,
            "n_vertices": [len(label.vertices) for label in labels],
        }
    ).to_csv(labels_path, sep="\t", index=False)

    pd.DataFrame({"time_index": range(len(times)), "time_s": times}).to_csv(
        times_path,
        sep="\t",
        index=False,
    )


def extract_label_time_courses_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    condition: str,
    stc_path: str | Path | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    method: str | None = None,
    parcellation: str | None = None,
    extract_mode: str | None = None,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
    spacing: str | None = None,
    allow_empty: bool | str = False,
    verbose: bool | str | int | None = True,
) -> LabelTimeCourseResult:
    """Extract and save label time courses for one evoked source estimate."""
    entities = _recording_entities(recording)
    subject = entities["subject"]
    session = entities["session"]
    task = entities["task"]
    run = entities["run"]
    effective_method = _effective_apply_inverse_method(config, method)
    effective_parc = str(parcellation or config.source.parcellation)
    effective_mode = str(extract_mode or config.source.extract_mode)
    effective_targets = _effective_target_labels(config, target_labels)

    if stc_path is None:
        stc_path = make_evoked_source_estimate_path(
            config,
            **entities,
            condition=condition,
            inverse_method=effective_method,
        )
    stc_path = Path(stc_path)

    ltc_path = make_evoked_label_time_course_path(
        config,
        **entities,
        condition=condition,
        parcellation=effective_parc,
        inverse_method=effective_method,
        extension=".tsv",
    )
    labels_path, times_path = _label_sidecar_paths(ltc_path)

    if ltc_path.exists() and on_existing == "skip":
        return LabelTimeCourseResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            condition=condition,
            path=str(ltc_path),
            status="skipped_existing",
            stc_path=str(stc_path),
            labels_path=str(labels_path),
            times_path=str(times_path),
            parcellation=effective_parc,
            extract_mode=effective_mode,
            message="Label time course already exists.",
        )

    if not stc_path.exists():
        return LabelTimeCourseResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            condition=condition,
            path=str(ltc_path),
            status="missing_stc",
            stc_path=str(stc_path),
            labels_path=str(labels_path),
            times_path=str(times_path),
            parcellation=effective_parc,
            extract_mode=effective_mode,
            message="Source estimate file does not exist.",
        )

    try:
        labels = _load_labels_for_subject(
            config,
            subject=subject,
            parcellation=effective_parc,
            target_labels=effective_targets,
        )
        if not labels:
            raise RuntimeError("No labels remained after filtering.")

        subjects_dir = _subjects_dir(config)
        src_path = source_space_path(
            subjects_dir,
            _subject_label(subject),
            spacing=_source_spacing(config, spacing),
        )
        if not src_path.exists():
            raise FileNotFoundError(src_path)

        stc = mne.read_source_estimate(
            stc_path,
            subject=_subject_label(subject),
        )
        src = mne.read_source_spaces(src_path, verbose=verbose)

        label_tc = mne.extract_label_time_course(
            stc,
            labels,
            src,
            mode=effective_mode,
            allow_empty=allow_empty,
            verbose=verbose,
        )
        label_tc = np.asarray(label_tc)

        _write_label_time_course_tables(
            data=label_tc,
            times=np.asarray(stc.times),
            labels=labels,
            ltc_path=ltc_path,
            labels_path=labels_path,
            times_path=times_path,
        )

        return LabelTimeCourseResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            condition=condition,
            path=str(ltc_path),
            status="written",
            stc_path=str(stc_path),
            labels_path=str(labels_path),
            times_path=str(times_path),
            parcellation=effective_parc,
            extract_mode=effective_mode,
            n_labels=int(label_tc.shape[0]),
            n_times=int(label_tc.shape[1]) if label_tc.ndim == 2 else None,
        )

    except Exception as exc:  # noqa: BLE001 - batch notebooks should continue.
        return LabelTimeCourseResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            condition=condition,
            path=str(ltc_path),
            status="failed",
            stc_path=str(stc_path),
            labels_path=str(labels_path),
            times_path=str(times_path),
            parcellation=effective_parc,
            extract_mode=effective_mode,
            message=f"{type(exc).__name__}: {exc}",
        )


def extract_label_time_courses_for_recordings(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    method: str | None = None,
    pick_conditions: tuple[str, ...] | list[str] | str | None = None,
    parcellation: str | None = None,
    extract_mode: str | None = None,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
    spacing: str | None = None,
    allow_empty: bool | str = False,
    verbose: bool | str | int | None = True,
) -> list[LabelTimeCourseResult]:
    """Extract label time courses for multiple recordings/source estimates."""
    overview = label_time_course_input_overview_to_dataframe(
        config,
        recordings,
        on_existing=on_existing,
        method=method,
        pick_conditions=pick_conditions,
        parcellation=parcellation,
        extract_mode=extract_mode,
        target_labels=target_labels,
    )

    results: list[LabelTimeCourseResult] = []

    for _, row in overview.iterrows():
        if row["status"] == "exists" and on_existing == "skip":
            results.append(
                LabelTimeCourseResult(
                    subject=str(row["subject"]),
                    session=row.get("session"),
                    task=row.get("task"),
                    run=row.get("run"),
                    condition=str(row.get("condition", "")),
                    path=str(row.get("ltc_path", "")),
                    status="skipped_existing",
                    stc_path=str(row.get("stc_path", "")),
                    labels_path=str(row.get("labels_path", "")),
                    times_path=str(row.get("times_path", "")),
                    parcellation=str(row.get("parcellation", "")),
                    extract_mode=str(row.get("extract_mode", "")),
                    n_labels=int(row["n_labels"]) if pd.notna(row.get("n_labels")) else None,
                    message="Label time course already exists.",
                )
            )
            continue

        if row["status"] != "ready":
            results.append(
                LabelTimeCourseResult(
                    subject=str(row["subject"]),
                    session=row.get("session"),
                    task=row.get("task"),
                    run=row.get("run"),
                    condition=str(row.get("condition", "")),
                    path=str(row.get("ltc_path", "")),
                    status=str(row["status"]),
                    stc_path=str(row.get("stc_path", "")),
                    labels_path=str(row.get("labels_path", "")),
                    times_path=str(row.get("times_path", "")),
                    parcellation=str(row.get("parcellation", "")),
                    extract_mode=str(row.get("extract_mode", "")),
                    n_labels=int(row["n_labels"]) if pd.notna(row.get("n_labels")) else None,
                    message=str(row.get("message", "")),
                )
            )
            continue

        recording: Recording = {
            "subject": str(row["subject"]).removeprefix("sub-"),
            "session": row.get("session"),
            "task": row.get("task"),
            "run": row.get("run"),
        }

        result = extract_label_time_courses_for_recording(
            config,
            recording,
            condition=str(row["condition"]),
            stc_path=row["stc_path"],
            on_existing=on_existing,
            method=method,
            parcellation=parcellation,
            extract_mode=extract_mode,
            target_labels=target_labels,
            spacing=spacing,
            allow_empty=allow_empty,
            verbose=verbose,
        )
        results.append(result)

    return results


def label_time_course_results_to_dataframe(
    results: Iterable[LabelTimeCourseResult],
) -> pd.DataFrame:
    """Convert label-time-course results to a status table."""
    return pd.DataFrame([result.__dict__ for result in results])


def label_time_course_qc_to_dataframe(
    label_time_course_results: pd.DataFrame | Iterable[LabelTimeCourseResult | dict[str, Any]],
    *,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Read label-time-course tables and summarize basic QC metadata."""
    if isinstance(label_time_course_results, pd.DataFrame):
        table = label_time_course_results.copy()
    else:
        rows = []
        for result in label_time_course_results:
            if isinstance(result, LabelTimeCourseResult):
                rows.append(result.__dict__)
            else:
                rows.append(dict(result))
        table = pd.DataFrame(rows)

    if table.empty:
        return pd.DataFrame(
            [{"status": "no_results", "message": "No label-time-course results to inspect."}]
        )

    if "path" not in table.columns:
        raise KeyError(
            f"label_time_course_results must contain a 'path' column. Columns: {list(table.columns)}"
        )

    candidate_table = table.copy()
    if max_rows is not None:
        candidate_table = candidate_table.head(max_rows)

    rows: list[dict[str, Any]] = []
    for _, row in candidate_table.iterrows():
        path = Path(row["path"])
        try:
            if not path.exists():
                raise FileNotFoundError(path)

            data = pd.read_csv(path, sep="\t")
            numeric = data.drop(columns=[col for col in ["label", "hemi"] if col in data.columns])
            values = numeric.to_numpy(dtype=float, copy=False)

            rows.append(
                {
                    "subject": row.get("subject"),
                    "session": row.get("session"),
                    "task": row.get("task"),
                    "run": row.get("run"),
                    "condition": row.get("condition"),
                    "status": "ok",
                    "path": str(path),
                    "n_labels": int(values.shape[0]) if values.ndim == 2 else None,
                    "n_times": int(values.shape[1]) if values.ndim == 2 else None,
                    "max_abs": float(np.abs(values).max()) if values.size else None,
                    "mean_abs": float(np.abs(values).mean()) if values.size else None,
                    "message": "",
                }
            )
        except Exception as exc:  # noqa: BLE001 - QC table should report all rows.
            rows.append(
                {
                    "subject": row.get("subject"),
                    "session": row.get("session"),
                    "task": row.get("task"),
                    "run": row.get("run"),
                    "condition": row.get("condition"),
                    "status": "failed",
                    "path": str(path),
                    "n_labels": None,
                    "n_times": None,
                    "max_abs": None,
                    "mean_abs": None,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )

    return pd.DataFrame(rows)


@dataclass(frozen=True)
class EpochLabelTimeCourseResult:
    """Result row for one epoch-wise label-time-course extraction job."""

    subject: str
    session: str | None
    task: str | None
    run: str | None
    path: str
    status: str
    epochs_path: str = ""
    inverse_path: str = ""
    labels_path: str = ""
    times_path: str = ""
    epochs_sidecar_path: str = ""
    parcellation: str = ""
    extract_mode: str = ""
    method: str = ""
    lambda2: float | None = None
    decim: int | None = None
    dtype: str = ""
    n_epochs: int | None = None
    n_labels: int | None = None
    n_times: int | None = None
    message: str = ""


def _label_time_courses_epochs_config(config: PipelineConfig) -> Any:
    """Return epoch-wise label-time-course config with backward-compatible defaults."""
    configured = getattr(getattr(config, "source", None), "label_time_courses_epochs", None)
    if configured is not None:
        return configured

    @dataclass(frozen=True)
    class _Defaults:
        enabled: bool = True
        method: str = str(getattr(getattr(config, "source", None), "inverse_method", "dSPM"))
        snr: float = 3.0
        lambda2: float | None = None
        parcellation: str | None = None
        extract_mode: str | None = None
        target_labels: tuple[str, ...] | None = None
        decim: int | None = 5
        tmin: float | None = None
        tmax: float | None = None
        dtype: str = "float32"
        save_format: str = "npy"

    return _Defaults()


def label_time_courses_epochs_config_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """Return effective epoch-wise label-time-course settings as a one-row table."""
    epoch_config = _label_time_courses_epochs_config(config)
    snr = float(getattr(epoch_config, "snr", 3.0))
    lambda2 = getattr(epoch_config, "lambda2", None)
    if lambda2 is None:
        lambda2 = 1.0 / snr**2

    return pd.DataFrame(
        [
            {
                "enabled": bool(getattr(epoch_config, "enabled", True)),
                "method": getattr(epoch_config, "method", config.source.inverse_method),
                "snr": snr,
                "lambda2": lambda2,
                "parcellation": getattr(epoch_config, "parcellation", None) or config.source.parcellation,
                "extract_mode": getattr(epoch_config, "extract_mode", None) or config.source.extract_mode,
                "target_labels": getattr(epoch_config, "target_labels", None) or config.source.target_labels,
                "decim": getattr(epoch_config, "decim", 5),
                "tmin": getattr(epoch_config, "tmin", None),
                "tmax": getattr(epoch_config, "tmax", None),
                "dtype": getattr(epoch_config, "dtype", "float32"),
                "save_format": getattr(epoch_config, "save_format", "npy"),
                "source_spacing": _source_spacing(config),
            }
        ]
    )


def _effective_epoch_ltc_settings(
    config: PipelineConfig,
    *,
    method: str | None = None,
    lambda2: float | None = None,
    snr: float | None = None,
    parcellation: str | None = None,
    extract_mode: str | None = None,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
    decim: int | None = None,
    tmin: float | None = None,
    tmax: float | None = None,
    dtype: str | None = None,
) -> dict[str, Any]:
    """Resolve epoch-wise label-time-course settings."""
    epoch_config = _label_time_courses_epochs_config(config)
    effective_method = str(method or getattr(epoch_config, "method", config.source.inverse_method))

    configured_lambda2 = getattr(epoch_config, "lambda2", None)
    if lambda2 is not None:
        effective_lambda2 = float(lambda2)
    elif configured_lambda2 is not None:
        effective_lambda2 = float(configured_lambda2)
    else:
        effective_snr = float(snr if snr is not None else getattr(epoch_config, "snr", 3.0))
        effective_lambda2 = 1.0 / effective_snr**2

    configured_targets = getattr(epoch_config, "target_labels", None)
    if target_labels is None and configured_targets is not None:
        effective_targets = configured_targets
    else:
        effective_targets = _effective_target_labels(config, target_labels)

    effective_decim = decim if decim is not None else getattr(epoch_config, "decim", 5)
    if effective_decim is not None:
        effective_decim = int(effective_decim)

    return {
        "method": effective_method,
        "lambda2": effective_lambda2,
        "parcellation": str(parcellation or getattr(epoch_config, "parcellation", None) or config.source.parcellation),
        "extract_mode": str(extract_mode or getattr(epoch_config, "extract_mode", None) or config.source.extract_mode),
        "target_labels": effective_targets,
        "decim": effective_decim,
        "tmin": tmin if tmin is not None else getattr(epoch_config, "tmin", None),
        "tmax": tmax if tmax is not None else getattr(epoch_config, "tmax", None),
        "dtype": str(dtype or getattr(epoch_config, "dtype", "float32")),
    }


def _epoch_label_time_course_sidecar_paths(path: str | Path) -> tuple[Path, Path, Path]:
    """Return labels, times, and epochs sidecar paths for an epoch-wise LTC array."""
    path = Path(path)
    name = path.name
    if name.endswith("-ltc.npy"):
        stem = name.removesuffix("-ltc.npy")
    else:
        stem = path.stem
    return (
        path.with_name(stem + "-labels.tsv"),
        path.with_name(stem + "-times.tsv"),
        path.with_name(stem + "-epochs.tsv"),
    )


def _write_epoch_label_time_course_array(
    *,
    data: np.ndarray,
    times: np.ndarray,
    labels: list[mne.Label],
    epochs: mne.Epochs,
    ltc_path: Path,
    labels_path: Path,
    times_path: Path,
    epochs_sidecar_path: Path,
) -> None:
    """Write epoch-wise label-time-course array and sidecar tables."""
    ltc_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(ltc_path, data)

    label_names = [label.name for label in labels]
    hemis = [getattr(label, "hemi", "") for label in labels]
    pd.DataFrame(
        {
            "label_index": range(len(labels)),
            "label": label_names,
            "hemi": hemis,
            "n_vertices": [len(label.vertices) for label in labels],
        }
    ).to_csv(labels_path, sep="\t", index=False)

    pd.DataFrame({"time_index": range(len(times)), "time_s": times}).to_csv(
        times_path,
        sep="\t",
        index=False,
    )

    event_id_lookup = {int(code): name for name, code in epochs.event_id.items()}
    event_codes = epochs.events[:, 2].astype(int) if len(epochs.events) else np.array([], dtype=int)
    event_names = [event_id_lookup.get(int(code), str(code)) for code in event_codes]
    selection = getattr(epochs, "selection", np.arange(len(event_codes)))

    epochs_table = pd.DataFrame(
        {
            "epoch_index": range(len(event_codes)),
            "original_epoch_index": selection,
            "event_sample": epochs.events[:, 0] if len(epochs.events) else [],
            "event_code": event_codes,
            "event_name": event_names,
        }
    )

    metadata = getattr(epochs, "metadata", None)
    if metadata is not None and len(metadata) == len(epochs_table):
        metadata = metadata.reset_index(drop=True)
        for column in metadata.columns:
            if column not in epochs_table.columns:
                epochs_table[column] = metadata[column]

    epochs_table.to_csv(epochs_sidecar_path, sep="\t", index=False)


def epoch_label_time_course_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    method: str | None = None,
    parcellation: str | None = None,
    extract_mode: str | None = None,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    decim: int | None = None,
    dtype: str | None = None,
) -> pd.DataFrame:
    """Summarize inputs/outputs for epoch-wise label-time-course extraction."""
    settings = _effective_epoch_ltc_settings(
        config,
        method=method,
        parcellation=parcellation,
        extract_mode=extract_mode,
        target_labels=target_labels,
        decim=decim,
        dtype=dtype,
    )
    mode = _noise_cov_mode(config, noise_cov_mode)
    rows: list[dict[str, Any]] = []

    for recording in recordings:
        entities = _recording_entities(recording)
        subject = entities["subject"]
        session = entities["session"]
        task = entities["task"]
        run = entities["run"]

        epochs_path = make_epochs_path(config, **entities, desc="cleaned")
        inverse_path = make_inverse_operator_path(
            config,
            **entities,
            spacing=spacing,
            noise_cov_mode=mode,
            inverse_method=settings["method"],
        )
        ltc_path = make_epoch_label_time_course_path(
            config,
            **entities,
            parcellation=settings["parcellation"],
            inverse_method=settings["method"],
            decim=settings["decim"],
            extension=".npy",
        )
        labels_path, times_path, epochs_sidecar_path = _epoch_label_time_course_sidecar_paths(ltc_path)

        labels_status = "found"
        labels_message = ""
        n_labels: int | None = None
        try:
            labels = _load_labels_for_subject(
                config,
                subject=subject,
                parcellation=settings["parcellation"],
                target_labels=settings["target_labels"],
            )
            n_labels = len(labels)
            if not labels:
                labels_status = "missing"
                labels_message = "No labels remained after filtering."
        except Exception as exc:  # noqa: BLE001 - overview should report missing labels.
            labels_status = "missing"
            labels_message = f"{type(exc).__name__}: {exc}"

        missing = []
        if not epochs_path.exists():
            missing.append("epochs")
        if not inverse_path.exists():
            missing.append("inverse")
        if labels_status != "found":
            missing.append("labels")

        if ltc_path.exists() and on_existing == "skip":
            status = "exists"
            message = "Epoch-wise label time courses already exist."
        elif missing:
            status = "missing_" + "_".join(missing)
            message = "Missing required input(s): " + ", ".join(missing)
            if labels_message:
                message += f"; labels: {labels_message}"
        else:
            status = "ready"
            message = labels_message

        rows.append(
            {
                "subject": _subject_label(subject),
                "session": session,
                "task": task,
                "run": run,
                "status": status,
                "message": message,
                "epochs_exists": epochs_path.exists(),
                "epochs_path": str(epochs_path),
                "inverse_exists": inverse_path.exists(),
                "inverse_path": str(inverse_path),
                "labels_status": labels_status,
                "labels_message": labels_message,
                "n_labels": n_labels,
                "ltc_exists": ltc_path.exists(),
                "ltc_path": str(ltc_path),
                "labels_path": str(labels_path),
                "times_path": str(times_path),
                "epochs_sidecar_path": str(epochs_sidecar_path),
                "method": settings["method"],
                "lambda2": settings["lambda2"],
                "parcellation": settings["parcellation"],
                "extract_mode": settings["extract_mode"],
                "target_labels": settings["target_labels"],
                "decim": settings["decim"],
                "dtype": settings["dtype"],
                "overwrite": on_existing == "overwrite",
            }
        )

    return pd.DataFrame(rows)


def extract_epoch_label_time_courses_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    epochs_path: str | Path | None = None,
    inverse_path: str | Path | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    method: str | None = None,
    lambda2: float | None = None,
    snr: float | None = None,
    parcellation: str | None = None,
    extract_mode: str | None = None,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    decim: int | None = None,
    tmin: float | None = None,
    tmax: float | None = None,
    dtype: str | None = None,
    allow_empty: bool | str = False,
    pick_ori: str | None = None,
    verbose: bool | str | int | None = True,
) -> EpochLabelTimeCourseResult:
    """Apply inverse epoch-wise and save compact label time courses."""
    entities = _recording_entities(recording)
    subject = entities["subject"]
    session = entities["session"]
    task = entities["task"]
    run = entities["run"]

    settings = _effective_epoch_ltc_settings(
        config,
        method=method,
        lambda2=lambda2,
        snr=snr,
        parcellation=parcellation,
        extract_mode=extract_mode,
        target_labels=target_labels,
        decim=decim,
        tmin=tmin,
        tmax=tmax,
        dtype=dtype,
    )
    mode = _noise_cov_mode(config, noise_cov_mode)

    if epochs_path is None:
        epochs_path = make_epochs_path(config, **entities, desc="cleaned")
    epochs_path = Path(epochs_path)

    if inverse_path is None:
        inverse_path = make_inverse_operator_path(
            config,
            **entities,
            spacing=spacing,
            noise_cov_mode=mode,
            inverse_method=settings["method"],
        )
    inverse_path = Path(inverse_path)

    ltc_path = make_epoch_label_time_course_path(
        config,
        **entities,
        parcellation=settings["parcellation"],
        inverse_method=settings["method"],
        decim=settings["decim"],
        extension=".npy",
    )
    labels_path, times_path, epochs_sidecar_path = _epoch_label_time_course_sidecar_paths(ltc_path)

    if ltc_path.exists() and on_existing == "skip":
        return EpochLabelTimeCourseResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(ltc_path),
            status="skipped_existing",
            epochs_path=str(epochs_path),
            inverse_path=str(inverse_path),
            labels_path=str(labels_path),
            times_path=str(times_path),
            epochs_sidecar_path=str(epochs_sidecar_path),
            parcellation=settings["parcellation"],
            extract_mode=settings["extract_mode"],
            method=settings["method"],
            lambda2=settings["lambda2"],
            decim=settings["decim"],
            dtype=settings["dtype"],
            message="Epoch-wise label time courses already exist.",
        )

    missing = []
    if not epochs_path.exists():
        missing.append("epochs")
    if not inverse_path.exists():
        missing.append("inverse")
    if missing:
        return EpochLabelTimeCourseResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(ltc_path),
            status="missing_" + "_".join(missing),
            epochs_path=str(epochs_path),
            inverse_path=str(inverse_path),
            labels_path=str(labels_path),
            times_path=str(times_path),
            epochs_sidecar_path=str(epochs_sidecar_path),
            parcellation=settings["parcellation"],
            extract_mode=settings["extract_mode"],
            method=settings["method"],
            lambda2=settings["lambda2"],
            decim=settings["decim"],
            dtype=settings["dtype"],
            message="Missing required input(s): " + ", ".join(missing),
        )

    try:
        labels = _load_labels_for_subject(
            config,
            subject=subject,
            parcellation=settings["parcellation"],
            target_labels=settings["target_labels"],
        )
        if not labels:
            raise RuntimeError("No labels remained after filtering.")

        subjects_dir = _subjects_dir(config)
        src_path = source_space_path(
            subjects_dir,
            _subject_label(subject),
            spacing=_source_spacing(config, spacing),
        )
        if not src_path.exists():
            raise FileNotFoundError(src_path)

        epochs = mne.read_epochs(epochs_path, preload=False, verbose=verbose)
        if settings["tmin"] is not None or settings["tmax"] is not None:
            epochs.crop(tmin=settings["tmin"], tmax=settings["tmax"])
        if settings["decim"] not in {None, 1}:
            epochs.decimate(int(settings["decim"]))

        inverse_operator = mne.minimum_norm.read_inverse_operator(inverse_path, verbose=verbose)
        src = mne.read_source_spaces(src_path, verbose=verbose)

        stcs = mne.minimum_norm.apply_inverse_epochs(
            epochs,
            inverse_operator,
            lambda2=settings["lambda2"],
            method=settings["method"],
            pick_ori=pick_ori,
            return_generator=True,
            verbose=verbose,
        )

        arrays: list[np.ndarray] = []
        for stc in stcs:
            label_tc = mne.extract_label_time_course(
                stc,
                labels,
                src,
                mode=settings["extract_mode"],
                allow_empty=allow_empty,
                verbose=verbose,
            )
            arrays.append(np.asarray(label_tc, dtype=settings["dtype"]))

        if not arrays:
            raise RuntimeError("No source epochs were produced.")

        data = np.stack(arrays, axis=0).astype(settings["dtype"], copy=False)

        _write_epoch_label_time_course_array(
            data=data,
            times=np.asarray(epochs.times),
            labels=labels,
            epochs=epochs,
            ltc_path=ltc_path,
            labels_path=labels_path,
            times_path=times_path,
            epochs_sidecar_path=epochs_sidecar_path,
        )

        return EpochLabelTimeCourseResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(ltc_path),
            status="written",
            epochs_path=str(epochs_path),
            inverse_path=str(inverse_path),
            labels_path=str(labels_path),
            times_path=str(times_path),
            epochs_sidecar_path=str(epochs_sidecar_path),
            parcellation=settings["parcellation"],
            extract_mode=settings["extract_mode"],
            method=settings["method"],
            lambda2=settings["lambda2"],
            decim=settings["decim"],
            dtype=settings["dtype"],
            n_epochs=int(data.shape[0]),
            n_labels=int(data.shape[1]),
            n_times=int(data.shape[2]),
        )

    except Exception as exc:  # noqa: BLE001 - batch notebooks should continue.
        return EpochLabelTimeCourseResult(
            subject=_subject_label(subject),
            session=session,
            task=task,
            run=run,
            path=str(ltc_path),
            status="failed",
            epochs_path=str(epochs_path),
            inverse_path=str(inverse_path),
            labels_path=str(labels_path),
            times_path=str(times_path),
            epochs_sidecar_path=str(epochs_sidecar_path),
            parcellation=settings["parcellation"],
            extract_mode=settings["extract_mode"],
            method=settings["method"],
            lambda2=settings["lambda2"],
            decim=settings["decim"],
            dtype=settings["dtype"],
            message=f"{type(exc).__name__}: {exc}",
        )


def extract_epoch_label_time_courses_for_recordings(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    method: str | None = None,
    lambda2: float | None = None,
    snr: float | None = None,
    parcellation: str | None = None,
    extract_mode: str | None = None,
    target_labels: tuple[str, ...] | list[str] | str | None = None,
    spacing: str | None = None,
    noise_cov_mode: str | None = None,
    decim: int | None = None,
    tmin: float | None = None,
    tmax: float | None = None,
    dtype: str | None = None,
    allow_empty: bool | str = False,
    pick_ori: str | None = None,
    verbose: bool | str | int | None = True,
) -> list[EpochLabelTimeCourseResult]:
    """Extract epoch-wise label time courses for multiple recordings."""
    overview = epoch_label_time_course_input_overview_to_dataframe(
        config,
        recordings,
        on_existing=on_existing,
        method=method,
        parcellation=parcellation,
        extract_mode=extract_mode,
        target_labels=target_labels,
        spacing=spacing,
        noise_cov_mode=noise_cov_mode,
        decim=decim,
        dtype=dtype,
    )

    results: list[EpochLabelTimeCourseResult] = []
    for _, row in overview.iterrows():
        if row["status"] == "exists" and on_existing == "skip":
            results.append(
                EpochLabelTimeCourseResult(
                    subject=str(row["subject"]),
                    session=row.get("session"),
                    task=row.get("task"),
                    run=row.get("run"),
                    path=str(row.get("ltc_path", "")),
                    status="skipped_existing",
                    epochs_path=str(row.get("epochs_path", "")),
                    inverse_path=str(row.get("inverse_path", "")),
                    labels_path=str(row.get("labels_path", "")),
                    times_path=str(row.get("times_path", "")),
                    epochs_sidecar_path=str(row.get("epochs_sidecar_path", "")),
                    parcellation=str(row.get("parcellation", "")),
                    extract_mode=str(row.get("extract_mode", "")),
                    method=str(row.get("method", "")),
                    lambda2=float(row["lambda2"]) if pd.notna(row.get("lambda2")) else None,
                    decim=int(row["decim"]) if pd.notna(row.get("decim")) else None,
                    dtype=str(row.get("dtype", "")),
                    n_labels=int(row["n_labels"]) if pd.notna(row.get("n_labels")) else None,
                    message="Epoch-wise label time courses already exist.",
                )
            )
            continue

        if row["status"] != "ready":
            results.append(
                EpochLabelTimeCourseResult(
                    subject=str(row["subject"]),
                    session=row.get("session"),
                    task=row.get("task"),
                    run=row.get("run"),
                    path=str(row.get("ltc_path", "")),
                    status=str(row["status"]),
                    epochs_path=str(row.get("epochs_path", "")),
                    inverse_path=str(row.get("inverse_path", "")),
                    labels_path=str(row.get("labels_path", "")),
                    times_path=str(row.get("times_path", "")),
                    epochs_sidecar_path=str(row.get("epochs_sidecar_path", "")),
                    parcellation=str(row.get("parcellation", "")),
                    extract_mode=str(row.get("extract_mode", "")),
                    method=str(row.get("method", "")),
                    lambda2=float(row["lambda2"]) if pd.notna(row.get("lambda2")) else None,
                    decim=int(row["decim"]) if pd.notna(row.get("decim")) else None,
                    dtype=str(row.get("dtype", "")),
                    n_labels=int(row["n_labels"]) if pd.notna(row.get("n_labels")) else None,
                    message=str(row.get("message", "")),
                )
            )
            continue

        recording: Recording = {
            "subject": str(row["subject"]).removeprefix("sub-"),
            "session": row.get("session") if pd.notna(row.get("session")) else None,
            "task": row.get("task") if pd.notna(row.get("task")) else None,
            "run": row.get("run") if pd.notna(row.get("run")) else None,
        }
        result = extract_epoch_label_time_courses_for_recording(
            config,
            recording,
            epochs_path=row.get("epochs_path"),
            inverse_path=row.get("inverse_path"),
            on_existing=on_existing,
            method=method,
            lambda2=lambda2,
            snr=snr,
            parcellation=parcellation,
            extract_mode=extract_mode,
            target_labels=target_labels,
            spacing=spacing,
            noise_cov_mode=noise_cov_mode,
            decim=decim,
            tmin=tmin,
            tmax=tmax,
            dtype=dtype,
            allow_empty=allow_empty,
            pick_ori=pick_ori,
            verbose=verbose,
        )
        results.append(result)

    return results


def epoch_label_time_course_results_to_dataframe(
    results: Iterable[EpochLabelTimeCourseResult],
) -> pd.DataFrame:
    """Convert epoch-wise label-time-course results to a status table."""
    return pd.DataFrame([result.__dict__ for result in results])


def epoch_label_time_course_qc_to_dataframe(
    epoch_label_time_course_results: pd.DataFrame | Iterable[EpochLabelTimeCourseResult | dict[str, Any]],
    *,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Read epoch-wise LTC arrays and summarize shape/basic QC metadata."""
    if isinstance(epoch_label_time_course_results, pd.DataFrame):
        table = epoch_label_time_course_results.copy()
    else:
        rows = []
        for result in epoch_label_time_course_results:
            if isinstance(result, EpochLabelTimeCourseResult):
                rows.append(result.__dict__)
            else:
                rows.append(dict(result))
        table = pd.DataFrame(rows)

    if table.empty:
        return pd.DataFrame(
            [{"status": "no_results", "message": "No epoch-wise label-time-course results to inspect."}]
        )

    if "path" not in table.columns:
        raise KeyError(
            f"epoch_label_time_course_results must contain a 'path' column. Columns: {list(table.columns)}"
        )

    candidate_table = table.copy()
    if max_rows is not None:
        candidate_table = candidate_table.head(max_rows)

    rows: list[dict[str, Any]] = []
    for _, row in candidate_table.iterrows():
        path = Path(row["path"])
        try:
            if not path.exists():
                raise FileNotFoundError(path)

            data = np.load(path, mmap_mode="r")
            shape = tuple(int(value) for value in data.shape)
            sample = np.asarray(data[: min(shape[0], 5)]) if len(shape) == 3 and shape[0] else np.asarray(data)

            rows.append(
                {
                    "subject": row.get("subject"),
                    "session": row.get("session"),
                    "task": row.get("task"),
                    "run": row.get("run"),
                    "status": "ok",
                    "path": str(path),
                    "shape": shape,
                    "n_epochs": shape[0] if len(shape) > 0 else None,
                    "n_labels": shape[1] if len(shape) > 1 else None,
                    "n_times": shape[2] if len(shape) > 2 else None,
                    "dtype": str(data.dtype),
                    "file_size_mb": path.stat().st_size / 1024**2,
                    "max_abs_sample": float(np.abs(sample).max()) if sample.size else None,
                    "mean_abs_sample": float(np.abs(sample).mean()) if sample.size else None,
                    "message": "",
                }
            )
        except Exception as exc:  # noqa: BLE001 - QC table should report all rows.
            rows.append(
                {
                    "subject": row.get("subject"),
                    "session": row.get("session"),
                    "task": row.get("task"),
                    "run": row.get("run"),
                    "status": "failed",
                    "path": str(path),
                    "shape": None,
                    "n_epochs": None,
                    "n_labels": None,
                    "n_times": None,
                    "dtype": None,
                    "file_size_mb": None,
                    "max_abs_sample": None,
                    "mean_abs_sample": None,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )

    return pd.DataFrame(rows)
