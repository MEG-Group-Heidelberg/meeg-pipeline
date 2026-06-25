from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


def find_trans_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "coreg",
) -> Path:
    """Return the expected coregistration transform path."""
    return coregistration_trans_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=desc,
    )


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
        trans_path = find_trans_path(config, **entities, desc=trans_desc)
        src_path = find_source_space_path(config, subject, spacing=spacing)
        bem_path = find_bem_solution_path(config, subject)
        fwd_path = make_forward_path(config, **entities, spacing=spacing)

        missing = []
        if info_input.status != "found":
            missing.append("info")
        if not trans_path.exists():
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
                "trans_exists": trans_path.exists(),
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
