from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from meeg_pipeline.bids import make_bids_path
from meeg_pipeline.config import PipelineConfig


SourcedataSessionMode = Literal["ignore", "include", "auto"]


@dataclass(frozen=True)
class SourceRecording:
    source_path: Path
    subject: str
    session: str | None
    task: str
    run: str | None
    source_session: str | None = None


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


def _configured_session_mode(config: PipelineConfig) -> SourcedataSessionMode:
    sourcedata = getattr(config, "sourcedata", None)
    mode = getattr(sourcedata, "sessions", "ignore")

    if mode not in {"ignore", "include", "auto"}:
        raise ValueError(
            "sourcedata.sessions must be one of 'ignore', 'include', or "
            f"'auto', got {mode!r}."
        )

    return mode


def _resolve_bids_session(
    source_session: str | None,
    *,
    subject: str,
    mode: SourcedataSessionMode,
    subject_session_counts: dict[str, int],
) -> str | None:
    if source_session is None:
        return None

    if mode == "include":
        return source_session

    if mode == "ignore":
        return None

    if mode == "auto":
        return source_session if subject_session_counts.get(subject, 0) > 1 else None

    raise ValueError(f"Invalid sourcedata session mode: {mode!r}.")


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

    raw_recordings: list[SourceRecording] = []
    issues: list[SourceDiscoveryIssue] = []
    source_sessions_by_subject: dict[str, set[str]] = defaultdict(set)

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
                source_session=None,
            )
            raw_recordings.extend(new_recordings)
            issues.extend(new_issues)

        for session_dir in sorted(subject_dir.glob("ses-*")):
            if not session_dir.is_dir():
                continue

            source_session = _strip_entity_prefix(session_dir.name, "ses")
            if source_session is None:
                continue

            source_sessions_by_subject[subject].add(source_session)

            meg_dir = session_dir / "meg"

            if not meg_dir.exists():
                issues.append(
                    SourceDiscoveryIssue(
                        path=str(session_dir),
                        status="missing_input",
                        message="Session folder does not contain a meg directory.",
                    )
                )
                continue

            new_recordings, new_issues = _discover_recordings_in_meg_dir(
                meg_dir=meg_dir,
                subject=subject,
                source_session=source_session,
            )
            raw_recordings.extend(new_recordings)
            issues.extend(new_issues)

    mode = _configured_session_mode(config)
    session_counts = {
        subject: len(source_sessions)
        for subject, source_sessions in source_sessions_by_subject.items()
    }

    recordings = [
        SourceRecording(
            source_path=recording.source_path,
            subject=recording.subject,
            session=_resolve_bids_session(
                recording.source_session,
                subject=recording.subject,
                mode=mode,
                subject_session_counts=session_counts,
            ),
            task=recording.task,
            run=recording.run,
            source_session=recording.source_session,
        )
        for recording in raw_recordings
    ]

    issues.extend(_target_collision_issues(config, recordings))

    return recordings, issues


def _discover_recordings_in_meg_dir(
    *,
    meg_dir: Path,
    subject: str,
    source_session: str | None,
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
                        session=None,
                        task=task,
                        run=run,
                        source_session=source_session,
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
                    session=None,
                    task=task,
                    run=None,
                    source_session=source_session,
                )
            )

    return recordings, issues


def _target_collision_issues(
    config: PipelineConfig,
    recordings: list[SourceRecording],
) -> list[SourceDiscoveryIssue]:
    target_to_recordings: dict[str, list[SourceRecording]] = defaultdict(list)

    for recording in recordings:
        target_to_recordings[str(make_target_bids_path(config, recording).fpath)].append(
            recording
        )

    issues: list[SourceDiscoveryIssue] = []

    for target_path, target_recordings in sorted(target_to_recordings.items()):
        if len(target_recordings) <= 1:
            continue

        source_paths = ", ".join(
            str(recording.source_path) for recording in target_recordings
        )
        issues.append(
            SourceDiscoveryIssue(
                path=target_path,
                status="duplicate_target",
                message=(
                    "Multiple source recordings map to the same BIDS target. "
                    "Use sourcedata.sessions: 'include', add run-* folders, or "
                    f"remove duplicate inputs. Source files: {source_paths}"
                ),
            )
        )

    return issues


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


@dataclass(frozen=True)
class EmptyRoomSourceRecording:
    """One original empty-room source FIF file."""

    source_path: Path
    session: str
    task: str
    run: str | None = None
    source_session: str | None = None


def _strip_session_prefix(session: str) -> str:
    return str(session).removeprefix("ses-")


