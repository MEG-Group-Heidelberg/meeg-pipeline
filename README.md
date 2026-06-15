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
      cleaning.py
      cli.py
      config.py
      conversion.py
      epoching.py
      events.py
      evokeds.py
      io.py
      preprocessing.py
      project.py
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

Install the package in editable mode with development and interactive-plotting
dependencies:

```bash
cd ~/MEEG/meeg-pipeline
pip install -e ".[dev,qt]"
```

If you also want to use optional autoreject-based epoch cleaning, install:

```bash
pip install -e ".[dev,qt,autoreject]"
```

The `qt` extra installs the packages needed for interactive MNE browser windows,
including `mne-qt-browser`, `pyqt6`, and `pyqtgraph`.

Test the installation:

```bash
python -c "import meeg_pipeline; print(meeg_pipeline.__version__)"
meegpipe --version
```

## Creating a new project

A new project can be initialized with the command-line interface.

First make sure that the pipeline package is installed in your active Python
environment:

```bash
cd ~/MEEG
source .venv/bin/activate

cd ~/MEEG/meeg-pipeline
pip install -e ".[dev,qt]"
```

For autoreject workflows, use:

```bash
pip install -e ".[dev,qt,autoreject]"
```

Then create a new project folder from the location where the project should live.

Example on the internal drive:

```bash
cd ~/MEEG
meegpipe init-project my-meeg-project
```

Example on an external drive:

```bash
cd /Volumes/YourDrive/MEEG
meegpipe init-project my-meeg-project
```

Alternatively, pass the target directory explicitly:

```bash
meegpipe init-project my-meeg-project --base-dir /Volumes/YourDrive/MEEG
```

This creates:

```text
my-meeg-project/
  README.md
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
    05_ica_cleaning.ipynb

  sourcedata/
    sub-0001/
      meg/
        task-example/
          README.md
      ses-20260523/
        meg/
          task-example/
            README.md

  derivatives/
    meeg-pipeline/
```

Existing files are not overwritten by default. To recreate template files, use:

```bash
meegpipe init-project my-meeg-project --overwrite
```

After creating the project, enter the project folder:

```bash
cd /Volumes/YourDrive/MEEG/my-meeg-project
```

Then edit:

```text
configs/local.yaml
```

At minimum, check the project name and paths:

```yaml
project:
  name: "my-meeg-project"

paths:
  bids_root: "."
  sourcedata_root: "./sourcedata"
  derivatives_root: "./derivatives/meeg-pipeline"

sourcedata:
  sessions: "ignore"  # "ignore" | "include" | "auto"
```

If original source files live on an external drive or outside the project folder,
set `sourcedata_root` accordingly:

```yaml
paths:
  sourcedata_root: "/Volumes/YourDrive/source-data/my-meeg-project"
```

Relative paths are resolved relative to the project root.

Test the config from the project root:

```bash
meegpipe config-info --config configs/local.yaml
meegpipe sourcedata-info --config configs/local.yaml
meegpipe bids-info --config configs/local.yaml
```

In Jupyter or VS Code, select the Python kernel from the environment in which the
package was installed, for example:

```text
~/MEEG/.venv/bin/python
```

For interactive MNE plots in notebooks, run this before plotting:

```python
%matplotlib qt

import mne
mne.viz.set_browser_backend("qt")

print(mne.viz.get_browser_backend())
```

Expected output:

```text
qt
```

Interactive plots such as the following should then open in separate windows:

```python
raw.plot(block=True)
ica.plot_sources(raw_for_ica, block=True)
```

