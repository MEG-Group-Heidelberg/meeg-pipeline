from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Iterable, Literal

import numpy as np
import pandas as pd

from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.conditions import (
    condition_candidate_columns,
    condition_definitions_from_config,
    normalize_condition_label,
    select_epoch_indices_from_metadata,
)
from meeg_pipeline.paths import derivative_path, sanitize_bids_label
from meeg_pipeline.source_modeling import (
    _epoch_label_time_course_sidecar_paths,
    make_epoch_label_time_course_path,
)
from meeg_pipeline.workflow import ExistingOutputPolicy, Recording


@dataclass(frozen=True)
class ConnectivityResult:
    """Result row for one source-label connectivity job."""

    subject: str
    session: str | None
    task: str | None
    run: str | None
    path: str
    status: str
    method: str = ""
    window: str = ""
    bands: str = ""
    condition: str = ""
    n_epochs: int | None = None
    n_labels: int | None = None
    n_times: int | None = None
    sfreq: float | None = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _subject_label(subject: str) -> str:
    return str(subject) if str(subject).startswith("sub-") else f"sub-{subject}"


def _recording_entities(recording: Recording) -> dict[str, str | None]:
    subject = recording.get("subject")
    if subject is None:
        raise ValueError("Recording must contain a non-missing 'subject'.")
    return {
        "subject": str(subject).removeprefix("sub-"),
        "session": recording.get("session"),
        "task": recording.get("task"),
        "run": recording.get("run"),
    }


def _source_epoch_ltc_settings(config: PipelineConfig) -> dict[str, Any]:
    epoch_cfg = config.source.label_time_courses_epochs
    return {
        "method": epoch_cfg.method or config.source.inverse.method,
        "parcellation": epoch_cfg.parcellation or config.source.labels.parcellation,
        "extract_mode": epoch_cfg.extract_mode or config.source.labels.extract_mode,
        "decim": epoch_cfg.decim,
    }


def _connectivity_n_jobs(config: PipelineConfig) -> int:
    return int(config.connectivity.n_jobs or config.runtime.n_jobs or 1)


def _window_names(config: PipelineConfig) -> list[str]:
    return list(config.connectivity.windows.keys())


def _band_names(config: PipelineConfig) -> list[str]:
    return list(config.connectivity.bands.keys())


def _condition_names(config: PipelineConfig) -> list[str]:
    conditions = config.connectivity.conditions
    if conditions == "all":
        return ["all"]
    return [str(condition) for condition in conditions]


def _connectivity_output_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None,
    session: str | None,
    run: str | None,
    method: str,
    window: str,
    condition: str,
    band_names: Iterable[str],
) -> Path:
    settings = _source_epoch_ltc_settings(config)
    parc_label = sanitize_bids_label(settings["parcellation"])
    method_label = sanitize_bids_label(method)
    window_label = sanitize_bids_label(window)
    condition_label = "" if condition == "all" else sanitize_bids_label(condition)
    band_label = sanitize_bids_label("-".join(band_names))
    desc_parts = [window_label]
    if condition_label:
        desc_parts.append(condition_label)
    desc_parts.extend([band_label, method_label])
    desc = "".join(desc_parts)

    return derivative_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        kind="connectivity",
        suffix=f"space-label_parc-{parc_label}_desc-{desc}-con.npz",
    )


def _ltc_input_paths(config: PipelineConfig, recording: Recording) -> tuple[Path, Path, Path, Path]:
    entities = _recording_entities(recording)
    settings = _source_epoch_ltc_settings(config)
    ltc_path = make_epoch_label_time_course_path(
        config,
        **entities,
        parcellation=settings["parcellation"],
        inverse_method=settings["method"],
        extract_mode=settings["extract_mode"],
        decim=settings["decim"],
        extension=".npy",
    )
    labels_path, times_path, epochs_path = _epoch_label_time_course_sidecar_paths(ltc_path)
    return ltc_path, labels_path, times_path, epochs_path


