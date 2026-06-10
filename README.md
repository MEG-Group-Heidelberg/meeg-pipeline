# meeg-pipeline

A modular, BIDS-compatible M/EEG analysis pipeline built on top of
[MNE-Python](https://mne.tools/stable/index.html) and
[MNE-BIDS](https://mne.tools/mne-bids/stable/index.html).

The goal of this project is to provide a transparent and extensible pipeline
for MEG and EEG data analysis. The pipeline is developed step by step, with a
strong focus on understanding each processing stage.

## Design principles

- BIDS-compatible project organization
- Clear separation between reusable pipeline code and project-specific data
- Original source data are preserved unchanged
- Raw BIDS data are treated as immutable analysis inputs
- Processed outputs are written to `derivatives/meeg-pipeline/`
- Intermediate preprocessing steps are saved as separate files
- Existing output files are not overwritten by default
- Event handling should be based on metadata-rich event tables
- Local and HPC-compatible execution
- Built on MNE-Python and MNE-BIDS

## Repository structure

This repository contains the reusable Python library, not project-specific data.

```text
meeg-pipeline/
  README.md
  pyproject.toml
  src/
    meeg_pipeline/
      __init__.py
      bids.py
      cli.py
      config.py
```

Concrete research projects should live in separate folders, for example:

```text
~/MEEG/
  meeg-pipeline/
  my-meeg-project/
```

The `meeg-pipeline` repository contains the reusable code.  
The project folder contains data, project-specific configs, and outputs.

## Installation for development

Clone the repository:

```bash
git clone https://github.com/MEG-Group-Heidelberg/meeg-pipeline.git
cd meeg-pipeline
```

Create and activate a Python environment. For example, using `venv`:

```bash
cd ~/MEEG
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Install the package in editable mode:

```bash
cd ~/MEEG/meeg-pipeline
pip install -e ".[dev]"
```

Test the installation:

```bash
python -c "import meeg_pipeline; print(meeg_pipeline.__version__)"
meegpipe --version
```

## Current command-line tools

Show the installed version:

```bash
meegpipe --version
```

Show information from a project config:

```bash
meegpipe config-info --config configs/local.yaml
```

Show basic information about a configured BIDS dataset:

```bash
meegpipe bids-info --config configs/local.yaml
```

Construct and inspect a BIDS path:

```bash
meegpipe bids-path \
  --config configs/local.yaml \
  --subject 0001 \
  --session 001 \
  --task chords \
  --extension .fif
```

## Project organization

A concrete M/EEG project should be organized separately from the pipeline
library.

Example with one subject, one session, and two tasks:

```text
my-meeg-project/
  dataset_description.json
  participants.tsv
  configs/
    local.yaml

  sourcedata/
    sub-0001/
      ses-001/
        meg/
          task-chords/
            original_chords_file.fif
          task-nochords/
            original_nochords_file.fif

  sub-0001/
    ses-001/
      meg/
        sub-0001_ses-001_task-chords_meg.fif
        sub-0001_ses-001_task-chords_meg.json
        sub-0001_ses-001_task-chords_channels.tsv
        sub-0001_ses-001_task-chords_events.tsv

        sub-0001_ses-001_task-nochords_meg.fif
        sub-0001_ses-001_task-nochords_meg.json
        sub-0001_ses-001_task-nochords_channels.tsv
        sub-0001_ses-001_task-nochords_events.tsv

  derivatives/
    meeg-pipeline/
      sub-0001/
        ses-001/
          meg/
            sub-0001_ses-001_task-chords_desc-filtered_meg.fif
            sub-0001_ses-001_task-chords_desc-cleaned_meg.fif
            sub-0001_ses-001_task-chords_desc-cleaned_epo.fif
```

## Data organization

### `sourcedata/`

`sourcedata/` contains the original files as exported from the acquisition system
or laboratory storage. These files should remain unchanged.

The folder structure should encode the relevant BIDS entities:

```text
sourcedata/
  sub-0001/
    ses-001/
      meg/
        task-chords/
          <original_file>.fif
        task-nochords/
          <original_file>.fif
```

If a project does not use sessions, omit the `ses-...` level:

```text
sourcedata/
  sub-0001/
    meg/
      task-chords/
        <original_file>.fif
      task-nochords/
        <original_file>.fif
```

If the same task has multiple runs, add `run-...` folders:

```text
sourcedata/
  sub-0001/
    ses-001/
      meg/
        task-chords/
          run-01/
            <original_file>.fif
          run-02/
            <original_file>.fif
```

The source FIF filename itself can be arbitrary. However, each lowest-level
source folder should contain exactly one `.fif` file.

### Raw BIDS data

The BIDS-formatted raw data are stored outside `sourcedata/`, using BIDS naming.

Example:

```text
sub-0001/
  ses-001/
    meg/
      sub-0001_ses-001_task-chords_meg.fif
      sub-0001_ses-001_task-nochords_meg.fif
```

These files should be generated from the original source data, preferably using
MNE-BIDS. They should be treated as immutable inputs for analysis.

The raw BIDS area should not contain intermediate preprocessing outputs.

### Derivatives

All processed outputs are written to:

```text
derivatives/meeg-pipeline/
```

Intermediate preprocessing steps are saved as separate files using BIDS-style
derivative names.

Examples:

```text
derivatives/meeg-pipeline/sub-0001/ses-001/meg/
  sub-0001_ses-001_task-chords_desc-filtered_meg.fif
  sub-0001_ses-001_task-chords_desc-cleaned_meg.fif
  sub-0001_ses-001_task-chords_desc-cleaned_epo.fif
```

The raw BIDS files should not be modified during preprocessing.

## Subject, session, task, and run naming

### Subjects

Subject folders use the BIDS format:

```text
sub-0001
sub-0002
sub-0003
```

In command-line arguments, subjects can be passed without the `sub-` prefix:

```bash
meegpipe bids-path --config configs/local.yaml --subject 0001
```

### Sessions

Sessions are optional in BIDS.

Use sessions if the project contains distinct measurement appointments, visits,
or timepoints.

If a project is known to contain only one measurement appointment per
participant, the `ses-...` level can be omitted.

Recommended session naming:

```text
ses-001
ses-002
ses-003
```

The session index is participant-specific:

```text
sub-0001/ses-001 = first measurement appointment of participant sub-0001
sub-0001/ses-002 = second measurement appointment of participant sub-0001
sub-0002/ses-001 = first measurement appointment of participant sub-0002
```

The same session label does not have to correspond to the same calendar date
across participants.

### Tasks

The `task-...` entity describes the experimental paradigm or recording context.

Example:

```text
task-chords
task-nochords
```

Even if both recordings are passive listening, they can be represented as
different tasks if they correspond to distinct experimental stimulus contexts.

### Runs

Runs are used for repeated recordings of the same task within the same session.

Example:

```text
sub-0001_ses-001_task-chords_run-01_meg.fif
sub-0001_ses-001_task-chords_run-02_meg.fif
```

Use `run-...` if the same task was repeated or split into multiple acquisition
blocks.

## Minimal project config

Each project should contain a config file, for example:

```text
my-meeg-project/
  configs/
    local.yaml
```

Example `configs/local.yaml`:

```yaml
project:
  name: "my-meeg-project"

paths:
  bids_root: "."
  derivatives_root: "./derivatives/meeg-pipeline"

bids:
  datatype: "meg"
  task: null
  session: null
  run: null
```

From the project root, test the config:

```bash
meegpipe config-info --config configs/local.yaml
```

Then inspect the BIDS structure:

```bash
meegpipe bids-info --config configs/local.yaml
```

## Minimal BIDS project files

At the project root, create a `dataset_description.json` file.

Example:

```json
{
  "Name": "my-meeg-project",
  "BIDSVersion": "1.10.0",
  "DatasetType": "raw",
  "Authors": ["Léon Bartosch"]
}
```

Also create a `participants.tsv` file.

Example:

```text
participant_id
sub-0001
sub-0002
```

The participant IDs in `participants.tsv` should match the `sub-*` folders.

## Recommended first data import step

Before converting to BIDS, place the original files under `sourcedata/`.

For one participant with one session and two tasks:

```bash
cd ~/MEEG/my-meeg-project

mkdir -p sourcedata/sub-0001/ses-001/meg/task-chords
mkdir -p sourcedata/sub-0001/ses-001/meg/task-nochords
```

Copy the original FIF files into the corresponding `sourcedata/` task folders:

```text
sourcedata/sub-0001/ses-001/meg/task-chords/<original_chords_file>.fif
sourcedata/sub-0001/ses-001/meg/task-nochords/<original_nochords_file>.fif
```

For projects without sessions, use:

```text
sourcedata/sub-0001/meg/task-chords/<original_chords_file>.fif
sourcedata/sub-0001/meg/task-nochords/<original_nochords_file>.fif
```

Do not modify these files.

The corresponding BIDS raw files will later be generated under:

```text
sub-0001/ses-001/meg/
```

or, if no session level is used:

```text
sub-0001/meg/
```

with filenames such as:

```text
sub-0001_ses-001_task-chords_meg.fif
sub-0001_ses-001_task-nochords_meg.fif
```

or, without sessions:

```text
sub-0001_task-chords_meg.fif
sub-0001_task-nochords_meg.fif
```

## Checking expected BIDS paths

The current CLI can construct expected BIDS paths.

Example:

```bash
cd ~/MEEG/my-meeg-project

meegpipe bids-path \
  --config configs/local.yaml \
  --subject 0001 \
  --session 001 \
  --task chords \
  --extension .fif
```

Expected output path:

```text
sub-0001/ses-001/meg/sub-0001_ses-001_task-chords_meg.fif
```

For the no-chords recording:

```bash
meegpipe bids-path \
  --config configs/local.yaml \
  --subject 0001 \
  --session 001 \
  --task nochords \
  --extension .fif
```

Expected output path:

```text
sub-0001/ses-001/meg/sub-0001_ses-001_task-nochords_meg.fif
```

## Overwrite policy

By default, pipeline steps should not overwrite existing files.

If an output file already exists, the corresponding pipeline step should stop or
skip that file instead of silently replacing it.

To recompute a specific step, delete the corresponding output file first.

For example, to recompute the filtered data for one subject, session, and task:

```bash
rm derivatives/meeg-pipeline/sub-0001/ses-001/meg/sub-0001_ses-001_task-chords_desc-filtered_meg.fif
```

Then rerun the corresponding pipeline step.

This makes intermediate analysis states explicit and prevents accidental
overwriting of previous results.

An explicit overwrite option may be added later, but the recommended workflow is
to remove specific outputs intentionally before recomputing them.

## Event handling principle

The pipeline should not assume that recorded trigger codes are always identical
to the final analysis events.

Instead, event handling should be table-based.

A simple event table may look like this:

```text
onset    duration    trial_type    trigger_code
1.532    0.0         stimulus      1
3.847    0.0         stimulus      1
```

More complex projects may derive analysis events from anchor triggers and
external metadata.

Example:

```text
onset    duration    trial_type        trial_id    stimulus_id    speaker      phoneme    relative_onset
42.000   3.200       sentence_onset    17          sent_017       speaker_03   n/a        0.000
42.134   0.087       phoneme_onset     17          sent_017       speaker_03   a          0.134
42.221   0.061       phoneme_onset     17          sent_017       speaker_03   t          0.221
42.309   0.102       phoneme_onset     17          sent_017       speaker_03   sh         0.309
```

Design principle:

```text
Raw triggers are acquisition-level anchors.
Analysis events are table-based, metadata-rich, and may be derived from anchors
plus external annotations.
MNE integer event codes are a late-stage compatibility representation, not the
primary event model.
```

## Development status

Early development.

Currently implemented:

- Python package structure
- `meegpipe` command-line entry point
- project config loading
- basic BIDS dataset inspection
- participants.tsv inspection
- BIDSPath construction
- path existence check

Not yet implemented:

- conversion from `sourcedata/` to raw BIDS
- raw data loading via MNE-BIDS
- event table creation
- preprocessing steps
- derivatives writing
- reports
- HPC/Slurm execution