If plots do not open in an external window, restart the notebook kernel, run the
Qt setup cell before any plotting commands, and check that the selected kernel is
the intended virtual environment.

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
    05_ica_cleaning.ipynb
    06_epoching.ipynb
    07_evokeds.ipynb

  sourcedata/
    sub-0001/
      ses-yyyymmdd/
        meg/
          task-chords/
            original_chords_file.fif
          task-nochords/
            original_nochords_file.fif

  sub-0001/
    ses-yyyymmdd/
      meg/
        sub-0001_ses-yyyymmdd_task-chords_meg.fif
        sub-0001_ses-yyyymmdd_task-chords_meg.json
        sub-0001_ses-yyyymmdd_task-chords_channels.tsv
        sub-0001_ses-yyyymmdd_task-chords_events.tsv

        sub-0001_ses-yyyymmdd_task-nochords_meg.fif
        sub-0001_ses-yyyymmdd_task-nochords_meg.json
        sub-0001_ses-yyyymmdd_task-nochords_channels.tsv
        sub-0001_ses-yyyymmdd_task-nochords_events.tsv

  derivatives/
    meeg-pipeline/
      sub-0001/
        ses-yyyymmdd/
          meg/
            sub-0001_ses-yyyymmdd_task-chords_desc-badchannels.json
            sub-0001_ses-yyyymmdd_task-chords_desc-filtered_meg.fif
            sub-0001_ses-yyyymmdd_task-chords_desc-badsegments_annotations.fif
            sub-0001_ses-yyyymmdd_task-chords_desc-ica_ica.fif
            sub-0001_ses-yyyymmdd_task-chords_desc-icadecision.json
            sub-0001_ses-yyyymmdd_task-chords_desc-cleaned_meg.fif
            sub-0001_ses-yyyymmdd_task-chords_desc-cleaned_epo.fif
            sub-0001_ses-yyyymmdd_task-chords_desc-evoked_ave.fif
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
        sub-0001_task-chords_desc-ica_ica.fif
        sub-0001_task-chords_desc-icadecision.json
        sub-0001_task-chords_desc-cleaned_meg.fif
        sub-0001_task-chords_desc-cleaned_epo.fif
        sub-0001_task-chords_desc-evoked_ave.fif
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

The folder structure inside `sourcedata_root` should encode subject, task, and
optionally acquisition-date/session and run information. Session folders may be
used for source-data organization without necessarily becoming BIDS sessions.
This is controlled in `configs/local.yaml`:

```yaml
sourcedata:
  sessions: "ignore"  # "ignore" | "include" | "auto"
```

Supported session modes:

- `ignore`: `ses-*` folders are allowed in `sourcedata/`, but omitted from BIDS
  target paths. This is the recommended default for one-session analyses.
- `include`: `ses-*` folders become BIDS session entities. Use this for true
  multi-session BIDS datasets.
- `auto`: sessions are included only for subjects with more than one `ses-*`
  folder. This is convenient, but less reproducible than an explicit choice.

Without source session folders:

```text
sourcedata/
  sub-0001/
    meg/
      task-rest/
        <original_file>.fif
      task-auditory/
        <original_file>.fif
```

With acquisition-date folders:

```text
sourcedata/
  sub-0001/
    ses-20260523/
      meg/
        task-rest/
          <original_file>.fif
        task-auditory/
          <original_file>.fif
```

With runs:

```text
sourcedata/
  sub-0001/
    ses-20260523/
      meg/
        task-rest/
          run-01/
            <original_file>.fif
          run-02/
            <original_file>.fif
```

The source FIF filename itself can be arbitrary. However, each lowest-level
source folder should contain exactly one `.fif` file.

Examples:

```text
sourcedata/sub-0001/meg/task-rest/original_file.fif
sourcedata/sub-0001/ses-20260523/meg/task-rest/run-01/original_file.fif
```

The pipeline uses the folder structure to infer BIDS entities such as subject,
session, task, and run. If `sourcedata.sessions` is `ignore`, the source session
is retained in source-discovery summaries but not written to raw BIDS filenames.

### Raw BIDS data

The BIDS-formatted raw data are stored outside `sourcedata/`, using BIDS naming.

Example:

```text
sub-0001/
  ses-yyyymmdd/
    meg/
      sub-0001_ses-yyyymmdd_task-chords_meg.fif
      sub-0001_ses-yyyymmdd_task-chords_channels.tsv
      sub-0001_ses-yyyymmdd_task-chords_events.tsv
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
derivatives/meeg-pipeline/sub-0001/ses-yyyymmdd/meg/
  sub-0001_ses-yyyymmdd_task-chords_desc-badchannels.json
  sub-0001_ses-yyyymmdd_task-chords_desc-filtered_meg.fif
  sub-0001_ses-yyyymmdd_task-chords_desc-badsegments_annotations.fif
  sub-0001_ses-yyyymmdd_task-chords_desc-ica_ica.fif
  sub-0001_ses-yyyymmdd_task-chords_desc-icadecision.json
  sub-0001_ses-yyyymmdd_task-chords_desc-cleaned_meg.fif
  sub-0001_ses-yyyymmdd_task-chords_desc-cleaned_epo.fif
  sub-0001_ses-yyyymmdd_task-chords_desc-evoked_ave.fif
```

