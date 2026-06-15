from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from meeg_pipeline.bids import list_bids_entities, make_events_path
from meeg_pipeline.config import PipelineConfig
from meeg_pipeline.paths import bids_path_to_path

EntitySelection = str | Sequence[str] | set[str] | None
Recording = dict[str, str | None]
ExistingOutputPolicy = Literal["skip", "overwrite"]
ManualDecisionPolicy = Literal["load", "overwrite"]


def as_set(value: Any) -> set[Any]:
    """Return *value* as a set.

    This is useful for notebook parameters that may be written as ``None``, a
    single value, or a list/tuple/set of values.
    """
    if value is None:
        return set()

    if isinstance(value, set):
        return value

    if isinstance(value, (list, tuple)):
        return set(value)

    return {value}


def sorted_nonmissing_unique(values: Iterable[Any]) -> list[Any]:
    """Return sorted unique values, excluding missing values.

    Missing means ``None`` or pandas-style ``NA``/``NaN``.
    """
    unique: set[Any] = set()

    for value in values:
        if value is None:
            continue

        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass

        unique.add(value)

    return sorted(unique)


def safe_join(values: Iterable[Any], *, sep: str = ", ", missing: str = "") -> str:
    """Join non-missing values as strings.

    Returns ``missing`` when no non-missing values are present.
    """
    clean_values = sorted_nonmissing_unique(values)

    if not clean_values:
        return missing

    return sep.join(str(value) for value in clean_values)


def resolve_entity_values(
    config: PipelineConfig,
    entity: str,
    selection: EntitySelection,
) -> list[str | None]:
    """Resolve a notebook selection for one BIDS entity.

    Allowed selections are:
    - ``None``: entity is not used, returns ``[None]``
    - ``"all"``: all detected values for the entity
    - ``["all"]``: same as ``"all"``
    - one value, e.g. ``"01"``
    - multiple values, e.g. ``["01", "02"]``

    If no values are available for ``"all"``, ``[None]`` is returned. This keeps
    partially acquired or not-yet-converted projects usable in notebooks.
    """
    if selection is None:
        return [None]

    available_values = list_bids_entities(config, entity)

    if selection == "all":
        return available_values if available_values else [None]

    if isinstance(selection, (list, tuple, set)):
        values = list(selection)

        if "all" in values:
            return available_values if available_values else [None]

        return [None if value is None else str(value) for value in values]

    return [str(selection)]


def iter_recordings(
    config: PipelineConfig,
    *,
    subjects: EntitySelection,
    sessions: EntitySelection = None,
    tasks: EntitySelection = None,
    runs: EntitySelection = None,
) -> Iterable[Recording]:
    """Yield concrete subject/session/task/run combinations.

    The yielded dictionaries are accepted by high-level pipeline functions that
    expect ``subject``, ``session``, ``task``, and ``run`` keys.
    """
    for subject in resolve_entity_values(config, "subject", subjects):
        if subject is None:
            continue

        for session in resolve_entity_values(config, "session", sessions):
            for task in resolve_entity_values(config, "task", tasks):
                for run in resolve_entity_values(config, "run", runs):
                    yield {
                        "subject": subject,
                        "session": session,
                        "task": task,
                        "run": run,
                    }


def recording_label(recording: Recording) -> str:
    """Return a compact BIDS-like label for one recording dictionary."""
    subject = recording.get("subject")

    if subject is None:
        raise ValueError("recording must contain a non-missing 'subject'.")

    parts = [f"sub-{str(subject).removeprefix('sub-')}"]

    session = recording.get("session")
    task = recording.get("task")
    run = recording.get("run")

    if session is not None:
        parts.append(f"ses-{session}")
    if task is not None:
        parts.append(f"task-{task}")
    if run is not None:
        parts.append(f"run-{run}")

    return "_".join(parts)


def recordings_to_dataframe(
    recordings: Iterable[Recording],
    *,
    include_index: bool = False,
) -> pd.DataFrame:
    """Convert recording dictionaries to a notebook-friendly table."""
    rows = []

    for index, recording in enumerate(recordings):
        row = {
            "recording": recording_label(recording),
            "subject": recording.get("subject"),
            "session": recording.get("session"),
            "task": recording.get("task"),
            "run": recording.get("run"),
        }

        if include_index:
            row = {"index": index, **row}

        rows.append(row)

    columns = ["recording", "subject", "session", "task", "run"]
    if include_index:
        columns = ["index", *columns]

    return pd.DataFrame(rows, columns=columns)


def selected_recordings_to_dataframe(recordings: Iterable[Recording]) -> pd.DataFrame:
    """Convert selected recordings to a table with stable inspection indices.

    This is a readable alias for ``recordings_to_dataframe(..., include_index=True)``.
    """
    return recordings_to_dataframe(recordings, include_index=True)


def _recording_matches(
    recording: Recording,
    *,
    subject: str,
    session: str | None,
    task: str | None,
    run: str | None,
) -> bool:
    """Return whether one recording matches the requested BIDS entities."""
    return (
        str(recording.get("subject", "")).removeprefix("sub-")
        == subject.removeprefix("sub-")
        and recording.get("session") == session
        and recording.get("task") == task
        and recording.get("run") == run
    )