def _read_ltc_inputs(
    ltc_path: str | Path,
    labels_path: str | Path,
    times_path: str | Path,
    epochs_path: str | Path,
) -> tuple[np.ndarray, pd.DataFrame, np.ndarray, pd.DataFrame]:
    data = np.load(ltc_path, mmap_mode="r")
    labels = pd.read_csv(labels_path, sep="\t")
    times = pd.read_csv(times_path, sep="\t")["time_s"].to_numpy(dtype=float)
    epochs = pd.read_csv(epochs_path, sep="\t")
    return data, labels, times, epochs


def _select_time_indices(times: np.ndarray, *, tmin: float, tmax: float) -> np.ndarray:
    mask = (times >= float(tmin)) & (times <= float(tmax))
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        raise ValueError(f"No samples found for connectivity window {tmin}..{tmax} s.")
    return idx


def _select_label_indices(labels: pd.DataFrame, patterns: tuple[str, ...] | None) -> np.ndarray:
    if not patterns:
        return np.arange(len(labels), dtype=int)
    names = labels["label"].astype(str).str.lower()
    mask = np.zeros(len(labels), dtype=bool)
    for pattern in patterns:
        mask |= names.str.contains(str(pattern).lower(), regex=False).to_numpy()
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        raise ValueError(
            "connectivity.label_patterns selected no labels: "
            + ", ".join(str(pattern) for pattern in patterns)
        )
    return idx



def _normalize_condition_label(value: object) -> str:
    """Backward-compatible wrapper around generic condition normalization."""
    return normalize_condition_label(value)


def _condition_candidate_columns(epochs: pd.DataFrame) -> list[str]:
    """Backward-compatible wrapper around generic condition columns."""
    return condition_candidate_columns(epochs)


def _select_epoch_indices(
    epochs: pd.DataFrame,
    condition: str,
    *,
    definitions: dict[str, Any] | None = None,
) -> np.ndarray:
    """Select epochs for a condition using configured definitions or labels."""
    return select_epoch_indices_from_metadata(
        epochs,
        condition,
        definitions=definitions,
    )


def _sfreq_from_times(times: np.ndarray) -> float:
    if len(times) < 2:
        raise ValueError("At least two time samples are required to infer sampling rate.")
    diffs = np.diff(times)
    return float(1.0 / np.median(diffs))


def connectivity_config_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """Summarize connectivity settings."""
    rows: list[dict[str, Any]] = []
    for window_name, window in config.connectivity.windows.items():
        for band_name, band in config.connectivity.bands.items():
            rows.append(
                {
                    "enabled": config.connectivity.enabled,
                    "input": config.connectivity.input,
                    "space": config.connectivity.space,
                    "parcellation": config.connectivity.parcellation or config.source.labels.parcellation,
                    "methods": ",".join(config.connectivity.methods),
                    "mode": config.connectivity.mode,
                    "window": window_name,
                    "tmin": window.tmin,
                    "tmax": window.tmax,
                    "band": band_name,
                    "fmin": band.fmin,
                    "fmax": band.fmax,
                    "faverage": config.connectivity.faverage,
                    "conditions": config.connectivity.conditions,
                    "label_patterns": config.connectivity.label_patterns,
                    "block_size": config.connectivity.block_size,
                    "n_jobs": _connectivity_n_jobs(config),
                    "save_format": config.connectivity.save_format,
                }
            )
    return pd.DataFrame(rows)