The raw BIDS FIF files should not be modified during preprocessing.

Raw outputs are intended to be BIDS-compliant. Derivative outputs follow a
BIDS-Derivatives-style organization and MNE naming conventions.

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

Recommended session naming for acquisition-date folders:

```text
ses-20260523
ses-20260602
```

Use dates without hyphens because BIDS entity labels are alphanumeric. Date-like
session labels also make it easier to match recordings to empty-room
measurements. Numeric labels such as `ses-yyyymmdd` are still valid when they better
fit the project.

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
sub-0001_ses-yyyymmdd_task-chords_run-01_meg.fif
sub-0001_ses-yyyymmdd_task-chords_run-02_meg.fif
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

runtime:
  n_jobs: 4
  thread_limits: true

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

cleaning:
  ica:
    n_components: 60
    method: "fastica"
    random_state: 97
    max_iter: "auto"
    decim: 4
    fit_resample_sfreq: null

epochs:
  tmin: -1.0
  tmax: 1.0
  baseline: null
  bad_interpolation: "epochs"

autoreject:
  enabled: false
  use: null
  consensus_percs: null
  n_interpolates: null
  subset: null

source:
  spacing: "ico5"
  noise_cov_mode: "erm"
  target_labels: null
  parcellation: "aparc_sub"
  extract_mode: "mean"
  inverse_method: "dSPM"
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

For ICA fitting, `decim` uses MNE's native decimation during the ICA fit. If
`decim` is set, `fit_resample_sfreq` is ignored. A typical setting for long
1000 Hz recordings is:

```yaml
cleaning:
  ica:
    n_components: 60
    decim: 4
    fit_resample_sfreq: null
```

From the project root, test the config:

```bash
meegpipe config-info --config configs/local.yaml
```

Then inspect the source data and BIDS structure:

```bash
meegpipe sourcedata-info --config configs/local.yaml
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

## Event extraction and event derivation

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

The pipeline distinguishes between trigger extraction and project-specific event
derivation.

```text
Trigger extraction:
  Raw BIDS data
  -> acquisition-level trigger anchors
  -> raw BIDS-compatible events.tsv

Project-specific event derivation:
  trigger anchors
  + stimulus metadata
  + project-specific timing rules
  -> analysis-ready derivative events.tsv
```

The raw BIDS `events.tsv` files are written by the raw/event notebook and remain
trigger-derived. Optional project-specific notebooks may derive richer analysis
events and write them as derivatives, for example:

```text
derivatives/meeg-pipeline/sub-0001/meg/
  sub-0001_task-chords_desc-analysis_events.tsv
```

Downstream analysis should prefer analysis-event derivatives if they exist and
fall back to raw BIDS events otherwise.

## Event handling principle

The pipeline should not assume that recorded trigger codes are always identical
to the final analysis events.

Instead, event handling should be table-based.

A simple trigger-derived event table may look like this:

```text
onset    duration    trial_type    value    sample
1.532    0.0         trigger_1     1        1532
3.847    0.0         trigger_1     1        3847
```

More complex projects may derive analysis events from anchor triggers and
external metadata.

Example:

```text
onset    duration    trial_type        note_id    note_index    key_signature    scale_degree    non_diatonic
42.000   0.0         key_change        128        0             3                1               0
42.500   0.0         non_diatonic      129        1             3                2               1
43.000   0.0         note              130        2             3                3               0
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

## ICA cleaning

ICA cleaning is used to remove stereotyped artifact components from filtered
continuous data.

Recommended workflow:

1. Load filtered raw data.
2. Apply saved bad-channel decisions.
3. Apply saved bad-segment annotations.
4. Fit ICA on the filtered data.
5. Inspect ICA components interactively.
6. Mark artifact components in `ica.plot_sources`.
7. Save the selected component indices as an ICA decision JSON.
8. Apply the ICA decision and write a cleaned raw derivative.

