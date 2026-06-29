from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InitProjectResult:
    project_root: str
    status: str
    created_paths: list[str]
    skipped_paths: list[str]
    message: str = ""


def _write_text_if_missing(
    path: Path,
    content: str,
    *,
    overwrite: bool,
    created_paths: list[str],
    skipped_paths: list[str],
) -> None:
    """Write a text file unless it already exists and overwrite is disabled."""
    if path.exists() and not overwrite:
        skipped_paths.append(str(path))
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created_paths.append(str(path))


def _mkdir_if_missing(
    path: Path,
    *,
    created_paths: list[str],
    skipped_paths: list[str],
) -> None:
    """Create a directory unless it already exists."""
    if path.exists():
        skipped_paths.append(str(path))
        return

    path.mkdir(parents=True, exist_ok=True)
    created_paths.append(str(path))


def _minimal_notebook(title: str, body: str) -> str:
    """Create a minimal placeholder notebook as JSON text."""
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    f"# {title}\n",
                    "\n",
                    body,
                ],
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "pygments_lexer": "ipython3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    return json.dumps(notebook, indent=1, ensure_ascii=False)


def make_local_yaml(project_name: str) -> str:
    """Create a default project config."""
    return f"""project:
  name: "{project_name}"

paths:
  # rawdata/ is the raw BIDS dataset root. Project-level files such as
  # README.md, configs/, notebooks/, sourcedata/, and derivatives/ live one
  # level above it in the outer project folder.
  bids_root: "./rawdata"
  sourcedata_root: "./sourcedata"
  derivatives_root: "./derivatives/meeg-pipeline"

sourcedata:
  # How ses-* folders in sourcedata are mapped to BIDS sessions:
  # "ignore": allow ses-* folders for organization, but omit ses from BIDS paths
  # "include": keep ses-* folders as BIDS sessions
  # "auto": include sessions only when a subject has multiple ses-* folders
  sessions: "ignore"

bids:
  datatype: "meg"
  task: null
  session: null
  run: null

events:
  extraction:
    method: "binary_channels"
    stim_channels:
      - "STI 001"
      - "STI 002"
      - "STI 003"
      - "STI 004"
      - "STI 005"
      - "STI 006"
    min_duration: 0.0
    shortest_event: 1
    min_gap: 7000
    adjust_timeline_by_msec: 0.0
    tolerance_samples: 1
    mute_bad_annotations: true

preprocessing:
  filtering:
    notch_freqs: [50]
    l_freq: 1.0
    h_freq: 40.0
    method: "fir"
"""


def make_dataset_description(project_name: str) -> str:
    """Create a minimal BIDS dataset_description.json."""
    payload = {
        "Name": project_name,
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "Authors": [],
    }

    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def make_participants_tsv() -> str:
    """Create a minimal BIDS participants.tsv."""
    return "participant_id\nsub-0001\n"


def make_participants_json() -> str:
    """Create a minimal BIDS participants.json sidecar."""
    payload = {
        "participant_id": {
            "Description": "Unique participant identifier"
        },
        "age": {
            "Description": "Age of the participant at time of testing",
            "Units": "years",
        },
        "sex": {
            "Description": "Sex of the participant",
            "Levels": {
                "F": "female",
                "M": "male",
                "O": "other",
            },
        },
        "hand": {
            "Description": "Handedness of the participant",
            "Levels": {
                "R": "right",
                "L": "left",
                "A": "ambidextrous",
            },
        },
    }

    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def make_bids_readme(project_name: str) -> str:
    """Create a short README for the raw BIDS dataset root."""
    return f"""# {project_name} raw BIDS dataset

This directory is the raw BIDS dataset root for the outer project folder.

It contains BIDS metadata files such as `dataset_description.json`,
`participants.tsv`, and `participants.json`, plus BIDS subject folders
`sub-*`.

Original acquisition exports are stored separately in the outer
`sourcedata/` directory. Processed outputs are stored separately in the outer
`derivatives/` directory.
"""


def make_project_readme(project_name: str) -> str:
    """Create a minimal project README.

    Avoid Markdown code fences here because this text is embedded in a Python
    triple-quoted string.
    """
    return f"""# {project_name}

This is a M/EEG project initialized with `meegpipe init-project`.

## Structure

This outer folder is the project workspace, not the raw BIDS dataset root.

- `README.md` — project-level notes for the analysis workspace
- `configs/local.yaml` — project configuration
- `notebooks/` — project workflow notebooks
- `sourcedata/` — original acquisition exports, kept unchanged
- `rawdata/` — raw BIDS dataset root
- `derivatives/meeg-pipeline/` — M/EEG pipeline outputs
- `derivatives/freesurfer/` — FreeSurfer anatomy outputs

The raw BIDS metadata files live under `rawdata/`, not in the outer project
folder:

- `rawdata/dataset_description.json`
- `rawdata/participants.tsv`
- `rawdata/participants.json`
- `rawdata/README`

## First steps

1. Edit `configs/local.yaml`.
2. Place original FIF files under `sourcedata/`.
3. Convert source files into the raw BIDS dataset under `rawdata/`.
4. Open the notebooks in order.
5. Run the summary notebook to inspect project status.

## Source data example

Place original files under a folder structure like:

    sourcedata/sub-0001/meg/task-example/<original_file>.fif

or, when you want to organize source files by acquisition date:

    sourcedata/sub-0001/ses-20260523/meg/task-example/<original_file>.fif

By default, `sourcedata.sessions` is set to `ignore`, so a single `ses-*`
folder can be used for organization without creating a BIDS session entity.
Set `sourcedata.sessions: "include"` for true multi-session BIDS datasets.

If source data live outside this project folder, set `sourcedata_root` in
`configs/local.yaml`, for example:

    paths:
      bids_root: "./rawdata"
      sourcedata_root: "../sourcedata"

Do not modify original source files after placing them in `sourcedata_root`.
"""