def find_recording(
    recordings: Iterable[Recording],
    *,
    subject: str,
    session: str | None = None,
    task: str | None = None,
    run: str | None = None,
    require: bool = False,
) -> Recording | None:
    """Find one recording matching the requested BIDS entities.

    The subject can be passed with or without the ``sub-`` prefix.

    Returns ``None`` when no matching recording is found, unless ``require=True``.
    Raises ``ValueError`` if more than one recording matches.
    """
    matches = [
        recording
        for recording in recordings
        if _recording_matches(
            recording,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )
    ]

    if len(matches) == 1:
        return matches[0]

    requested = recording_label(
        {
            "subject": subject,
            "session": session,
            "task": task,
            "run": run,
        }
    )

    if len(matches) > 1:
        raise ValueError(
            f"Expected at most one recording matching {requested!r}, "
            f"found {len(matches)}."
        )

    if require:
        raise ValueError(f"No recording matching {requested!r} was found.")

    return None


def should_overwrite(step_name: str, overwrite_steps: Sequence[str] | str) -> bool:
    """Return whether a workflow step should overwrite existing outputs.

    ``overwrite_steps`` is intended for notebook-level settings such as::

        OVERWRITE_STEPS = []
        OVERWRITE_STEPS = ["events"]
        OVERWRITE_STEPS = "all"
    """
    if overwrite_steps == "all":
        return True

    if isinstance(overwrite_steps, str):
        raise ValueError(
            f"Invalid overwrite_steps value: {overwrite_steps!r}. "
            "Use 'all' or a list/tuple/set of step names."
        )

    if isinstance(overwrite_steps, (list, tuple, set)):
        return step_name in overwrite_steps

    raise ValueError(
        f"Invalid overwrite_steps value: {overwrite_steps!r}. "
        "Use 'all' or a list/tuple/set of step names."
    )


def existing_output_policy_for_step(
    step_name: str,
    overwrite_steps: Sequence[str] | str,
) -> ExistingOutputPolicy:
    """Return ``'overwrite'`` or ``'skip'`` for file-producing steps."""
    return "overwrite" if should_overwrite(step_name, overwrite_steps) else "skip"


def decision_policy_for_step(
    step_name: str,
    overwrite_steps: Sequence[str] | str,
) -> ManualDecisionPolicy:
    """Return ``'overwrite'`` or ``'load'`` for manual decision steps.

    This is suitable for outputs such as manually reviewed bad-channel or
    bad-segment decisions, where existing files should normally be loaded rather
    than skipped.
    """
    return "overwrite" if should_overwrite(step_name, overwrite_steps) else "load"


def bad_channels_policy_for_step(
    step_name: str,
    overwrite_steps: Sequence[str] | str,
) -> ManualDecisionPolicy:
    """Return policy for manual bad-channel decisions.

    This is a readable alias for ``decision_policy_for_step``.
    """
    return decision_policy_for_step(step_name, overwrite_steps)


def raw_events_path(
    config: PipelineConfig,
    recording: Recording | None = None,
    *,
    subject: str | None = None,
    session: str | None = None,
    task: str | None = None,
    run: str | None = None,
) -> Path:
    """Return the raw BIDS ``events.tsv`` path for one recording."""
    if recording is not None:
        subject = recording.get("subject")
        session = recording.get("session")
        task = recording.get("task")
        run = recording.get("run")

    if subject is None:
        raise ValueError("subject is required.")

    return bids_path_to_path(
        make_events_path(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
        )
    )


def read_raw_events(
    config: PipelineConfig,
    recording: Recording | None = None,
    *,
    subject: str | None = None,
    session: str | None = None,
    task: str | None = None,
    run: str | None = None,
) -> pd.DataFrame | None:
    """Read a raw BIDS ``events.tsv`` file if it exists.

    Missing files return ``None`` instead of raising ``FileNotFoundError`` so
    batch notebook workflows can report missing recordings without stopping.
    """
    path = raw_events_path(
        config,
        recording,
        subject=subject,
        session=session,
        task=task,
        run=run,
    )

    if not path.exists():
        return None

    return pd.read_csv(path, sep="\t")


def _recording_entities(recording: Recording) -> dict[str, str | None]:
    """Return BIDS entity keyword arguments for one recording."""
    return {
        "subject": recording.get("subject"),
        "session": recording.get("session"),
        "task": recording.get("task"),
        "run": recording.get("run"),
    }


def recording_path_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
    path_func: Callable[..., Path],
    *,
    exists_column: str = "exists",
    path_column: str = "path",
) -> pd.DataFrame:
    """Summarize expected paths for recordings.

    ``path_func`` must accept ``config`` plus ``subject``, ``session``, ``task``,
    and ``run`` keyword arguments. This works with helpers such as
    ``make_filtered_raw_path`` or ``make_bad_channels_path``.
    """
    rows = []

    for recording in recordings:
        path = path_func(config, **_recording_entities(recording))

        rows.append(
            {
                "recording": recording_label(recording),
                exists_column: path.exists(),
                path_column: str(path),
            }
        )

    return pd.DataFrame(rows)


def bad_channels_status_to_dataframe(
    config: PipelineConfig,
    recordings: Iterable[Recording],
) -> pd.DataFrame:
    """Summarize saved bad-channel decisions for selected recordings."""
    from meeg_pipeline.qc import load_bad_channels, make_bad_channels_path

    rows = []

    for recording in recordings:
        entities = _recording_entities(recording)
        path = make_bad_channels_path(config, **entities)

        if path.exists():
            bad_channels = load_bad_channels(config, **entities)
            bads = ", ".join(bad_channels.bads)
            n_bad_channels = len(bad_channels.bads)
            method = bad_channels.method
        else:
            bads = ""
            n_bad_channels = None
            method = ""

        rows.append(
            {
                "recording": recording_label(recording),
                "badchannels_exists": path.exists(),
                "n_bad_channels": n_bad_channels,
                "bad_channels": bads,
                "method": method,
                "path": str(path),
            }
        )

    return pd.DataFrame(rows)