Example files:

```text
derivatives/meeg-pipeline/sub-1409/meg/
  sub-1409_task-chords_desc-ica_ica.fif
  sub-1409_task-chords_desc-icadecision.json
  sub-1409_task-chords_desc-cleaned_meg.fif
```

The `desc-cleaned_meg.fif` file is the ICA-cleaned continuous raw derivative.
It is the recommended input for epoching and later analysis steps.

ICA decisions are recording-specific. In other words, decisions are made per
combination of subject, session, task, and run. Component index `5` in one
recording is not the same component as index `5` in another recording.

A conservative ICA decision is recommended. Components should only be excluded
when they clearly represent artifact sources such as heartbeat, eye movement,
muscle bursts, or technical noise. Single outliers inside a component are usually
better handled as bad segments, not by removing the entire component.

## Epoching and evokeds

Epoching turns cleaned continuous data into trial-wise data.

Recommended workflow:

1. Load `desc-cleaned_meg.fif`.
2. Load project-specific `desc-analysis_events.tsv` if it exists.
3. Otherwise load the raw BIDS `events.tsv`.
4. Create MNE `Epochs`.
5. Keep the full events table as `epochs.metadata`.
6. Save `desc-cleaned_epo.fif`.

Evokeds are created from saved epochs using project-specific condition
definitions.

Recommended workflow:

1. Load `desc-cleaned_epo.fif`.
2. Inspect `epochs.metadata`.
3. Define project-specific conditions as metadata queries or old-style event ID
   lists.
4. Average selected epochs per condition.
5. Save `desc-evoked_ave.fif`.

Example condition definitions:

```python
CONDITIONS = {
    "non_diatonic": "non_diatonic in [1, 2, 3, 4, 5]",
    "key_change": "note_index == 0",
}
```

Old-style event-code definitions are also possible:

```python
CONDITIONS = {
    "some_condition": [1, 5, 9, 12],
}
```

Condition definitions are project-specific and should usually live in the
evoked notebook rather than in the reusable library.

## Notebook workflow

The recommended project workflow is notebook-oriented.

A project may contain notebooks such as:

```text
notebooks/
  00_project_summary.ipynb
  01_raw_bids_and_bad_channels.ipynb
  02_project_specific_events.ipynb
  03_preprocessing.ipynb
  04_artifact_annotation.ipynb
  05_ica_cleaning.ipynb
  06_epoching.ipynb
  07_evokeds.ipynb
```

Suggested roles:

```text
00_project_summary.ipynb
  Read-only dashboard.
  Shows what data exist, what has been computed, event status, bad-channel status,
  filtered-derivative status, bad-segment annotation status, ICA status, cleaned-
  raw status, epoch status, and evoked status.

01_raw_bids_and_bad_channels.ipynb
  Active raw-data and bad-channel notebook.
  Discovers sourcedata, converts to raw BIDS, extracts trigger-derived events,
  inspects channels, performs manual bad-channel QC, and updates channels.tsv.

02_project_specific_events.ipynb
  Optional event-derivation notebook.
  Reads trigger-derived events.tsv files and derives project-specific analysis-
  ready event tables from trigger anchors and stimulus metadata. This notebook
  can be skipped when trigger-derived events are already the analysis events.

03_preprocessing.ipynb
  Preprocessing notebook.
  Applies saved bad-channel decisions, filters data, and writes filtered raw
  derivatives.

04_artifact_annotation.ipynb
  Bad-segment annotation notebook.
  Loads filtered data, interactively marks BAD_* time spans, and writes bad-
  segment annotation derivatives.

05_ica_cleaning.ipynb
  ICA cleaning notebook.
  Fits ICA models, saves ICA component-exclusion decisions, and writes cleaned
  raw derivatives.

06_epoching.ipynb
  Epoching notebook.
  Creates epochs from cleaned raw data and either analysis-event derivatives or
  raw BIDS events.

07_evokeds.ipynb
  Evoked-response notebook.
  Defines project-specific conditions from epoch metadata and writes evoked
  response files.
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

analysis_events:
  skip / overwrite

bad_channels:
  load / overwrite

annotations:
  load / overwrite

filtering:
  skip / overwrite

ica:
  skip / overwrite

ica_decision:
  load / overwrite

cleaned_raw:
  skip / overwrite

epochs:
  skip / overwrite

evokeds:
  skip / overwrite
```