def init_project(
    project_name: str,
    *,
    base_dir: str | Path = ".",
    overwrite: bool = False,
) -> InitProjectResult:
    """Create a new M/EEG project scaffold.

    Parameters
    ----------
    project_name
        Name of the project folder to create.
    base_dir
        Directory in which the project folder should be created.
    overwrite
        If True, existing template files are overwritten. Existing directories
        are never deleted.
    """
    base_dir = Path(base_dir).expanduser().resolve()
    project_root = base_dir / project_name

    created_paths: list[str] = []
    skipped_paths: list[str] = []

    _mkdir_if_missing(
        project_root,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )

    _write_text_if_missing(
        project_root / "README.md",
        make_project_readme(project_name),
        overwrite=overwrite,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )

    _write_text_if_missing(
        project_root / "rawdata" / "dataset_description.json",
        make_dataset_description(project_name),
        overwrite=overwrite,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )

    _write_text_if_missing(
        project_root / "rawdata" / "participants.tsv",
        make_participants_tsv(),
        overwrite=overwrite,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )

    _write_text_if_missing(
        project_root / "rawdata" / "participants.json",
        make_participants_json(),
        overwrite=overwrite,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )

    _write_text_if_missing(
        project_root / "rawdata" / "README",
        make_bids_readme(project_name),
        overwrite=overwrite,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )

    _write_text_if_missing(
        project_root / "configs" / "local.yaml",
        make_local_yaml(project_name),
        overwrite=overwrite,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )

    for directory in [
        project_root / "notebooks",
        project_root / "rawdata",
        project_root / "rawdata" / "sub-0001" / "meg",
        project_root / "sourcedata",
        project_root / "sourcedata" / "sub-0001" / "meg" / "task-example",
        project_root
        / "sourcedata"
        / "sub-0001"
        / "ses-20260523"
        / "meg"
        / "task-example",
        project_root / "derivatives" / "meeg-pipeline",
    ]:
        _mkdir_if_missing(
            directory,
            created_paths=created_paths,
            skipped_paths=skipped_paths,
        )

    _write_text_if_missing(
        project_root
        / "sourcedata"
        / "sub-0001"
        / "meg"
        / "task-example"
        / "README.md",
        "Place exactly one original .fif file for this example task in this folder.\n",
        overwrite=overwrite,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )


    _write_text_if_missing(
        project_root
        / "sourcedata"
        / "sub-0001"
        / "ses-20260523"
        / "meg"
        / "task-example"
        / "README.md",
        (
            "Alternative example using an acquisition-date session folder. "
            "With sourcedata.sessions: 'ignore', this folder is used only for "
            "source organization and the BIDS target omits ses-20260523.\n"
        ),
        overwrite=overwrite,
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )

    placeholder_notebooks = {
        "00_project_summary.ipynb": (
            "00 Project Summary",
            (
                "Read-only dashboard. Replace this placeholder with the current "
                "project-summary notebook template.\n"
            ),
        ),
        "01_raw_bids_and_bad_channels.ipynb": (
            "01 Raw BIDS and Bad Channels",
            (
                "Convert sourcedata to BIDS and perform bad-channel QC. Replace "
                "this placeholder with the current notebook template.\n"
            ),
        ),
        "02_events.ipynb": (
            "02 Events",
            (
                "Extract or write BIDS-compatible events.tsv files. Replace this "
                "placeholder once the events notebook exists.\n"
            ),
        ),
        "03_preprocessing.ipynb": (
            "03 Preprocessing",
            (
                "Apply bad-channel decisions, filter data, and write filtered "
                "derivatives. Replace this placeholder with the current notebook "
                "template.\n"
            ),
        ),
        "04_artifact_annotation.ipynb": (
            "04 Artifact Annotation",
            (
                "Mark BAD time segments in filtered data. Replace this placeholder "
                "with the current notebook template.\n"
            ),
        ),
        "05_ica_cleaning.ipynb": (
            "05 ICA Cleaning",
            (
                "Fit ICA, inspect components, save ICA decisions, and write "
                "cleaned raw derivatives. Replace this placeholder with the "
                "current notebook template.\n"
            ),
        ),
    }

    for filename, (title, body) in placeholder_notebooks.items():
        _write_text_if_missing(
            project_root / "notebooks" / filename,
            _minimal_notebook(title, body),
            overwrite=overwrite,
            created_paths=created_paths,
            skipped_paths=skipped_paths,
        )

    return InitProjectResult(
        project_root=str(project_root),
        status="initialized",
        created_paths=created_paths,
        skipped_paths=skipped_paths,
    )