def connectivity_input_overview_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
) -> pd.DataFrame:
    """Summarize source-label connectivity inputs and outputs."""
    rows: list[dict[str, Any]] = []
    band_names = _band_names(config)
    condition_definitions = condition_definitions_from_config(config)

    for recording in recordings:
        entities = _recording_entities(recording)
        ltc_path, labels_path, times_path, epochs_path = _ltc_input_paths(config, recording)
        input_exists = all(path.exists() for path in [ltc_path, labels_path, times_path, epochs_path])
        n_epochs = n_labels = n_times = None
        label_names_preview = ""
        message = ""
        if input_exists:
            try:
                data, labels, times, epochs = _read_ltc_inputs(
                    ltc_path, labels_path, times_path, epochs_path
                )
                n_epochs, n_labels, n_times = data.shape
                label_idx = _select_label_indices(labels, config.connectivity.label_patterns)
                label_names_preview = ", ".join(
                    labels.iloc[label_idx[:10]]["label"].astype(str).tolist()
                )
                if len(label_idx) > 10:
                    label_names_preview += ", ..."
            except Exception as exc:  # noqa: BLE001
                message = f"Could not inspect inputs: {type(exc).__name__}: {exc}"
        else:
            missing = [
                name
                for name, path in [
                    ("ltc", ltc_path),
                    ("labels", labels_path),
                    ("times", times_path),
                    ("epochs", epochs_path),
                ]
                if not path.exists()
            ]
            message = "Missing input(s): " + ", ".join(missing)

        for method in config.connectivity.methods:
            for window_name in _window_names(config):
                for condition in _condition_names(config):
                    out_path = _connectivity_output_path(
                        config,
                        **entities,
                        method=method,
                        window=window_name,
                        condition=condition,
                        band_names=band_names,
                    )

                    condition_n_epochs = None
                    condition_message = message
                    if input_exists and not message:
                        try:
                            condition_idx = _select_epoch_indices(
                                epochs,
                                condition,
                                definitions=condition_definitions,
                            )
                            condition_n_epochs = int(len(condition_idx))
                            if condition_n_epochs == 0:
                                condition_message = f"Condition {condition!r} selected no epochs."
                        except Exception as exc:  # noqa: BLE001
                            condition_message = (
                                f"Could not select condition {condition!r}: "
                                f"{type(exc).__name__}: {exc}"
                            )

                    if out_path.exists() and on_existing == "skip":
                        status = "exists"
                    elif input_exists and not condition_message:
                        status = "ready"
                    elif input_exists:
                        status = "inspect_warning"
                    else:
                        status = "missing_inputs"
                    rows.append(
                        {
                            "subject": _subject_label(entities["subject"]),
                            "session": entities["session"],
                            "task": entities["task"],
                            "run": entities["run"],
                            "method": method,
                            "window": window_name,
                            "condition": condition,
                            "status": status,
                            "message": condition_message,
                            "ltc_path": str(ltc_path),
                            "labels_path": str(labels_path),
                            "times_path": str(times_path),
                            "epochs_path": str(epochs_path),
                            "output_path": str(out_path),
                            "n_epochs": n_epochs,
                            "condition_n_epochs": condition_n_epochs,
                            "n_labels": n_labels,
                            "n_times": n_times,
                            "selected_label_preview": label_names_preview,
                            "overwrite": on_existing == "overwrite",
                        }
                    )
    columns = [
        "subject", "session", "task", "run", "method", "window", "condition",
        "status", "message", "ltc_path", "labels_path", "times_path",
        "epochs_path", "output_path", "n_epochs", "condition_n_epochs",
        "n_labels", "n_times", "selected_label_preview", "overwrite",
    ]
    return pd.DataFrame(rows, columns=columns)


