# {{ project_name }}

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

The raw BIDS metadata files live under `rawdata/`, not in the outer project folder.

## First steps

1. Edit `configs/local.yaml`.
2. Place original M/EEG files under `sourcedata/`.
3. Place raw MRI exports under `sourcedata/mri_raw/` or standardized MRI inputs under `sourcedata/mri/`.
4. Convert source files into the raw BIDS dataset under `rawdata/`.
5. Open the notebooks in order.

## Source data example

Place original files under a folder structure like:

    sourcedata/sub-0001/meg/task-example/<original_file>.fif

or, when you want to organize source files by acquisition date:

    sourcedata/sub-0001/ses-20260523/meg/task-example/<original_file>.fif

By default, `sourcedata.sessions` is set to `ignore`, so a single `ses-*` folder can be used for organization without creating a BIDS session entity. Set `sourcedata.sessions: "include"` for true multi-session BIDS datasets.

Do not modify original source files after placing them in `sourcedata_root`.
