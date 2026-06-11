from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProjectPaths:
    bids_root: Path
    sourcedata_root: Path
    derivatives_root: Path


@dataclass(frozen=True)
class RuntimeConfig:
    n_jobs: int = 1
    thread_limits: bool = True


@dataclass(frozen=True)
class BIDSConfig:
    datatype: str = "meg"
    task: str | None = None
    session: str | None = None
    run: str | None = None


@dataclass(frozen=True)
class EventExtractionConfig:
    method: str = "binary_channels"
    stim_channels: tuple[str, ...] = (
        "STI 001",
        "STI 002",
        "STI 003",
        "STI 004",
        "STI 005",
        "STI 006",
    )
    min_duration: float = 0.0
    shortest_event: int = 1
    min_gap: int = 7000
    adjust_timeline_by_msec: float = 0.0
    tolerance_samples: int = 1
    mute_bad_annotations: bool = True


@dataclass(frozen=True)
class EventsConfig:
    extraction: EventExtractionConfig


@dataclass(frozen=True)
class FilteringConfig:
    notch_freqs: tuple[float, ...] = (50.0,)
    l_freq: float | None = 1.0
    h_freq: float | None = 40.0
    method: str = "fir"


@dataclass(frozen=True)
class PreprocessingConfig:
    filtering: FilteringConfig


@dataclass(frozen=True)
class ICAConfig:
    n_components: int | float | None = 0.99
    method: str = "fastica"
    random_state: int = 97
    max_iter: int | str = "auto"
    decim: int | None = None
    fit_resample_sfreq: float | None = None


@dataclass(frozen=True)
class CleaningConfig:
    ica: ICAConfig


@dataclass(frozen=True)
class EpochsConfig:
    tmin: float = -1.0
    tmax: float = 1.0
    baseline: tuple[float | None, float | None] | None = None
    bad_interpolation: str | None = "epochs"


@dataclass(frozen=True)
class AutorejectConfig:
    enabled: bool = False
    use: str | None = None
    consensus_percs: tuple[float, ...] | None = None
    n_interpolates: tuple[int, ...] | None = None
    subset: int | None = None


@dataclass(frozen=True)
class SourceConfig:
    spacing: str = "ico5"
    noise_cov_mode: str = "erm"
    target_labels: tuple[str, ...] | None = None
    parcellation: str = "aparc_sub"
    extract_mode: str = "mean"
    inverse_method: str = "dSPM"


@dataclass(frozen=True)
class PipelineConfig:
    project_name: str
    paths: ProjectPaths
    runtime: RuntimeConfig
    bids: BIDSConfig
    events: EventsConfig
    preprocessing: PreprocessingConfig
    cleaning: CleaningConfig
    epochs: EpochsConfig
    autoreject: AutorejectConfig
    source: SourceConfig


def _resolve_path(path: str | Path, *, base_dir: Path) -> Path:
    path = Path(path).expanduser()

    if not path.is_absolute():
        path = base_dir / path

    return path.resolve()


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None

    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None

    return int(value)


def _optional_float_tuple(value: Any) -> tuple[float, ...] | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return (float(value),)

    return tuple(float(item) for item in value)


def _optional_int_tuple(value: Any) -> tuple[int, ...] | None:
    if value is None:
        return None

    if isinstance(value, int):
        return (int(value),)

    return tuple(int(item) for item in value)