For notebooks, a central variable can be used:

```python
OVERWRITE_STEPS = []
OVERWRITE_STEPS = ["events"]
OVERWRITE_STEPS = ["analysis_events"]
OVERWRITE_STEPS = ["bad_channels"]
OVERWRITE_STEPS = ["annotations"]
OVERWRITE_STEPS = ["filtering"]
OVERWRITE_STEPS = ["ica"]
OVERWRITE_STEPS = ["ica_decision"]
OVERWRITE_STEPS = ["cleaned_raw"]
OVERWRITE_STEPS = ["epochs"]
OVERWRITE_STEPS = ["evokeds"]
OVERWRITE_STEPS = ["ica_decision", "cleaned_raw"]
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
analysis_events  -> skip existing derivative analysis-event files
bad_channels     -> load existing bad-channel decisions
annotations      -> load existing bad-segment annotations
filtering        -> skip existing filtered derivatives
ica              -> skip existing ICA files
ica_decision     -> load existing ICA decisions
cleaned_raw      -> skip existing cleaned raw derivatives
epochs           -> skip existing epochs
evokeds          -> skip existing evoked files
```

To recompute a specific step, either delete the corresponding output file
intentionally or add the step to `OVERWRITE_STEPS`.

## Current command-line tools

The package currently provides a small command-line interface called `meegpipe`.

Show the installed version:

```bash
meegpipe --version
```

Create a new project scaffold:

```bash
meegpipe init-project my-meeg-project
```

Create a project scaffold in a specific directory:

```bash
meegpipe init-project my-meeg-project --base-dir /Volumes/YourDrive/MEEG
```

Overwrite existing template files:

```bash
meegpipe init-project my-meeg-project --overwrite
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

Write BIDS-compatible trigger-derived `events.tsv` files:

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

mkdir -p sourcedata/sub-0001/ses-yyyymmdd/meg/task-chords
mkdir -p sourcedata/sub-0001/ses-yyyymmdd/meg/task-nochords
```

Copy the original FIF files into the corresponding `sourcedata/` task folders:

```text
sourcedata/sub-0001/ses-yyyymmdd/meg/task-chords/<original_chords_file>.fif
sourcedata/sub-0001/ses-yyyymmdd/meg/task-nochords/<original_nochords_file>.fif
```

For projects without sessions, use:

```text
sourcedata/sub-0001/meg/task-chords/<original_chords_file>.fif
sourcedata/sub-0001/meg/task-nochords/<original_nochords_file>.fif
```

Do not modify these source files.

The corresponding BIDS raw files will later be generated under:

```text
sub-0001/ses-yyyymmdd/meg/
```

or, if no session level is used:

```text
sub-0001/meg/
```

with filenames such as:

```text
sub-0001_ses-yyyymmdd_task-chords_meg.fif
sub-0001_ses-yyyymmdd_task-nochords_meg.fif
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
sub-0001/ses-yyyymmdd/meg/sub-0001_ses-yyyymmdd_task-chords_meg.fif
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
sub-0001/ses-yyyymmdd/meg/sub-0001_ses-yyyymmdd_task-nochords_meg.fif
```

## Development status

Early development.

Currently implemented:

- Python package structure
- `meegpipe` command-line entry point
- project scaffold creation with `meegpipe init-project`
- project config loading
- configurable `sourcedata_root`
- runtime and analysis defaults in `configs/local.yaml`
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
- BIDS-compatible trigger-derived `events.tsv` writing
- optional project-specific analysis-event derivation notebooks
- preprocessing filter configuration
- filtered raw derivatives
- bad-segment annotation utilities
- bad-segment annotation derivatives
- ICA fitting utilities
- ICA decision JSON derivatives
- cleaned raw derivatives
- epoching utilities
- evoked-response utilities
- existing-output policies for conversion, events, analysis events, bad-channel QC, filtering, annotations, ICA, ICA decisions, cleaned raw derivatives, epochs, and evokeds

Not yet implemented:

- SSP / empty-room based cleaning
- source analysis
- reports
- HPC/Slurm execution
- automated tests
