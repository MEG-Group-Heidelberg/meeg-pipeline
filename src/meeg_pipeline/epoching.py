from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import mne
import numpy as np
import pandas as pd
from mne import Epochs
from mne.io import BaseRaw

from meeg_pipeline.bids import make_events_path
from meeg_pipeline.cleaning import make_cleaned_raw_path
from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.event_derivatives import make_analysis_events_path
from meeg_pipeline.paths import bids_path_to_path, derivative_path


ExistingOutputPolicy = Literal["skip", "overwrite"]
EventCodeMode = Literal["trial_type", "value"]


@dataclass(frozen=True)
class LoadRawResult:
    raw: BaseRaw | None
    path: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class LoadEventsResult:
    events: pd.DataFrame | None
    path: str
    status: str
    kind: str = ""
    message: str = ""


@dataclass(frozen=True)
class EpochingResult:
    path: str
    status: str
    n_epochs: int = 0
    n_events: int = 0
    n_event_ids: int = 0
    events_kind: str = ""
    message: str = ""


def make_epochs_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "cleaned",
) -> Path:
    """Create derivative path for epoched data."""
    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="epochs",
        suffix=f"desc-{desc}_epo.fif",
    )


def make_reject_log_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    desc: str = "autoreject",
) -> Path:
    """Create derivative path for an optional autoreject reject log."""
    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="arlog",
        suffix=f"desc-{desc}_rejectlog.npz",
    )


def load_cleaned_raw_for_epoching(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    preload: bool = True,
) -> LoadRawResult:
    """Load cleaned raw data if it exists."""
    path = make_cleaned_raw_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return LoadRawResult(
            raw=None,
            path=str(path),
            status="missing_input",
            message="Cleaned raw derivative does not exist.",
        )

    raw = mne.io.read_raw_fif(
        path,
        preload=preload,
        verbose="error",
    )

    return LoadRawResult(
        raw=raw,
        path=str(path),
        status="loaded",
    )


def load_events_for_epoching(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    analysis_desc: str = "analysis",
) -> LoadEventsResult:
    """Load analysis events if present, otherwise raw BIDS events.

    Priority
    --------
    1. derivatives/.../events/*_desc-analysis_events.tsv
    2. raw BIDS *_events.tsv
    """
    analysis_path = make_analysis_events_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=analysis_desc,
    )

    if analysis_path.exists():
        events = pd.read_csv(analysis_path, sep="\t")
        return LoadEventsResult(
            events=events,
            path=str(analysis_path),
            status="loaded",
            kind="analysis",
        )

    raw_bids_events_path = make_events_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    raw_events_path = bids_path_to_path(raw_bids_events_path)

    if not raw_events_path.exists():
        return LoadEventsResult(
            events=None,
            path=str(raw_events_path),
            status="missing_input",
            kind="",
            message="Neither analysis events nor raw BIDS events exist.",
        )

    events = pd.read_csv(raw_events_path, sep="\t")

    return LoadEventsResult(
        events=events,
        path=str(raw_events_path),
        status="loaded",
        kind="trigger",
    )


def prepare_raw_for_epoching(
    raw: BaseRaw,
    *,
    ch_types: list[str] | tuple[str, ...] | str | None = ("meg",),
    ch_names: list[str] | tuple[str, ...] | str | None = "all",
    bad_interpolation: Literal["epochs", "evokeds"] | None = "epochs",
) -> BaseRaw:
    """Prepare a Raw object for epoching by applying channel selections."""
    raw = raw.copy()

    if ch_types is not None:
        if isinstance(ch_types, str):
            raw.pick(ch_types)
        else:
            raw.pick(list(ch_types))

    if ch_names is not None and ch_names != "all":
        if isinstance(ch_names, str):
            raw.pick([ch_names])
        else:
            raw.pick(list(ch_names))

    if bad_interpolation is None:
        raw.pick("all", exclude="bads")

    return raw