def _optional_str_tuple(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None

    if isinstance(value, str):
        return (value,)

    return tuple(str(item) for item in value)


def _optional_baseline(
    value: Any,
) -> tuple[float | None, float | None] | None:
    if value is None:
        return None

    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(
            "epochs.baseline must be null or a two-element list/tuple, "
            f"got {value!r}."
        )

    start, end = value

    return (
        None if start is None else float(start),
        None if end is None else float(end),
    )


def _ica_n_components(value: Any) -> int | float | None:
    if value is None:
        return None

    if isinstance(value, int):
        return int(value)

    return float(value)


def load_config(config_path: str | Path) -> PipelineConfig:
    config_path = Path(config_path).expanduser().resolve()

    if not config_path.exists():
        raise FileNotFoundError(f"Config file does not exist: {config_path}")

    # Assumption:
    # If config is at <project>/configs/local.yaml,
    # then <project> is config_path.parent.parent.
    project_root = config_path.parent.parent

    with config_path.open("r", encoding="utf-8") as f:
        raw_loaded = yaml.safe_load(f)

    raw: dict[str, Any] = raw_loaded if raw_loaded is not None else {}

    paths_raw = raw["paths"]

    paths = ProjectPaths(
        bids_root=_resolve_path(paths_raw["bids_root"], base_dir=project_root),
        sourcedata_root=_resolve_path(
            paths_raw.get("sourcedata_root", "./sourcedata"),
            base_dir=project_root,
        ),
        derivatives_root=_resolve_path(
            paths_raw["derivatives_root"],
            base_dir=project_root,
        ),
    )

    runtime_raw = raw.get("runtime", {})
    runtime = RuntimeConfig(
        n_jobs=int(runtime_raw.get("n_jobs", 1)),
        thread_limits=bool(runtime_raw.get("thread_limits", True)),
    )

    bids_raw = raw.get("bids", {})
    bids = BIDSConfig(
        datatype=bids_raw.get("datatype", "meg"),
        task=bids_raw.get("task"),
        session=bids_raw.get("session"),
        run=bids_raw.get("run"),
    )

    events_raw = raw.get("events", {})
    extraction_raw = events_raw.get("extraction", {})

    event_extraction = EventExtractionConfig(
        method=extraction_raw.get("method", "binary_channels"),
        stim_channels=tuple(
            extraction_raw.get(
                "stim_channels",
                [
                    "STI 001",
                    "STI 002",
                    "STI 003",
                    "STI 004",
                    "STI 005",
                    "STI 006",
                ],
            )
        ),
        min_duration=float(extraction_raw.get("min_duration", 0.0)),
        shortest_event=int(extraction_raw.get("shortest_event", 1)),
        min_gap=int(extraction_raw.get("min_gap", 7000)),
        adjust_timeline_by_msec=float(
            extraction_raw.get("adjust_timeline_by_msec", 0.0)
        ),
        tolerance_samples=int(extraction_raw.get("tolerance_samples", 1)),
        mute_bad_annotations=bool(extraction_raw.get("mute_bad_annotations", True)),
    )

    events = EventsConfig(extraction=event_extraction)

    preprocessing_raw = raw.get("preprocessing", {})
    filtering_raw = preprocessing_raw.get("filtering", {})

    notch_freqs_raw = filtering_raw.get("notch_freqs", [50.0])

    if notch_freqs_raw is None:
        notch_freqs = ()
    else:
        notch_freqs = tuple(float(freq) for freq in notch_freqs_raw)

    filtering = FilteringConfig(
        notch_freqs=notch_freqs,
        l_freq=_optional_float(filtering_raw.get("l_freq", 1.0)),
        h_freq=_optional_float(filtering_raw.get("h_freq", 40.0)),
        method=filtering_raw.get("method", "fir"),
    )

    preprocessing = PreprocessingConfig(filtering=filtering)

    cleaning_raw = raw.get("cleaning", {})
    ica_raw = cleaning_raw.get("ica", {})

    cleaning = CleaningConfig(
        ica=ICAConfig(
            n_components=_ica_n_components(ica_raw.get("n_components", 0.99)),
            method=ica_raw.get("method", "fastica"),
            random_state=int(ica_raw.get("random_state", 97)),
            max_iter=ica_raw.get("max_iter", "auto"),
            decim=_optional_int(ica_raw.get("decim", None)),
            fit_resample_sfreq=_optional_float(
                ica_raw.get("fit_resample_sfreq", None)
            ),
        )
    )

    epochs_raw = raw.get("epochs", {})
    epochs = EpochsConfig(
        tmin=float(epochs_raw.get("tmin", -1.0)),
        tmax=float(epochs_raw.get("tmax", 1.0)),
        baseline=_optional_baseline(epochs_raw.get("baseline", None)),
        bad_interpolation=epochs_raw.get("bad_interpolation", "epochs"),
    )

    autoreject_raw = raw.get("autoreject", {})
    autoreject = AutorejectConfig(
        enabled=bool(autoreject_raw.get("enabled", False)),
        use=autoreject_raw.get("use"),
        consensus_percs=_optional_float_tuple(
            autoreject_raw.get("consensus_percs", None)
        ),
        n_interpolates=_optional_int_tuple(
            autoreject_raw.get("n_interpolates", None)
        ),
        subset=_optional_int(autoreject_raw.get("subset", None)),
    )

    source_raw = raw.get("source", {})
    source = SourceConfig(
        spacing=source_raw.get("spacing", "ico5"),
        noise_cov_mode=source_raw.get("noise_cov_mode", "erm"),
        target_labels=_optional_str_tuple(source_raw.get("target_labels", None)),
        parcellation=source_raw.get("parcellation", "aparc_sub"),
        extract_mode=source_raw.get("extract_mode", "mean"),
        inverse_method=source_raw.get("inverse_method", "dSPM"),
    )

    return PipelineConfig(
        project_name=raw["project"]["name"],
        paths=paths,
        runtime=runtime,
        bids=bids,
        events=events,
        preprocessing=preprocessing,
        cleaning=cleaning,
        epochs=epochs,
        autoreject=autoreject,
        source=source,
    )