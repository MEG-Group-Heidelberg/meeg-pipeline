from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProjectPaths:
    bids_root: Path
    derivatives_root: Path


@dataclass(frozen=True)
class BIDSConfig:
    datatype: str = "meg"
    task: str | None = None
    session: str | None = None
    run: str | None = None


@dataclass(frozen=True)
class PipelineConfig:
    project_name: str
    paths: ProjectPaths
    bids: BIDSConfig


def _resolve_path(path: str | Path, *, base_dir: Path) -> Path:
    path = Path(path).expanduser()

    if not path.is_absolute():
        path = base_dir / path

    return path.resolve()


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

    paths = ProjectPaths(
        bids_root=_resolve_path(raw["paths"]["bids_root"], base_dir=project_root),
        derivatives_root=_resolve_path(
            raw["paths"]["derivatives_root"],
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

    return PipelineConfig(
        project_name=raw["project"]["name"],
        paths=paths,
        bids=bids,
    )