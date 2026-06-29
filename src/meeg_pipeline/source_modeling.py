from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable, Literal

import mne
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
    extension: str = ".h5",
) -> Path:
    """Create the path for epoch-level label time courses."""
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
        suffix=f"space-label_parc-{parc_label}_desc-epoch{method_label}-ltc{extension}",
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

