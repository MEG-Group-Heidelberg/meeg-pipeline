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
class PipelineConfig:
    project_name: str
    paths: ProjectPaths
    bids: BIDSConfig
    events: EventsConfig
    preprocessing: PreprocessingConfig


def _resolve_path(path: str | Path, *, base_dir: Path) -> Path:
    path = Path(path).expanduser()

    if not path.is_absolute():
        path = base_dir / path

    return path.resolve()


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None

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
        raw: dict[str, Any] = yaml.safe_load(f)

    paths_raw = raw["paths"]

    paths = ProjectPaths(
        bids_root=_resolve_path(paths_raw["bids_root"], base_dir=project_root),
        derivatives_root=_resolve_path(
            paths_raw["derivatives_root"],
            base_dir=project_root,
        ),
        sourcedata_root=_resolve_path(
            paths_raw.get("sourcedata_root", "./sourcedata"),
            base_dir=project_root,
        ),
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

    return PipelineConfig(
        project_name=raw["project"]["name"],
        paths=paths,
        bids=bids,
        events=events,
        preprocessing=preprocessing,
    )