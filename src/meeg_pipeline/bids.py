from __future__ import annotations

from pathlib import Path

import pandas as pd
from mne_bids import BIDSPath, get_entity_vals, read_raw_bids

from meeg_pipeline.config import PipelineConfig


def has_dataset_description(bids_root: Path) -> bool:
    return (bids_root / "dataset_description.json").exists()


def has_participants_tsv(bids_root: Path) -> bool:
    return (bids_root / "participants.tsv").exists()


def read_participants(bids_root: Path) -> list[str]:
    participants_path = bids_root / "participants.tsv"

    if not participants_path.exists():
        return []

    participants = pd.read_csv(participants_path, sep="\t")

    if "participant_id" not in participants.columns:
        raise ValueError(
            f"participants.tsv must contain a 'participant_id' column: "
            f"{participants_path}"
        )

    return participants["participant_id"].astype(str).tolist()


def normalize_participant_id(participant_id: str) -> str:
    return participant_id.removeprefix("sub-")


def compare_subjects_with_participants(config: PipelineConfig) -> tuple[list[str], list[str]]:
    """Compare subject folders/entities with participants.tsv entries.

    Returns
    -------
    subjects_not_in_participants
        Subjects present as sub-* folders or BIDS entities but missing from participants.tsv.
    participants_without_subject_folder
        Participants listed in participants.tsv but missing as detected subjects.
    """
    subjects = set(list_bids_entities(config, "subject"))
    participants = {
        normalize_participant_id(participant)
        for participant in read_participants(config.paths.bids_root)
    }

    subjects_not_in_participants = sorted(subjects - participants)
    participants_without_subject_folder = sorted(participants - subjects)

    return subjects_not_in_participants, participants_without_subject_folder


def make_bids_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    extension: str | None = None,
) -> BIDSPath:
    """Create an MNE-BIDS path for a raw M/EEG recording."""
    return BIDSPath(
        root=config.paths.bids_root,
        subject=subject.removeprefix("sub-"),
        session=session or config.bids.session,
        task=task or config.bids.task,
        run=run or config.bids.run,
        datatype=config.bids.datatype,
        suffix=config.bids.datatype,
        extension=extension,
    )


def make_events_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
) -> BIDSPath:
    """Create a BIDSPath for an events.tsv file."""
    return BIDSPath(
        root=config.paths.bids_root,
        subject=subject.removeprefix("sub-"),
        session=session or config.bids.session,
        task=task or config.bids.task,
        run=run or config.bids.run,
        datatype=config.bids.datatype,
        suffix="events",
        extension=".tsv",
    )


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

    if entity == "subject":
        folder_subjects = [
            path.name.removeprefix("sub-")
            for path in config.paths.bids_root.glob("sub-*")
            if path.is_dir()
        ]
        values = sorted(set(values) | set(folder_subjects))

    return sorted(values)


def read_raw_bids_recording(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    preload: bool = False,
):
    """Read a raw BIDS recording using MNE-BIDS."""
    bids_path = make_bids_path(
        config,
        subject=subject,
        task=task,
        session=session,
        run=run,
        extension=".fif",
    )

    if not bids_path.fpath.exists():
        raise FileNotFoundError(f"Raw BIDS file does not exist: {bids_path.fpath}")

    return read_raw_bids(
        bids_path=bids_path,
        extra_params={"preload": preload},
        verbose=True,
    )