def events_table_to_mne_events(
    events: pd.DataFrame,
    *,
    event_code_mode: EventCodeMode = "trial_type",
) -> tuple[np.ndarray, dict[str, int], pd.DataFrame]:
    """Convert an events table to MNE events, event_id, and metadata.

    With event_code_mode="trial_type", compact MNE event codes are derived from
    the trial_type column. The original event table is kept as metadata.

    With event_code_mode="value", the integer value column is used as MNE event
    codes directly. This is closer to older event-id based workflows.
    """
    required_columns = {"sample", "trial_type"}
    missing_columns = sorted(required_columns - set(events.columns))
    if missing_columns:
        raise ValueError(
            "Events table is missing required columns for epoching: "
            f"{missing_columns}"
        )

    events = events.copy().reset_index(drop=True)

    if len(events) == 0:
        raise ValueError("Events table is empty.")

    if event_code_mode == "trial_type":
        trial_types = sorted(str(value) for value in events["trial_type"].unique())
        event_id = {
            trial_type: index + 1
            for index, trial_type in enumerate(trial_types)
        }

        codes = events["trial_type"].map(
            lambda value: event_id[str(value)]
        ).astype(int)

    elif event_code_mode == "value":
        if "value" not in events.columns:
            raise ValueError(
                "event_code_mode='value' requires a 'value' column."
            )

        values = pd.to_numeric(events["value"], errors="coerce")

        if values.isna().any():
            raise ValueError("Events value column contains non-numeric values.")

        codes = values.astype(int)
        event_id = {
            f"value_{int(value)}": int(value)
            for value in sorted(codes.unique())
        }

    else:
        raise ValueError(
            f"Invalid event_code_mode: {event_code_mode!r}. "
            "Use 'trial_type' or 'value'."
        )

    samples = pd.to_numeric(events["sample"], errors="coerce")

    if samples.isna().any():
        raise ValueError("Events sample column contains non-numeric values.")

    mne_events = np.column_stack(
        [
            samples.astype(int).to_numpy(),
            np.zeros(len(events), dtype=int),
            codes.astype(int).to_numpy(),
        ]
    )

    metadata = events.copy()

    return mne_events, event_id, metadata


def make_epochs(
    raw: BaseRaw,
    events_table: pd.DataFrame,
    *,
    tmin: float,
    tmax: float,
    baseline: tuple[float | None, float | None] | None = None,
    event_code_mode: EventCodeMode = "trial_type",
    picks: str | list[str] | None = None,
    apply_proj: bool = True,
    reject: dict[str, float] | None = None,
    flat: dict[str, float] | None = None,
    decim: int = 1,
    reject_by_annotation: bool = True,
    preload: bool = True,
    on_missing: str = "ignore",
    verbose: bool | str | int | None = True,
) -> Epochs:
    """Create MNE Epochs from a raw object and an events table."""
    mne_events, event_id, metadata = events_table_to_mne_events(
        events_table,
        event_code_mode=event_code_mode,
    )

    epochs = mne.Epochs(
        raw,
        events=mne_events,
        event_id=event_id,
        tmin=tmin,
        tmax=tmax,
        baseline=baseline,
        picks=picks,
        preload=preload,
        proj=apply_proj,
        reject=reject,
        flat=flat,
        decim=decim,
        metadata=metadata,
        reject_by_annotation=reject_by_annotation,
        on_missing=on_missing,
        verbose=verbose,
    )

    return epochs


