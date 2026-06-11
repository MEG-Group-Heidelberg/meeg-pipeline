from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mne
from mne.io import BaseRaw
from mne.preprocessing import ICA

from meeg_pipeline.annotations import apply_bad_annotations
from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.preprocessing import make_filtered_raw_path
from meeg_pipeline.qc import apply_bad_channels


ExistingOutputPolicy = Literal["skip", "overwrite"]
ExistingDecisionPolicy = Literal["load", "overwrite"]


@dataclass(frozen=True)
class ICAFitResult:
    path: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class ICADecision:
    exclude: list[int]
    method: str
    notes: str


@dataclass(frozen=True)
class ICADecisionResult:
    path: str
    status: str
    exclude: list[int]
    method: str = ""
    notes: str = ""
    message: str = ""


@dataclass(frozen=True)
class CleanedRawResult:
    path: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class LoadICAResult:
    ica: ICA | None
    path: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class LoadRawResult:
    raw: BaseRaw | None
    path: str
    status: str
    message: str = ""


def _recording_parts(
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> list[str]:
    subject = subject.removeprefix("sub-")

    parts = [f"sub-{subject}"]

    if session is not None:
        parts.append(f"ses-{session}")

    if task is not None:
        parts.append(f"task-{task}")

    if run is not None:
        parts.append(f"run-{run}")

    return parts


def _derivative_directory(
    config: PipelineConfig,
    *,
    subject: str,
    session: str | None = None,
) -> Path:
    subject = subject.removeprefix("sub-")

    if session is None:
        return config.paths.derivatives_root / f"sub-{subject}" / config.bids.datatype

    return (
        config.paths.derivatives_root
        / f"sub-{subject}"
        / f"ses-{session}"
        / config.bids.datatype
    )


def make_ica_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create derivative path for fitted ICA."""
    parts = _recording_parts(
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    basename = "_".join(parts + ["desc-ica_ica.fif"])

    return _derivative_directory(
        config,
        subject=subject,
        session=session,
    ) / basename


def make_ica_decision_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create derivative path for manually selected ICA exclusions."""
    parts = _recording_parts(
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    basename = "_".join(parts + ["desc-icadecision.json"])

    return _derivative_directory(
        config,
        subject=subject,
        session=session,
    ) / basename


def make_cleaned_raw_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> Path:
    """Create derivative path for ICA-cleaned continuous raw data."""
    parts = _recording_parts(
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    basename = "_".join(parts + ["desc-cleaned_meg.fif"])

    return _derivative_directory(
        config,
        subject=subject,
        session=session,
    ) / basename


def load_filtered_raw_for_cleaning(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    preload: bool = True,
) -> LoadRawResult:
    """Load filtered raw data and apply saved bad channels and annotations.

    Missing inputs are returned as status values instead of interrupting batch
    processing.
    """
    filtered_path = make_filtered_raw_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not filtered_path.exists():
        return LoadRawResult(
            raw=None,
            path=str(filtered_path),
            status="missing_input",
            message="Filtered raw derivative does not exist.",
        )

    raw = mne.io.read_raw_fif(
        filtered_path,
        preload=preload,
        verbose="error",
    )

    apply_bad_channels(
        raw,
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    apply_bad_annotations(
        raw,
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    return LoadRawResult(
        raw=raw,
        path=str(filtered_path),
        status="loaded",
    )


def fit_ica(
    raw: BaseRaw,
    *,
    n_components: int | float | None = 0.99,
    method: str = "fastica",
    random_state: int = 97,
    max_iter: int | str = "auto",
    reject_by_annotation: bool = True,
    decim: int | None = None,
    fit_resample_sfreq: float | None = None,
) -> ICA:
    """Fit ICA on a Raw object.

    The Raw object should already contain bad channels and bad-segment
    annotations.

    By default, ICA is fitted at the sampling rate of the input Raw object.

    If ``decim`` is not None, ICA fitting uses MNE's native decimation option
    and ``fit_resample_sfreq`` is ignored.

    If ``decim`` is None and ``fit_resample_sfreq`` is not None, ICA is fitted
    on a resampled copy of the raw data. This can speed up ICA fitting for long
    recordings. The fitted ICA can still be applied to the original filtered
    data as long as channel names, bad channels, and picks are consistent.
    """
    if decim is not None:
        raw_for_fit = raw
        fit_decim = decim
    elif fit_resample_sfreq is not None:
        raw_for_fit = raw.copy().resample(fit_resample_sfreq)
        fit_decim = None
    else:
        raw_for_fit = raw
        fit_decim = None

    ica = ICA(
        n_components=n_components,
        method=method,
        random_state=random_state,
        max_iter=max_iter,
    )

    picks = mne.pick_types(
        raw_for_fit.info,
        meg=True,
        eeg=True,
        eog=False,
        ecg=False,
        stim=False,
        exclude="bads",
    )

    ica.fit(
        raw_for_fit,
        picks=picks,
        reject_by_annotation=reject_by_annotation,
        decim=fit_decim,
    )

    return ica


def fit_ica_for_recording(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    n_components: int | float | None = 0.99,
    method: str = "fastica",
    random_state: int = 97,
    max_iter: int | str = "auto",
    decim: int | None = None,
    fit_resample_sfreq: float | None = None,
) -> ICAFitResult:
    """Fit and save ICA for one recording."""
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    output_path = make_ica_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if output_path.exists() and on_existing == "skip":
        return ICAFitResult(
            path=str(output_path),
            status="skipped_existing",
            message="ICA file already exists.",
        )

    raw_result = load_filtered_raw_for_cleaning(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        preload=True,
    )

    if raw_result.raw is None:
        return ICAFitResult(
            path=str(output_path),
            status=raw_result.status,
            message=raw_result.message,
        )

    ica = fit_ica(
        raw_result.raw,
        n_components=n_components,
        method=method,
        random_state=random_state,
        max_iter=max_iter,
        decim=decim,
        fit_resample_sfreq=fit_resample_sfreq,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ica.save(output_path, overwrite=on_existing == "overwrite")

    return ICAFitResult(
        path=str(output_path),
        status="written",
    )


def fit_ica_for_recordings(
    config: PipelineConfig,
    recordings: list[dict[str, str | None]],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    n_components: int | float | None = 0.99,
    method: str = "fastica",
    random_state: int = 97,
    max_iter: int | str = "auto",
    decim: int | None = None,
    fit_resample_sfreq: float | None = None,
) -> list[ICAFitResult]:
    """Fit and save ICA for multiple recordings."""
    return [
        fit_ica_for_recording(
            config,
            subject=recording["subject"],
            session=recording.get("session"),
            task=recording.get("task"),
            run=recording.get("run"),
            on_existing=on_existing,
            n_components=n_components,
            method=method,
            random_state=random_state,
            max_iter=max_iter,
            decim=decim,
            fit_resample_sfreq=fit_resample_sfreq,
        )
        for recording in recordings
    ]


def load_ica(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> LoadICAResult:
    """Load saved ICA if it exists."""
    path = make_ica_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return LoadICAResult(
            ica=None,
            path=str(path),
            status="missing_input",
            message="ICA file does not exist.",
        )

    return LoadICAResult(
        ica=mne.preprocessing.read_ica(path),
        path=str(path),
        status="loaded",
    )


def save_or_load_ica_decision(
    config: PipelineConfig,
    *,
    subject: str,
    exclude: list[int],
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    method: str = "manual_ica_inspection",
    notes: str = "",
    on_existing: ExistingDecisionPolicy = "load",
) -> ICADecisionResult:
    """Save ICA exclusion decision, or load existing decision."""
    if on_existing not in {"load", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'load' or 'overwrite'."
        )

    path = make_ica_decision_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if path.exists() and on_existing == "load":
        payload = json.loads(path.read_text(encoding="utf-8"))

        return ICADecisionResult(
            path=str(path),
            status="loaded_existing",
            exclude=[int(component) for component in payload.get("exclude", [])],
            method=str(payload.get("method", "")),
            notes=str(payload.get("notes", "")),
            message="ICA decision file already exists; loaded existing decision.",
        )

    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "subject": subject.removeprefix("sub-"),
        "session": session,
        "task": task,
        "run": run,
        "exclude": [int(component) for component in exclude],
        "method": method,
        "notes": notes,
    }

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return ICADecisionResult(
        path=str(path),
        status="written",
        exclude=[int(component) for component in exclude],
        method=method,
        notes=notes,
    )


def load_ica_decision(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> ICADecisionResult:
    """Load saved ICA decision if it exists."""
    path = make_ica_decision_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return ICADecisionResult(
            path=str(path),
            status="missing_input",
            exclude=[],
            message="ICA decision file does not exist.",
        )

    payload = json.loads(path.read_text(encoding="utf-8"))

    return ICADecisionResult(
        path=str(path),
        status="loaded",
        exclude=[int(component) for component in payload.get("exclude", [])],
        method=str(payload.get("method", "")),
        notes=str(payload.get("notes", "")),
    )


def write_cleaned_raw_for_recording(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingOutputPolicy = "skip",
) -> CleanedRawResult:
    """Apply saved ICA decision and write cleaned raw derivative."""
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    output_path = make_cleaned_raw_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if output_path.exists() and on_existing == "skip":
        return CleanedRawResult(
            path=str(output_path),
            status="skipped_existing",
            message="Cleaned raw file already exists.",
        )

    raw_result = load_filtered_raw_for_cleaning(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        preload=True,
    )

    if raw_result.raw is None:
        return CleanedRawResult(
            path=str(output_path),
            status=raw_result.status,
            message=raw_result.message,
        )

    ica_result = load_ica(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if ica_result.ica is None:
        return CleanedRawResult(
            path=str(output_path),
            status=ica_result.status,
            message=ica_result.message,
        )

    decision = load_ica_decision(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if decision.status == "missing_input":
        return CleanedRawResult(
            path=str(output_path),
            status="missing_input",
            message="ICA decision file does not exist.",
        )

    ica = ica_result.ica
    ica.exclude = decision.exclude

    cleaned = raw_result.raw.copy()
    ica.apply(cleaned)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.save(output_path, overwrite=on_existing == "overwrite")

    return CleanedRawResult(
        path=str(output_path),
        status="written",
    )


def write_cleaned_raw_for_recordings(
    config: PipelineConfig,
    recordings: list[dict[str, str | None]],
    *,
    on_existing: ExistingOutputPolicy = "skip",
) -> list[CleanedRawResult]:
    """Write cleaned raw derivatives for multiple recordings."""
    return [
        write_cleaned_raw_for_recording(
            config,
            subject=recording["subject"],
            session=recording.get("session"),
            task=recording.get("task"),
            run=recording.get("run"),
            on_existing=on_existing,
        )
        for recording in recordings
    ]