def compute_source_label_connectivity_for_recording(
    config: PipelineConfig,
    recording: Recording,
    *,
    on_existing: ExistingOutputPolicy = "skip",
    methods: tuple[str, ...] | list[str] | str | None = None,
    windows: tuple[str, ...] | list[str] | str | None = None,
    conditions: tuple[str, ...] | list[str] | str | Literal["all"] | None = None,
    verbose: bool | str | int | None = True,
) -> list[ConnectivityResult]:
    """Compute spectral connectivity from epoch-wise source-label time courses."""
    try:
        from mne_connectivity import spectral_connectivity_epochs
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise ImportError(
            "mne-connectivity is required for connectivity analysis. Install it with "
            "`pip install mne-connectivity` or add it to your environment."
        ) from exc

    entities = _recording_entities(recording)
    ltc_path, labels_path, times_path, epochs_path = _ltc_input_paths(config, recording)
    data, labels, times, epochs = _read_ltc_inputs(ltc_path, labels_path, times_path, epochs_path)

    method_list = [methods] if isinstance(methods, str) else list(methods or config.connectivity.methods)
    if isinstance(windows, str):
        window_list = [windows]
    elif windows is None:
        window_list = _window_names(config)
    else:
        window_list = list(windows)

    if conditions is None:
        condition_list = _condition_names(config)
    elif conditions == "all":
        condition_list = ["all"]
    elif isinstance(conditions, str):
        condition_list = [conditions]
    else:
        condition_list = list(conditions)

    label_idx = _select_label_indices(labels, config.connectivity.label_patterns)
    label_names = labels.iloc[label_idx]["label"].astype(str).to_numpy()
    bands = config.connectivity.bands
    band_names = _band_names(config)
    condition_definitions = condition_definitions_from_config(config)
    fmin = [bands[name].fmin for name in band_names]
    fmax = [bands[name].fmax for name in band_names]

    results: list[ConnectivityResult] = []
    for window_name in window_list:
        if window_name not in config.connectivity.windows:
            raise ValueError(f"Unknown connectivity window: {window_name!r}")
        window = config.connectivity.windows[window_name]
        time_idx = _select_time_indices(times, tmin=window.tmin, tmax=window.tmax)
        cropped_times = np.asarray(times[time_idx], dtype=float)
        sfreq = _sfreq_from_times(cropped_times)

        for condition in condition_list:
            epoch_idx = _select_epoch_indices(
                epochs,
                condition,
                definitions=condition_definitions,
            )
            # Copy only the selected compact analysis block into RAM. This avoids
            # materializing the whole recording when label/time/condition subsets are used.
            selected = np.asarray(
                data[np.ix_(epoch_idx, label_idx, time_idx)],
                dtype=np.float64,
            )
            for method in method_list:
                out_path = _connectivity_output_path(
                    config,
                    **entities,
                    method=method,
                    window=window_name,
                    condition=condition,
                    band_names=band_names,
                )
                if out_path.exists() and on_existing == "skip":
                    results.append(
                        ConnectivityResult(
                            subject=_subject_label(entities["subject"]),
                            session=entities["session"],
                            task=entities["task"],
                            run=entities["run"],
                            path=str(out_path),
                            status="skipped_existing",
                            method=method,
                            window=window_name,
                            bands=",".join(band_names),
                            condition=condition,
                            n_epochs=int(selected.shape[0]),
                            n_labels=int(selected.shape[1]),
                            n_times=int(selected.shape[2]),
                            sfreq=sfreq,
                        )
                    )
                    continue
                if out_path.exists() and on_existing == "error":
                    raise FileExistsError(f"Connectivity output already exists: {out_path}")

                out_path.parent.mkdir(parents=True, exist_ok=True)
                con = spectral_connectivity_epochs(
                    selected,
                    names=list(label_names),
                    method=method,
                    mode=config.connectivity.mode,
                    sfreq=sfreq,
                    fmin=fmin,
                    fmax=fmax,
                    faverage=config.connectivity.faverage,
                    n_jobs=_connectivity_n_jobs(config),
                    block_size=config.connectivity.block_size,
                    verbose=verbose,
                )
                con_data = con.get_data(output="dense")
                freqs = np.asarray(getattr(con, "freqs", []), dtype=object)

                np.savez_compressed(
                    out_path,
                    connectivity=con_data,
                    labels=label_names,
                    method=np.asarray(method),
                    mode=np.asarray(config.connectivity.mode),
                    band_names=np.asarray(band_names),
                    fmin=np.asarray(fmin, dtype=float),
                    fmax=np.asarray(fmax, dtype=float),
                    freqs=freqs,
                    faverage=np.asarray(config.connectivity.faverage),
                    window=np.asarray(window_name),
                    tmin=np.asarray(window.tmin),
                    tmax=np.asarray(window.tmax),
                    condition=np.asarray(condition),
                    n_epochs=np.asarray(selected.shape[0]),
                    sfreq=np.asarray(sfreq),
                    source_ltc_path=np.asarray(str(ltc_path)),
                )
                results.append(
                    ConnectivityResult(
                        subject=_subject_label(entities["subject"]),
                        session=entities["session"],
                        task=entities["task"],
                        run=entities["run"],
                        path=str(out_path),
                        status="written",
                        method=method,
                        window=window_name,
                        bands=",".join(band_names),
                        condition=condition,
                        n_epochs=int(selected.shape[0]),
                        n_labels=int(selected.shape[1]),
                        n_times=int(selected.shape[2]),
                        sfreq=sfreq,
                    )
                )
    return results