def maybe_apply_autoreject(
    epochs: Epochs,
    *,
    use_autoreject: Literal["Interpolation", "Threshold"] | None = None,
    consensus_percs: list[float] | tuple[float, ...] | None = None,
    n_interpolates: list[int] | tuple[int, ...] | None = None,
    n_jobs: int = 1,
    random_state: int = 8,
    verbose: bool | str | int | None = True,
) -> tuple[Epochs, Any | None, dict[str, float] | None]:
    """Optionally apply autoreject.

    This function imports autoreject lazily so the base pipeline can be used
    without installing autoreject.
    """
    if use_autoreject is None:
        if verbose:
            print("Autoreject disabled.")
        return epochs, None, None

    try:
        import autoreject as ar
    except ImportError:
        if verbose:
            print("Autoreject requested, but package 'autoreject' is not installed.")
        return epochs, None, None

    if verbose:
        ch_types_present = sorted(
            {
                channel_type
                for channel_type in epochs.get_channel_types()
                if channel_type in {"mag", "grad", "eeg"}
            }
        )
        print(
            "Autoreject input: "
            f"{len(epochs)} epochs, "
            f"{len(epochs.ch_names)} channels, "
            f"ch_types={ch_types_present}, "
            f"bads={list(epochs.info['bads'])}"
        )
        print(
            "Autoreject mode: "
            f"{use_autoreject}, "
            f"n_jobs={n_jobs}, "
            f"consensus={consensus_percs}, "
            f"n_interpolate={n_interpolates}"
        )

    if use_autoreject == "Interpolation":
        ar_object = ar.AutoReject(
            n_interpolate=n_interpolates,
            consensus=consensus_percs,
            n_jobs=n_jobs,
            verbose=verbose,
        )

        cleaned_epochs, reject_log = ar_object.fit_transform(
            epochs,
            return_log=True,
        )

        if verbose:
            n_bad_epochs = int(reject_log.bad_epochs.sum())
            print(
                "Autoreject finished: "
                f"{len(cleaned_epochs)} epochs retained, "
                f"{n_bad_epochs} epochs marked bad in reject log."
            )

        return cleaned_epochs, reject_log, None

    if use_autoreject == "Threshold":
        reject_threshold = ar.get_rejection_threshold(
            epochs,
            random_state=random_state,
            verbose=verbose,
        )

        if verbose:
            print(f"Autoreject threshold estimate: {reject_threshold}")

        epochs = epochs.copy()
        n_before = len(epochs)
        epochs.drop_bad(reject=reject_threshold)
        n_after = len(epochs)

        if verbose:
            print(
                "Autoreject thresholding finished: "
                f"{n_before - n_after} epochs dropped, "
                f"{n_after} epochs retained."
            )

        return epochs, None, reject_threshold

    if verbose:
        print(f"Unknown autoreject mode {use_autoreject!r}; returning epochs unchanged.")

    return epochs, None, None


