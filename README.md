# meeg-pipeline

A modular, BIDS-compatible M/EEG analysis pipeline built on top of
[MNE-Python](https://mne.tools/stable/index.html) and
[MNE-BIDS](https://mne.tools/mne-bids/stable/index.html).

The goal of this project is to provide a transparent and extensible pipeline
for MEG and EEG data analysis. The pipeline is developed step by step, with a
strong focus on understanding each processing stage.

The package contains reusable pipeline code. Concrete research projects should
live in separate project folders and use this package as a library.

## Design principles

- BIDS-compatible project organization
- Clear separation between reusable pipeline code and project-specific data
- Original source data are preserved unchanged
- Raw BIDS FIF files are treated as immutable analysis inputs
- BIDS sidecar metadata such as `channels.tsv` may be updated when appropriate
- Processed outputs are written to `derivatives/meeg-pipeline/`
- Intermediate preprocessing steps are saved as separate files
- Existing output files are not overwritten by default
- Missing inputs are reported as status values instead of interrupting batch workflows
- Manual QC decisions are stored explicitly
- Event handling is table-based and metadata-friendly
- Notebook-friendly interactive workflow
- CLI-friendly batch workflow
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
      annotations.py
      bids.py
      channels.py
      cli.py
      config.py
      conversion.py
      events.py
      io.py
      preprocessing.py
      qc.py
      sourcedata.py
```

Concrete research projects should live in separate folders, for example:

```text
~/MEEG/
  meeg-pipeline/
  my-meeg-project/
```

The `meeg-pipeline` repository contains reusable code.  
The project folder contains data, project-specific configs, notebooks, and
outputs.

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

  notebooks/
    00_project_summary.ipynb
    01_raw_bids_and_bad_channels.ipynb
    02_events.ipynb
    03_preprocessing.ipynb
    04_artifact_annotation.ipynb

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
            sub-0001_ses-001_task-chords_desc-badchannels.json
            sub-0001_ses-001_task-chords_desc-filtered_meg.fif
            sub-0001_ses-001_task-chords_desc-badsegments_annotations.fif
            sub-0001_ses-001_task-chords_desc-cleaned_meg.fif
            sub-0001_ses-001_task-chords_desc-cleaned_epo.fif
```

For projects without sessions, omit the `ses-...` level consistently:

```text
sub-0001/
  meg/
    sub-0001_task-chords_meg.fif
    sub-0001_task-chords_channels.tsv
    sub-0001_task-chords_events.tsv

derivatives/
  meeg-pipeline/
    sub-0001/
      meg/
        sub-0001_task-chords_desc-badchannels.json
        sub-0001_task-chords_desc-filtered_meg.fif
        sub-0001_task-chords_desc-badsegments_annotations.fif
```

## Data organization

### `sourcedata/`

`sourcedata/` contains the original files as exported from the acquisition system
or laboratory storage. These files should remain unchanged.

The source-data root is configured in `configs/local.yaml`:

```yaml
paths:
  sourcedata_root: "./sourcedata"
```

It may also point to an external drive or network location:

```yaml
paths:
  sourcedata_root: "/Volumes/MEGDrive/my-meeg-project/sourcedata"
```

Relative paths are resolved relative to the project root.

The folder structure inside `sourcedata_root` should encode the relevant BIDS
entities.

With sessions:

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

Without sessions:

```text
sourcedata/
  sub-0001/
    meg/
      task-chords/
        <original_file>.fif
      task-nochords/
        <original_file>.fif
```

With runs:

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

Examples:

```text
sourcedata/sub-0001/meg/task-chords/original_file.fif
sourcedata/sub-0001/ses-001/meg/task-chords/run-01/original_file.fif
```

The pipeline uses the folder structure to infer BIDS entities such as subject,
session, task, and run.

### Raw BIDS data

The BIDS-formatted raw data are stored outside `sourcedata/`, using BIDS naming.

Example:

```text
sub-0001/
  ses-001/
    meg/
      sub-0001_ses-001_task-chords_meg.fif
      sub-0001_ses-001_task-chords_channels.tsv
      sub-0001_ses-001_task-chords_events.tsv
```

Raw BIDS FIF files are generated from the original source data, preferably using
MNE-BIDS. They should be treated as immutable analysis inputs.

The raw BIDS area should not contain intermediate preprocessing outputs.

### BIDS sidecars

Some BIDS sidecar files are part of the raw BIDS dataset and may be updated when
metadata decisions are made.

For example, manual bad-channel decisions should update:

```text
sub-0001/meg/sub-0001_task-chords_channels.tsv
```

using the BIDS columns:

```text
status
status_description
```

The raw FIF file itself should remain unchanged.

### Derivatives

All processed outputs and explicit pipeline decisions are written to:

```text
derivatives/meeg-pipeline/
```

Examples:

```text
derivatives/meeg-pipeline/sub-0001/ses-001/meg/
  sub-0001_ses-001_task-chords_desc-badchannels.json
  sub-0001_ses-001_task-chords_desc-filtered_meg.fif
  sub-0001_ses-001_task-chords_desc-badsegments_annotations.fif
  sub-0001_ses-001_task-chords_desc-cleaned_meg.fif
  sub-0001_ses-001_task-chords_desc-cleaned_epo.fif
```

The raw BIDS FIF files should not be modified during preprocessing.

## Subject, session, task, and run naming

### Subjects

Subject folders use the BIDS format:

```text
sub-0001
sub-0002
sub-0003
```

In command-line arguments and Python functions, subjects can usually be passed
without the `sub-` prefix:

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
  sourcedata_root: "./sourcedata"
  derivatives_root: "./derivatives/meeg-pipeline"

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
```

To disable notch filtering, use:

```yaml
preprocessing:
  filtering:
    notch_freqs: null
    l_freq: 1.0
    h_freq: 40.0
    method: "fir"
```

To disable either the high-pass or low-pass filter, use `null`:

```yaml
preprocessing:
  filtering:
    notch_freqs: [50]
    l_freq: null
    h_freq: 40.0
    method: "fir"
```

From the project root, test the config:

```bash
meegpipe config-info --config configs/local.yaml
```

Then inspect the BIDS structure:

```bash
meegpipe bids-info --config configs/local.yaml
```

## Status-oriented batch behavior

Pipeline functions are designed to support projects where not every subject,
session, task, or run has been collected or processed yet.

Normal pipeline states are reported as status values instead of interrupting
the whole batch process.

Common status values include:

```text
missing_input
skipped_existing
loaded
loaded_existing
written
applied
```

For example, if a filtered file does not exist for one subject, the corresponding
notebook row should report `missing_input`, while processing can continue for
other subjects.

Exceptions are reserved for actual programming or configuration errors, such as
invalid policy values or malformed input files.

## Event extraction config

Event extraction parameters are stored in the project config, not hard-coded in
the library.

Example for a lab setup where trigger IDs are encoded as binary combinations
across six stimulus channels:

```yaml
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
```

With `method: "binary_channels"`, event IDs are created by binary coding across
the listed stimulus channels.

For example:

```text
STI 001 -> 1
STI 002 -> 2
STI 003 -> 4
STI 004 -> 8
STI 005 -> 16
STI 006 -> 32
```

If `STI 001` and `STI 003` are active at the same event onset, the resulting
event ID is:

```text
1 + 4 = 5
```

The same event extraction function can be reused across projects by changing the
config values.

## Event handling principle

The pipeline should not assume that recorded trigger codes are always identical
to the final analysis events.

Instead, event handling should be table-based.

A simple event table may look like this:

```text
onset    duration    trial_type    value    sample
1.532    0.0         trigger_1     1        1532
3.847    0.0         trigger_1     1        3847
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

## Manual bad-channel QC

Manual bad-channel marking is treated as an explicit QC decision.

Recommended workflow:

1. Load one raw BIDS recording.
2. Optionally compute automatic bad-channel candidates.
3. Open the interactive MNE browser with `raw.plot(block=True)`.
4. Mark bad channels in the GUI.
5. Close the browser window.
6. Save the bad-channel decision as a JSON derivative.
7. Update the raw BIDS `*_channels.tsv` sidecar.
8. Keep the raw `*_meg.fif` file unchanged.

Example files:

```text
sub-1409/meg/sub-1409_task-chords_meg.fif
sub-1409/meg/sub-1409_task-chords_channels.tsv

derivatives/meeg-pipeline/sub-1409/meg/
  sub-1409_task-chords_desc-badchannels.json
```

The raw FIF file remains unchanged.  
The BIDS sidecar `channels.tsv` is updated using the columns:

```text
status
status_description
```

Example bad-channel JSON:

```json
{
  "subject": "1409",
  "session": null,
  "task": "chords",
  "run": null,
  "bads": ["MEG0112"],
  "method": "manual_mne_gui_with_maxwell_candidates",
  "notes": "Automatic Maxwell bad-channel candidates were pre-marked and manually reviewed with raw.plot(block=True)."
}
```

Example `channels.tsv` rows after manual QC:

```text
name       type     units   status   status_description
MEG0112    MEGGRAD  T/m     bad      manual_mne_gui_with_maxwell_candidates: Automatic Maxwell bad-channel candidates were pre-marked and manually reviewed with raw.plot(block=True).
MEG0113    MEGGRAD  T/m     good
```

This makes bad-channel decisions visible to BIDS-aware tools while keeping the
original raw FIF data intact.

## Bad-segment annotation

Bad-segment annotation is used to mark bad time spans after filtering.

Recommended workflow:

1. Load a filtered raw derivative, for example `desc-filtered_meg.fif`.
2. Open the interactive MNE browser with `raw.plot(picks="meg", block=True)`.
3. Press `a` to open the annotation controls.
4. Use **Add Description** to create a bad-segment label.
5. Mark bad time spans using a label that starts with `BAD`.
6. Close the browser window.
7. Save only the `BAD*` annotations as a derivative.

Recommended bad-segment descriptions:

```text
BAD_artifact
BAD_jump
BAD_movement
BAD_noise
BAD_muscle
BAD_other
```

Event-like descriptions such as `trigger_1`, `trigger_2`, etc. may appear in the
MNE annotation dropdown if events were loaded as annotations. These should not be
used for artifact rejection.

Only annotations whose description starts with `BAD` are saved in the
bad-segment derivative.

Example file:

```text
derivatives/meeg-pipeline/sub-1409/meg/
  sub-1409_task-chords_desc-badsegments_annotations.fif
```

These annotations can later be applied to filtered or cleaned data. Downstream
MNE steps can use the standard `reject_by_annotation=True` behavior to ignore
bad spans.

## Notebook workflow

The recommended project workflow is notebook-oriented.

A project may contain notebooks such as:

```text
notebooks/
  00_project_summary.ipynb
  01_raw_bids_and_bad_channels.ipynb
  02_events.ipynb
  03_preprocessing.ipynb
  04_artifact_annotation.ipynb
```

Suggested roles:

```text
00_project_summary.ipynb
  Read-only dashboard.
  Shows what data exist, what has been computed, event status, bad-channel status,
  filtered-derivative status, bad-segment annotation status, and later derivative
  status.

01_raw_bids_and_bad_channels.ipynb
  Active raw-data and bad-channel notebook.
  Discovers sourcedata, converts to raw BIDS, inspects channels, performs manual
  bad-channel QC, and updates channels.tsv.

02_events.ipynb
  Event extraction notebook.
  Extracts or writes BIDS-compatible events.tsv files.

03_preprocessing.ipynb
  Preprocessing notebook.
  Applies saved bad-channel decisions, filters data, and writes filtered raw
  derivatives.

04_artifact_annotation.ipynb
  Bad-segment annotation notebook.
  Loads filtered data, interactively marks BAD_* time spans, and writes
  bad-segment annotation derivatives.
```

Notebook steps should call reusable library functions rather than implementing
large processing logic directly inside notebooks.

## Existing-output and overwrite policy

By default, pipeline steps should not silently overwrite existing files.

Different steps can use different existing-output policies:

```text
convert_to_bids:
  skip / overwrite

events:
  skip / overwrite

bad_channels:
  load / overwrite

annotations:
  load / overwrite

filtering:
  skip / overwrite
```

For notebooks, a central variable can be used:

```python
OVERWRITE_STEPS = []
OVERWRITE_STEPS = ["events"]
OVERWRITE_STEPS = ["bad_channels"]
OVERWRITE_STEPS = ["annotations"]
OVERWRITE_STEPS = ["filtering"]
OVERWRITE_STEPS = ["events", "bad_channels"]
OVERWRITE_STEPS = "all"
```

Recommended default:

```python
OVERWRITE_STEPS = []
```

This means:

```text
convert_to_bids  -> skip existing raw BIDS files
events           -> skip existing events.tsv files
bad_channels     -> load existing bad-channel decisions
annotations      -> load existing bad-segment annotations
filtering        -> skip existing filtered derivatives
```

To recompute a specific step, either delete the corresponding output file
intentionally or add the step to `OVERWRITE_STEPS`.

## Current command-line tools

The package currently provides a small command-line interface called `meegpipe`.

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

Inspect discovered source recordings:

```bash
meegpipe sourcedata-info --config configs/local.yaml
```

Convert source recordings to raw BIDS:

```bash
meegpipe convert-to-bids --config configs/local.yaml
```

Read a raw BIDS recording and show basic information:

```bash
meegpipe raw-info \
  --config configs/local.yaml \
  --subject 1409 \
  --task chords
```

Show channel information:

```bash
meegpipe channels-info \
  --config configs/local.yaml \
  --subject 1409 \
  --task chords
```

Extract events and show event information:

```bash
meegpipe events-info \
  --config configs/local.yaml \
  --subject 1409 \
  --task chords
```

Write BIDS-compatible `events.tsv` files:

```bash
meegpipe write-events \
  --config configs/local.yaml \
  --subject 1409 \
  --task chords
```

The CLI is useful for quick checks and later batch/HPC workflows. Interactive QC
is better handled in notebooks.

## Recommended first data import step

Before converting to BIDS, place the original files under the configured
`sourcedata_root`.

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

Do not modify these source files.

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

The CLI can construct expected BIDS paths.

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

## Development status

Early development.

Currently implemented:

- Python package structure
- `meegpipe` command-line entry point
- project config loading
- configurable `sourcedata_root`
- basic BIDS dataset inspection
- participants.tsv inspection
- BIDSPath construction
- sourcedata discovery
- conversion from `sourcedata_root` to raw BIDS
- raw data loading via MNE-BIDS
- status-oriented batch behavior for missing inputs and existing outputs
- channel summaries
- automatic bad-channel candidate detection using Maxwell-based heuristics
- manual bad-channel QC utilities
- bad-channel JSON derivatives
- updating BIDS `channels.tsv` from manual bad-channel decisions
- binary-channel event extraction
- BIDS-compatible `events.tsv` writing
- notebook-friendly event and channel summaries
- preprocessing filter configuration
- filtered raw derivatives
- bad-segment annotation utilities
- bad-segment annotation derivatives
- existing-output policies for conversion, events, bad-channel QC, filtering, and annotations

Not yet implemented:

- ICA / SSP artifact handling
- cleaned raw derivatives
- epoching
- evoked/TFR/source analysis
- reports
- HPC/Slurm execution
- automated tests