def _strip_run_prefix(run: str) -> str:
    return str(run).removeprefix("run-")


def _run_from_path(path: Path) -> str | None:
    """Infer a BIDS run label from a path component or filename if present."""
    for part in path.parts:
        if part.startswith("run-"):
            return _strip_run_prefix(part)

    for token in path.stem.replace("_", "-").split("-"):
        if token.isdigit() and "run" in path.stem.lower():
            return token.zfill(2) if len(token) == 1 else token

    return None


def discover_empty_room_source_recordings(
    config: PipelineConfig,
) -> list[EmptyRoomSourceRecording]:
    """Find empty-room source FIF files from ``empty_room.sourcedata_root``.

    The source filename may be arbitrary. The session is inferred from the
    ``ses-*`` folder directly below ``sourcedata/emptyroom``. Runs are optional
    and may be encoded as a ``run-*`` folder or in the filename.
    """
    recordings, _issues = discover_empty_room_source_recordings_with_issues(config)
    return recordings


def discover_empty_room_source_recordings_with_issues(
    config: PipelineConfig,
) -> tuple[list[EmptyRoomSourceRecording], list[SourceDiscoveryIssue]]:
    empty_room = getattr(config, "empty_room", None)

    if empty_room is None or not getattr(empty_room, "enabled", False):
        return [], []

    root = empty_room.sourcedata_root
    if root is None or not Path(root).exists():
        return [], [
            SourceDiscoveryIssue(
                path=str(root),
                status="missing_input",
                message="Empty-room sourcedata directory does not exist.",
            )
        ]

    recordings: list[EmptyRoomSourceRecording] = []
    issues: list[SourceDiscoveryIssue] = []
    seen: set[Path] = set()

    for session_dir in sorted(Path(root).glob(empty_room.session_pattern)):
        if not session_dir.is_dir():
            continue

        session = _strip_session_prefix(session_dir.name)
        candidate_files: list[Path] = []
        for pattern in empty_room.file_patterns:
            candidate_files.extend(session_dir.rglob(pattern))

        files = sorted({candidate.resolve() for candidate in candidate_files if candidate.is_file()})

        if not files:
            issues.append(
                SourceDiscoveryIssue(
                    path=str(session_dir),
                    status="missing_input",
                    message="No empty-room FIF file found in session folder.",
                )
            )
            continue

        # If several files exist and none has a run label, report an ambiguity
        # instead of silently creating duplicate BIDS targets.
        runs = [_run_from_path(file) for file in files]
        if len(files) > 1 and any(run is None for run in runs):
            issues.append(
                SourceDiscoveryIssue(
                    path=str(session_dir),
                    status="ambiguous_input",
                    message=(
                        "Multiple empty-room FIF files found but not all have "
                        "a run label. Add run-* folders or run-* filenames."
                    ),
                )
            )
            continue

        for file, run in zip(files, runs):
            if file in seen:
                continue
            seen.add(file)
            recordings.append(
                EmptyRoomSourceRecording(
                    source_path=file,
                    session=session,
                    task=empty_room.task,
                    run=run,
                    source_session=session,
                )
            )

    return recordings, issues


def make_empty_room_target_bids_path(
    config: PipelineConfig,
    recording: EmptyRoomSourceRecording,
):
    """Return the raw BIDS target path for one empty-room source recording."""
    empty_room = config.empty_room
    return make_bids_path(
        config,
        subject=empty_room.subject,
        session=recording.session,
        task=recording.task,
        run=recording.run,
        extension=".fif",
    )


def empty_room_sourcedata_overview_to_dataframe(config: PipelineConfig):
    """Return a notebook-friendly overview of empty-room source files."""
    import pandas as pd

    recordings, issues = discover_empty_room_source_recordings_with_issues(config)
    rows: list[dict[str, str | bool | None]] = []

    for recording in recordings:
        target = make_empty_room_target_bids_path(config, recording)
        rows.append(
            {
                "kind": "emptyroom",
                "session": recording.session,
                "task": recording.task,
                "run": recording.run,
                "source_path": str(recording.source_path),
                "target_path": str(target.fpath),
                "target_exists": target.fpath.exists(),
                "status": "found",
                "message": "",
            }
        )

    for issue in issues:
        rows.append(
            {
                "kind": "emptyroom",
                "session": None,
                "task": getattr(config.empty_room, "task", "noise"),
                "run": None,
                "source_path": issue.path,
                "target_path": "",
                "target_exists": False,
                "status": issue.status,
                "message": issue.message,
            }
        )

    return pd.DataFrame(rows)

