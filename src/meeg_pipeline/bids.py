from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from mne.io import BaseRaw
from mne_bids import BIDSPath, get_entity_vals, read_raw_bids

from meeg_pipeline.config import PipelineConfig


@dataclass(frozen=True)
class RawBIDSResult:
    raw: BaseRaw | None
    path: str
    status: str
    message: str = ""


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
        return []

    return participants["participant_id"].astype(str).tolist()


def normalize_participant_id(participant_id: str) -> str:
    return participant_id.removeprefix("sub-")


def normalize_subject_id(subject: str) -> str:
    return subject.removeprefix("sub-")


def compare_subjects_with_participants(
    config: PipelineConfig,
) -> tuple[list[str], list[str]]:
    participants = set(read_participants(config.paths.bids_root))
    subjects = {
        f"sub-{subject}"
        for subject in list_bids_entities(config, "subject")
    }

    return (
        sorted(subjects - participants),
        sorted(participants - subjects),
    )


def list_bids_entities(config: PipelineConfig, entity: str) -> list[str]:
    if not config.paths.bids_root.exists():
        return []

    return sorted(
        str(value)
        for value in get_entity_vals(config.paths.bids_root, entity, ignore_sessions=False)
    )


def make_bids_path(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    extension: str | None = None,
) -> BIDSPath:
    return BIDSPath(
        root=config.paths.bids_root,
        subject=normalize_subject_id(subject),
        session=session,
        task=task,
        run=run,
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
    return make_bids_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        extension=".tsv",
    ).update(suffix="events")


def read_raw_bids_recording(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    preload: bool = False,
) -> BaseRaw | None:
    """Read a raw BIDS recording if it exists.

    Missing recordings are normal in incomplete multi-subject projects and are
    represented by None instead of raising FileNotFoundError.
    """
    result = read_raw_bids_recording_if_exists(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        preload=preload,
    )
    return result.raw


def read_raw_bids_recording_if_exists(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None = None,
    session: str | None = None,
    run: str | None = None,
    preload: bool = False,
) -> RawBIDSResult:
    bids_path = make_bids_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        extension=".fif",
    )

    if not bids_path.fpath.exists():
        return RawBIDSResult(
            raw=None,
            path=str(bids_path.fpath),
            status="missing_input",
            message="Raw BIDS file does not exist.",
        )

    raw = read_raw_bids(
        bids_path=bids_path,
        extra_params={"preload": preload},
        verbose="error",
    )

    return RawBIDSResult(
        raw=raw,
        path=str(bids_path.fpath),
        status="loaded",
    )