def write_epochs_for_recording(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    tmin: float | None = None,
    tmax: float | None = None,
    baseline: tuple[float | None, float | None] | None = None,
    event_code_mode: EventCodeMode = "trial_type",
    ch_types: list[str] | tuple[str, ...] | str | None = ("meg",),
    ch_names: list[str] | tuple[str, ...] | str | None = "all",
    bad_interpolation: Literal["epochs", "evokeds"] | None = "epochs",
    apply_proj: bool = True,
    reject: dict[str, float] | None = None,
    flat: dict[str, float] | None = None,
    decim: int = 1,
    reject_by_annotation: bool = True,
    use_autoreject: Literal["Interpolation", "Threshold"] | None = None,
    consensus_percs: list[float] | tuple[float, ...] | None = None,
    n_interpolates: list[int] | tuple[int, ...] | None = None,
    n_jobs: int = 1,
    verbose: bool | str | int | None = True,
) -> EpochingResult:
    """Create and write epochs for one recording."""
    if on_existing not in {"skip", "overwrite"}:
        raise ValueError(
            f"Invalid on_existing value: {on_existing!r}. "
            "Use 'skip' or 'overwrite'."
        )

    output_path = make_epochs_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if output_path.exists() and on_existing == "skip":
        return EpochingResult(
            path=str(output_path),
            status="skipped_existing",
            message="Epochs file already exists.",
        )

    raw_result = load_cleaned_raw_for_epoching(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        preload=True,
    )

    if raw_result.raw is None:
        return EpochingResult(
            path=str(output_path),
            status=raw_result.status,
            message=raw_result.message,
        )

    events_result = load_events_for_epoching(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if events_result.events is None:
        return EpochingResult(
            path=str(output_path),
            status=events_result.status,
            events_kind=events_result.kind,
            message=events_result.message,
        )

    if len(events_result.events) == 0:
        return EpochingResult(
            path=str(output_path),
            status="no_events",
            events_kind=events_result.kind,
            message="Events table is empty.",
        )

    raw = prepare_raw_for_epoching(
        raw_result.raw,
        ch_types=ch_types,
        ch_names=ch_names,
        bad_interpolation=bad_interpolation,
    )

    epochs = make_epochs(
        raw,
        events_result.events,
        tmin=config.epochs.tmin if tmin is None else tmin,
        tmax=config.epochs.tmax if tmax is None else tmax,
        baseline=config.epochs.baseline if baseline is None else baseline,
        event_code_mode=event_code_mode,
        apply_proj=apply_proj,
        reject=reject,
        flat=flat,
        decim=decim,
        reject_by_annotation=reject_by_annotation,
        preload=True,
        verbose=verbose,
    )

    epochs, reject_log, reject_threshold = maybe_apply_autoreject(
        epochs,
        use_autoreject=use_autoreject,
        consensus_percs=consensus_percs,
        n_interpolates=n_interpolates,
        n_jobs=n_jobs,
        verbose=verbose,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epochs.save(output_path, overwrite=on_existing == "overwrite")

    # Saving reject logs/thresholds can be added later once the desired file
    # format is stable. For now, the function keeps this information internal.

    return EpochingResult(
        path=str(output_path),
        status="written",
        n_epochs=len(epochs),
        n_events=len(events_result.events),
        n_event_ids=len(epochs.event_id),
        events_kind=events_result.kind,
    )


def write_epochs_for_recordings(
    config: PipelineConfig,
    recordings: list[dict[str, str | None]],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    tmin: float | None = None,
    tmax: float | None = None,
    baseline: tuple[float | None, float | None] | None = None,
    event_code_mode: EventCodeMode = "trial_type",
    ch_types: list[str] | tuple[str, ...] | str | None = ("meg",),
    ch_names: list[str] | tuple[str, ...] | str | None = "all",
    bad_interpolation: Literal["epochs", "evokeds"] | None = "epochs",
    apply_proj: bool = True,
    reject: dict[str, float] | None = None,
    flat: dict[str, float] | None = None,
    decim: int = 1,
    reject_by_annotation: bool = True,
    use_autoreject: Literal["Interpolation", "Threshold"] | None = None,
    consensus_percs: list[float] | tuple[float, ...] | None = None,
    n_interpolates: list[int] | tuple[int, ...] | None = None,
    n_jobs: int = 1,
    verbose: bool | str | int | None = True,
) -> list[EpochingResult]:
    """Create and write epochs for multiple recordings."""
    return [
        write_epochs_for_recording(
            config,
            subject=recording["subject"],
            session=recording.get("session"),
            task=recording.get("task"),
            run=recording.get("run"),
            on_existing=on_existing,
            tmin=tmin,
            tmax=tmax,
            baseline=baseline,
            event_code_mode=event_code_mode,
            ch_types=ch_types,
            ch_names=ch_names,
            bad_interpolation=bad_interpolation,
            apply_proj=apply_proj,
            reject=reject,
            flat=flat,
            decim=decim,
            reject_by_annotation=reject_by_annotation,
            use_autoreject=use_autoreject,
            consensus_percs=consensus_percs,
            n_interpolates=n_interpolates,
            n_jobs=n_jobs,
            verbose=verbose,
        )
        for recording in recordings
    ]
