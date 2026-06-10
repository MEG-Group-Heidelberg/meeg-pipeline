from __future__ import annotations

from pathlib import Path

from mne_bids import get_entity_vals

from meeg_pipeline.config import PipelineConfig


def has_dataset_description(bids_root: Path) -> bool:
    return (bids_root / "dataset_description.json").exists()


def list_bids_entities(config: PipelineConfig, entity: str) -> list[str]:
    """Return sorted BIDS entity values if they can be found.

    Examples for entity:
    - "subject"
    - "session"
    - "task"
    - "run"
    """
    if not config.paths.bids_root.exists():
        raise FileNotFoundError(f"BIDS root does not exist: {config.paths.bids_root}")

    values = get_entity_vals(
        config.paths.bids_root,
        entity_key=entity,
    )

    return sorted(values)