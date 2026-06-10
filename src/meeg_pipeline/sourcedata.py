from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meeg_pipeline.bids import make_bids_path
from meeg_pipeline.config import PipelineConfig


@dataclass(frozen=True)
class SourceRecording:
    source_path: Path
    subject: str
    session: str | None
    task: str
    run: str | None


def _strip_entity_prefix(value: str, prefix: str) -> str:
    expected_prefix = f"{prefix}-"
    if not value.startswith(expected_prefix):
        raise ValueError(f"Expected '{value}' to start with '{expected_prefix}'")

    return value.removeprefix(expected_prefix)


def _find_single_fif(folder: Path) -> Path:
    fif_files = sorted(folder.glob("*.fif"))

    if len(fif_files) == 0:
        raise FileNotFoundError(f"No .fif file found in {folder}")

    if len(fif_files) > 1:
        raise ValueError(
            f"Expected exactly one .fif file in {folder}, "
            f"but found {len(fif_files)}: {fif_files}"
        )

    return fif_files[0]


def discover_source_recordings(config: PipelineConfig) -> list[SourceRecording]:
    """Find source FIF files in the standardized sourcedata structure."""
    sourcedata_root = config.paths.bids_root / "sourcedata"

    if not sourcedata_root.exists():
        raise FileNotFoundError(f"sourcedata directory does not exist: {sourcedata_root}")

    recordings: list[SourceRecording] = []

    for subject_dir in sorted(sourcedata_root.glob("sub-*")):
        if not subject_dir.is_dir():
            continue

        subject = _strip_entity_prefix(subject_dir.name, "sub")

        # Case 1: sourcedata/sub-0001/meg/task-chords/*.fif
        meg_dir_without_session = subject_dir / "meg"
        if meg_dir_without_session.exists():
            recordings.extend(
                _discover_recordings_in_meg_dir(
                    meg_dir=meg_dir_without_session,
                    subject=subject,
                    session=None,
                )
            )

        # Case 2: sourcedata/sub-0001/ses-001/meg/task-chords/*.fif
        for session_dir in sorted(subject_dir.glob("ses-*")):
            if not session_dir.is_dir():
                continue

            session = _strip_entity_prefix(session_dir.name, "ses")
            meg_dir = session_dir / "meg"

            if not meg_dir.exists():
                continue

            recordings.extend(
                _discover_recordings_in_meg_dir(
                    meg_dir=meg_dir,
                    subject=subject,
                    session=session,
                )
            )

    return recordings


def _discover_recordings_in_meg_dir(
    *,
    meg_dir: Path,
    subject: str,
    session: str | None,
) -> list[SourceRecording]:
    recordings: list[SourceRecording] = []

    for task_dir in sorted(meg_dir.glob("task-*")):
        if not task_dir.is_dir():
            continue

        task = _strip_entity_prefix(task_dir.name, "task")

        run_dirs = sorted(path for path in task_dir.glob("run-*") if path.is_dir())

        if run_dirs:
            for run_dir in run_dirs:
                run = _strip_entity_prefix(run_dir.name, "run")
                source_path = _find_single_fif(run_dir)

                recordings.append(
                    SourceRecording(
                        source_path=source_path,
                        subject=subject,
                        session=session,
                        task=task,
                        run=run,
                    )
                )
        else:
            source_path = _find_single_fif(task_dir)

            recordings.append(
                SourceRecording(
                    source_path=source_path,
                    subject=subject,
                    session=session,
                    task=task,
                    run=None,
                )
            )

    return recordings


def make_target_bids_path(config: PipelineConfig, recording: SourceRecording):
    """Create the target raw BIDS path for a source recording."""
    return make_bids_path(
        config,
        subject=recording.subject,
        session=recording.session,
        task=recording.task,
        run=recording.run,
        extension=".fif",
    )