def compute_source_label_connectivity_for_recordings(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    *,
    on_existing: ExistingOutputPolicy = "skip",
    methods: tuple[str, ...] | list[str] | str | None = None,
    windows: tuple[str, ...] | list[str] | str | None = None,
    conditions: tuple[str, ...] | list[str] | str | Literal["all"] | None = None,
    verbose: bool | str | int | None = True,
) -> list[ConnectivityResult]:
    """Compute source-label connectivity for multiple recordings."""
    results: list[ConnectivityResult] = []
    for recording in recordings:
        results.extend(
            compute_source_label_connectivity_for_recording(
                config,
                recording,
                on_existing=on_existing,
                methods=methods,
                windows=windows,
                conditions=conditions,
                verbose=verbose,
            )
        )
    return results


def connectivity_results_to_dataframe(results: Iterable[ConnectivityResult]) -> pd.DataFrame:
    """Convert connectivity result objects to a dataframe."""
    return pd.DataFrame([result.__dict__ for result in results])


def connectivity_qc_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """Summarize written connectivity .npz files."""
    rows: list[dict[str, Any]] = []
    for path in sorted(config.paths.derivatives_root.glob("sub-*/meg/connectivity/*-con.npz")):
        try:
            with np.load(path, allow_pickle=True) as npz:
                data = npz["connectivity"]
                labels = npz["labels"]
                band_names = npz["band_names"]
                rows.append(
                    {
                        "path": str(path),
                        "size_mb": path.stat().st_size / 1024**2,
                        "shape": tuple(data.shape),
                        "n_labels": len(labels),
                        "bands": ",".join(str(x) for x in band_names.tolist()),
                        "method": str(npz["method"]),
                        "window": str(npz["window"]),
                        "condition": str(npz["condition"]),
                        "n_epochs": int(npz["n_epochs"]),
                        "sfreq": float(npz["sfreq"]),
                        "status": "ok",
                        "message": "",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "path": str(path),
                    "size_mb": path.stat().st_size / 1024**2 if path.exists() else None,
                    "shape": None,
                    "n_labels": None,
                    "bands": "",
                    "method": "",
                    "window": "",
                    "condition": "",
                    "n_epochs": None,
                    "sfreq": None,
                    "status": "error",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
    return pd.DataFrame(rows)



def load_connectivity_npz(path: str | Path) -> dict[str, Any]:
    """Load a saved source-label connectivity file into plain Python/numpy objects."""
    path = Path(path)
    with np.load(path, allow_pickle=True) as npz:
        return {
            "path": str(path),
            "connectivity": np.asarray(npz["connectivity"]),
            "labels": [str(label) for label in npz["labels"].tolist()],
            "method": str(npz["method"]),
            "mode": str(npz["mode"]) if "mode" in npz else "",
            "band_names": [str(band) for band in npz["band_names"].tolist()],
            "fmin": np.asarray(npz["fmin"], dtype=float),
            "fmax": np.asarray(npz["fmax"], dtype=float),
            "window": str(npz["window"]),
            "tmin": float(npz["tmin"]),
            "tmax": float(npz["tmax"]),
            "condition": str(npz["condition"]),
            "n_epochs": int(npz["n_epochs"]),
            "sfreq": float(npz["sfreq"]),
            "source_ltc_path": str(npz["source_ltc_path"]) if "source_ltc_path" in npz else "",
        }


def _entities_from_connectivity_path(path: str | Path) -> dict[str, str | None]:
    """Extract common BIDS entities from a connectivity derivative path."""
    path = Path(path)
    stem = path.name
    entities: dict[str, str | None] = {"subject": None, "session": None, "task": None, "run": None}
    for part in stem.split("_"):
        if part.startswith("sub-"):
            entities["subject"] = part
        elif part.startswith("ses-"):
            entities["session"] = part.removeprefix("ses-")
        elif part.startswith("task-"):
            entities["task"] = part.removeprefix("task-")
        elif part.startswith("run-"):
            entities["run"] = part.removeprefix("run-")
    if entities["subject"] is None:
        for parent in path.parents:
            if parent.name.startswith("sub-"):
                entities["subject"] = parent.name
                break
    return entities


def connectivity_matrix_summary_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """Summarize written connectivity matrices per subject/task/method/band."""
    rows: list[dict[str, Any]] = []
    for path in sorted(config.paths.derivatives_root.glob("sub-*/meg/connectivity/*-con.npz")):
        try:
            loaded = load_connectivity_npz(path)
            data = loaded["connectivity"]
            entities = _entities_from_connectivity_path(path)
            n_bands = data.shape[-1] if data.ndim == 3 else 1
            for band_idx in range(n_bands):
                matrix = data[:, :, band_idx] if data.ndim == 3 else data
                finite = np.asarray(matrix, dtype=float)
                finite = finite[np.isfinite(finite)]
                if finite.size == 0:
                    mean_value = mean_abs = max_abs = np.nan
                else:
                    mean_value = float(np.mean(finite))
                    mean_abs = float(np.mean(np.abs(finite)))
                    max_abs = float(np.max(np.abs(finite)))
                band_name = loaded["band_names"][band_idx] if band_idx < len(loaded["band_names"]) else str(band_idx)
                rows.append(
                    {
                        **entities,
                        "path": str(path),
                        "method": loaded["method"],
                        "window": loaded["window"],
                        "condition": loaded["condition"],
                        "band": band_name,
                        "fmin": loaded["fmin"][band_idx] if band_idx < len(loaded["fmin"]) else np.nan,
                        "fmax": loaded["fmax"][band_idx] if band_idx < len(loaded["fmax"]) else np.nan,
                        "n_epochs": loaded["n_epochs"],
                        "n_labels": len(loaded["labels"]),
                        "mean": mean_value,
                        "mean_abs": mean_abs,
                        "max_abs": max_abs,
                        "status": "ok",
                        "message": "",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    **_entities_from_connectivity_path(path),
                    "path": str(path),
                    "method": "",
                    "window": "",
                    "condition": "",
                    "band": "",
                    "fmin": np.nan,
                    "fmax": np.nan,
                    "n_epochs": None,
                    "n_labels": None,
                    "mean": np.nan,
                    "mean_abs": np.nan,
                    "max_abs": np.nan,
                    "status": "error",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
    return pd.DataFrame(rows)


def connectivity_top_edges_to_dataframe(
    path: str | Path,
    *,
    band: str | int = 0,
    n_edges: int = 25,
    absolute: bool = True,
    include_diagonal: bool = False,
) -> pd.DataFrame:
    """Return the strongest edges from one saved connectivity matrix."""
    loaded = load_connectivity_npz(path)
    data = loaded["connectivity"]
    band_names = loaded["band_names"]
    if isinstance(band, str):
        if band not in band_names:
            raise ValueError(f"Unknown band {band!r}; available bands: {band_names}")
        band_idx = band_names.index(band)
    else:
        band_idx = int(band)
    matrix = data[:, :, band_idx] if data.ndim == 3 else data
    labels = loaded["labels"]
    rows: list[dict[str, Any]] = []
    n_labels = len(labels)
    for i in range(n_labels):
        for j in range(n_labels):
            if not include_diagonal and i == j:
                continue
            value = float(matrix[i, j])
            if not np.isfinite(value):
                continue
            rows.append(
                {
                    "label_from": labels[i],
                    "label_to": labels[j],
                    "value": value,
                    "abs_value": abs(value),
                    "method": loaded["method"],
                    "band": band_names[band_idx] if band_idx < len(band_names) else str(band_idx),
                    "window": loaded["window"],
                    "condition": loaded["condition"],
                    "path": str(path),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    sort_col = "abs_value" if absolute else "value"
    return df.sort_values(sort_col, ascending=False).head(int(n_edges)).reset_index(drop=True)



def connectivity_window_contrast_to_dataframe(
    config: PipelineConfig,
    *,
    post_window: str = "note_early",
    pre_window: str = "pre_3notes",
    condition: str | None = None,
    methods: tuple[str, ...] | list[str] | str | None = None,
) -> pd.DataFrame:
    """Summarize post-minus-pre window contrasts for saved connectivity files.

    The contrast is computed as ``connectivity(post_window) - connectivity(pre_window)``
    within each subject/task/method/condition and each frequency band. It does not
    write new derivative files; it is intended for QC and first-look plots.
    """
    rows: list[dict[str, Any]] = []
    paths = sorted(config.paths.derivatives_root.glob("sub-*/meg/connectivity/*-con.npz"))
    loaded_rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            loaded = load_connectivity_npz(path)
            entities = _entities_from_connectivity_path(path)
            loaded_rows.append({**entities, **loaded, "path": str(path)})
        except Exception:
            continue

    if not loaded_rows:
        return pd.DataFrame(rows)

    method_filter = None
    if methods is not None:
        method_filter = {methods} if isinstance(methods, str) else set(methods)

    def condition_matches(value: str) -> bool:
        if condition is None:
            return True
        return _normalize_condition_label(value) == _normalize_condition_label(condition)

    for post in loaded_rows:
        if post["window"] != post_window:
            continue
        if method_filter is not None and post["method"] not in method_filter:
            continue
        if not condition_matches(post["condition"]):
            continue

        matches = [
            pre for pre in loaded_rows
            if pre["subject"] == post["subject"]
            and pre.get("session") == post.get("session")
            and pre.get("task") == post.get("task")
            and pre.get("run") == post.get("run")
            and pre["method"] == post["method"]
            and pre["condition"] == post["condition"]
            and pre["window"] == pre_window
        ]
        if not matches:
            continue
        pre = matches[0]
        post_data = np.asarray(post["connectivity"], dtype=float)
        pre_data = np.asarray(pre["connectivity"], dtype=float)
        if post_data.shape != pre_data.shape:
            continue
        diff = post_data - pre_data
        n_bands = diff.shape[-1] if diff.ndim == 3 else 1
        for band_idx in range(n_bands):
            matrix = diff[:, :, band_idx] if diff.ndim == 3 else diff
            finite = matrix[np.isfinite(matrix)]
            if finite.size == 0:
                mean_value = mean_abs = max_abs = np.nan
            else:
                mean_value = float(np.mean(finite))
                mean_abs = float(np.mean(np.abs(finite)))
                max_abs = float(np.max(np.abs(finite)))
            band_names = post["band_names"]
            band_name = band_names[band_idx] if band_idx < len(band_names) else str(band_idx)
            rows.append({
                "subject": post["subject"],
                "session": post.get("session"),
                "task": post.get("task"),
                "run": post.get("run"),
                "method": post["method"],
                "condition": post["condition"],
                "post_window": post_window,
                "pre_window": pre_window,
                "contrast": f"{post_window}_minus_{pre_window}",
                "band": band_name,
                "n_labels": len(post["labels"]),
                "n_epochs_post": post["n_epochs"],
                "n_epochs_pre": pre["n_epochs"],
                "mean": mean_value,
                "mean_abs": mean_abs,
                "max_abs": max_abs,
                "post_path": post["path"],
                "pre_path": pre["path"],
                "status": "ok",
            })
    return pd.DataFrame(rows)


def load_connectivity_window_contrast(
    post_path: str | Path,
    pre_path: str | Path,
) -> dict[str, Any]:
    """Load two connectivity files and return a post-minus-pre contrast matrix."""
    post = load_connectivity_npz(post_path)
    pre = load_connectivity_npz(pre_path)
    post_data = np.asarray(post["connectivity"], dtype=float)
    pre_data = np.asarray(pre["connectivity"], dtype=float)
    if post_data.shape != pre_data.shape:
        raise ValueError(f"Connectivity shapes differ: {post_data.shape} vs {pre_data.shape}")
    if post["labels"] != pre["labels"]:
        raise ValueError("Connectivity label order differs between post and pre files.")
    return {
        **post,
        "connectivity": post_data - pre_data,
        "post_path": str(post_path),
        "pre_path": str(pre_path),
        "post_window": post["window"],
        "pre_window": pre["window"],
        "contrast": f"{post['window']}_minus_{pre['window']}",
    }
