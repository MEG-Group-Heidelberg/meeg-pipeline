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


@dataclass(frozen=True)
class SourceDiscoveryIssue:
    path: str
    status: str
    message: str


def _strip_entity_prefix(value: str, prefix: str) -> str | None:
    expected_prefix = f"{prefix}-"
    if not value.startswith(expected_prefix):
        return None

    return value.removeprefix(expected_prefix)


def _find_single_fif(folder: Path) -> tuple[Path | None, SourceDiscoveryIssue | None]:
    fif_files = sorted(folder.glob("*.fif"))

    if len(fif_files) == 0:
        return None, SourceDiscoveryIssue(
            path=str(folder),
            status="missing_input",
            message="No .fif file found.",
        )

    if len(fif_files) > 1:
        return None, SourceDiscoveryIssue(
            path=str(folder),
            status="ambiguous_input",
            message=f"Expected exactly one .fif file, found {len(fif_files)}.",
        )

    return fif_files[0], None


def discover_source_recordings(config: PipelineConfig) -> list[SourceRecording]:
    """Find source FIF files in the standardized sourcedata structure.

    Missing or incomplete folders are skipped so partially acquired projects can
    be processed without interruption.
    """
    recordings, _issues = discover_source_recordings_with_issues(config)
    return recordings


def discover_source_recordings_with_issues(
    config: PipelineConfig,
) -> tuple[list[SourceRecording], list[SourceDiscoveryIssue]]:
    sourcedata_root = config.paths.sourcedata_root

    if not sourcedata_root.exists():
        return [], [
            SourceDiscoveryIssue(
                path=str(sourcedata_root),
                status="missing_input",
                message="sourcedata directory does not exist.",
            )
        ]

    recordings: list[SourceRecording] = []
    issues: list[SourceDiscoveryIssue] = []

    for subject_dir in sorted(sourcedata_root.glob("sub-*")):
        if not subject_dir.is_dir():
            continue

        subject = _strip_entity_prefix(subject_dir.name, "sub")
        if subject is None:
            continue

        meg_dir_without_session = subject_dir / "meg"
        if meg_dir_without_session.exists():
            new_recordings, new_issues = _discover_recordings_in_meg_dir(
                meg_dir=meg_dir_without_session,
                subject=subject,
                session=None,
            )
            recordings.extend(new_recordings)
            issues.extend(new_issues)

        for session_dir in sorted(subject_dir.glob("ses-*")):
            if not session_dir.is_dir():
                continue

            session = _strip_entity_prefix(session_dir.name, "ses")
            if session is None:
                continue

            meg_dir = session_dir / "meg"

            if not meg_dir.exists():
                continue

            new_recordings, new_issues = _discover_recordings_in_meg_dir(
                meg_dir=meg_dir,
                subject=subject,
                session=session,
            )
            recordings.extend(new_recordings)
            issues.extend(new_issues)

    return recordings, issues


def _discover_recordings_in_meg_dir(
    *,
    meg_dir: Path,
    subject: str,
    session: str | None,
) -> tuple[list[SourceRecording], list[SourceDiscoveryIssue]]:
    recordings: list[SourceRecording] = []
    issues: list[SourceDiscoveryIssue] = []

    for task_dir in sorted(meg_dir.glob("task-*")):
        if not task_dir.is_dir():
            continue

        task = _strip_entity_prefix(task_dir.name, "task")
        if task is None:
            continue

        run_dirs = sorted(path for path in task_dir.glob("run-*") if path.is_dir())

        if run_dirs:
            for run_dir in run_dirs:
                run = _strip_entity_prefix(run_dir.name, "run")
                if run is None:
                    continue

                source_path, issue = _find_single_fif(run_dir)
                if source_path is None:
                    if issue is not None:
                        issues.append(issue)
                    continue

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
            source_path, issue = _find_single_fif(task_dir)
            if source_path is None:
                if issue is not None:
                    issues.append(issue)
                continue

            recordings.append(
                SourceRecording(
                    source_path=source_path,
                    subject=subject,
                    session=session,
                    task=task,
                    run=None,
                )
            )

    return recordings, issues


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
