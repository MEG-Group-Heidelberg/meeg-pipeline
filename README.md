# meeg-pipeline

A modular, BIDS-compatible M/EEG analysis pipeline built on top of
[MNE-Python](https://mne.tools/stable/index.html) and
[MNE-BIDS](https://mne.tools/mne-bids/stable/index.html).

The goal of this project is to provide a transparent and extensible pipeline for
MEG and EEG data analysis. The pipeline is developed step by step, with a strong
focus on understanding each processing stage.

The package contains reusable pipeline code. Concrete research projects should
live in separate project folders and use this package as a library.

## Design principles

- BIDS-compatible project organization
- Clear separation between reusable pipeline code and project-specific data
- Original source data are preserved unchanged
- Raw BIDS FIF files are treated as immutable analysis inputs
- BIDS sidecar metadata such as `channels.tsv` may be updated when appropriate
- Processed M/EEG outputs are written to `derivatives/meeg-pipeline/`
- FreeSurfer outputs are written to a separate `derivatives/freesurfer/` tree
- Intermediate preprocessing steps are saved as separate files
- Existing output files are not overwritten by default
- Missing inputs are reported as status values instead of interrupting batch workflows
- Manual QC decisions are stored explicitly
- Event handling is table-based and metadata-friendly
- Anatomy preparation and MEG preprocessing are separate, partly independent workflows
- Notebook-friendly interactive workflow
- CLI-friendly batch workflow
- Local and HPC-compatible execution
- Built on MNE-Python, MNE-BIDS, MNE-Coregistration, and FreeSurfer-compatible anatomy workflows

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
      anatomy.py
      bids.py
      channels.py
      cleaning.py
      cli.py
      config.py
      conversion.py
      epoching.py
      event_derivatives.py
      events.py
      evokeds.py
      io.py
      paths.py
      preprocessing.py
      project.py
      qc.py
      sourcedata.py
      workflow.py
```

Concrete research projects should live in separate folders, for example:

```text
~/MEEG/
  meeg-pipeline/
  my-meeg-project/
```

The `meeg-pipeline` repository contains reusable code. The project folder
contains data, project-specific configs, notebooks, and outputs.

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

For anatomy preparation and source modeling, install FreeSurfer separately and
make sure that `FREESURFER_HOME` points to the FreeSurfer installation, or set
`freesurfer.home` in the project config.

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

A project should then be organized like this:

```text
my-meeg-project/
  README.md
  dataset_description.json
  participants.tsv

  configs/
    local.yaml

  notebooks/
    00_project_summary.ipynb

    1A_anatomy/
      01_convert_mri.ipynb
      02_recon.ipynb
      03_anatomy_setup.ipynb
      04_coregistration.ipynb

    1B_meg_preprocessing/
      01_raw_bids_and_events.ipynb
      02_project_specific_events.ipynb
      03_preprocessing.ipynb
      04_artifact_annotation.ipynb
      05_ica_cleaning.ipynb
      06_epoching.ipynb
      07_evokeds.ipynb

    2_source_modeling/
      # Forward/inverse/source-estimate notebooks will live here.

    3_analysis/
      # Project-specific analysis notebooks will live here.

  sourcedata/
    sub-0001/
      meg/
        task-example/
          <original_file>.fif
      ses-20260523/
        meg/
          task-example/
            <original_file>.fif

    mri_raw/
      sub-0001/
        T1/
          <many DICOM files>
        T2/
          <many DICOM files>

    mri/
      sub-0001/
        anat/
          sub-0001_T1w.nii.gz
          sub-0001_T2w.nii.gz

  derivatives/
    meeg-pipeline/
    freesurfer/
      subjects/
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
  mri_raw_root: "./sourcedata/mri_raw"
  mri_root: "./sourcedata/mri"

freesurfer:
  home: "/Applications/freesurfer"
  subjects_dir: "./derivatives/freesurfer/subjects"

sourcedata:
  sessions: "ignore"  # "ignore" | "include" | "auto"
```

If original source files live on an external drive or outside the project folder,
set `sourcedata_root`, `mri_raw_root`, or `mri_root` accordingly.

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
mne.gui.coregistration(...)
```

If plots do not open in an external window, restart the notebook kernel, run the
Qt setup cell before any plotting commands, and check that the selected kernel is
the intended virtual environment.

## Project organization

A concrete M/EEG project should be organized separately from the pipeline
library.

The project folder contains:

- project-level BIDS files such as `dataset_description.json` and `participants.tsv`
- project-specific configuration in `configs/`
- workflow notebooks in `notebooks/`
- original source files in `sourcedata/`
- raw BIDS files at the BIDS root
- M/EEG processed outputs in `derivatives/meeg-pipeline/`
- FreeSurfer anatomy outputs in `derivatives/freesurfer/subjects/`

The current notebook workflow is divided into independent or partly independent
blocks:

```text
notebooks/
  00_project_summary.ipynb

  1A_anatomy/
    01_convert_mri.ipynb
    02_recon.ipynb
    03_anatomy_setup.ipynb
    04_coregistration.ipynb

  1B_meg_preprocessing/
    01_raw_bids_and_events.ipynb
    02_project_specific_events.ipynb
    03_preprocessing.ipynb
    04_artifact_annotation.ipynb
    05_ica_cleaning.ipynb
    06_epoching.ipynb
    07_evokeds.ipynb

  2_source_modeling/
    # Forward solution, noise covariance, inverse operator, source estimates,
    # morphing, and label time courses.

  3_analysis/
    # Project-specific sensor-level, source-level, statistical, and figure notebooks.
```

`1A_anatomy` and `1B_meg_preprocessing` can often be run independently. They come
together later in `2_source_modeling`, where MEG/EEG recordings need anatomical
source spaces, BEM solutions, and coregistration transforms.

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

Here, `ses-20260523` follows the `ses-<YYYYMMDD>` convention and denotes the
acquisition date of the original recording.

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
source session, task, and run. If `sourcedata.sessions` is `ignore`, the source
session is retained in source-discovery summaries but not written to raw BIDS
filenames.

### MRI inputs

MRI inputs are handled separately from MEG/EEG source FIF files.

Raw MRI exports from the MRI lab often arrive as DICOM series consisting of many
individual files. These raw exports should be stored separately from converted
NIfTI/MGZ files:

```text
sourcedata/
  mri_raw/
    sub-0001/
      T1/
        <many DICOM files>
      T2/
        <many DICOM files>
```

The `1A_anatomy/01_convert_mri.ipynb` notebook converts these raw MRI inputs into
a predictable project layout:

```text
sourcedata/
  mri/
    sub-0001/
      anat/
        sub-0001_T1w.nii.gz
        sub-0001_T1w.json
        sub-0001_T2w.nii.gz
        sub-0001_T2w.json
        T1.mgz
        T2.mgz
```

`T1` is the required input for the standard `recon-all` workflow. `T2` is
optional and can be used as an additional input for pial-surface refinement when
configured. A subject with only T2 and no T1 is reported as an unsupported or
missing-input case in the standard workflow.

These MRI paths are configured with:

```yaml
paths:
  mri_raw_root: "./sourcedata/mri_raw"
  mri_root: "./sourcedata/mri"

anatomy:
  t1_pattern: "{subject}/anat/*T1w*.nii*"
  t2_pattern: "{subject}/anat/*T2w*.nii*"
  conversion:
    converter: "dcm2niix"
    t1_source_pattern: "{subject}/T1"
    t2_source_pattern: "{subject}/T2"
    make_mgz: true
```

### Raw BIDS data

The BIDS-formatted raw MEG/EEG data are stored outside `sourcedata/`, using BIDS
naming.

With BIDS sessions:

```text
sub-0001/
  ses-20260523/
    meg/
      sub-0001_ses-20260523_task-rest_meg.fif
      sub-0001_ses-20260523_task-rest_meg.json
      sub-0001_ses-20260523_task-rest_channels.tsv
      sub-0001_ses-20260523_task-rest_events.tsv
```

Without BIDS sessions:

```text
sub-0001/
  meg/
    sub-0001_task-rest_meg.fif
    sub-0001_task-rest_meg.json
    sub-0001_task-rest_channels.tsv
    sub-0001_task-rest_events.tsv
```

Raw BIDS FIF files are generated from the original source data, preferably using
MNE-BIDS. They should be treated as immutable analysis inputs.

The raw BIDS area should not contain intermediate preprocessing outputs.

### BIDS sidecars

Some BIDS sidecar files are part of the raw BIDS dataset and may be updated when
metadata decisions are made.

For example, manual bad-channel decisions should update:

```text
sub-0001/meg/sub-0001_task-rest_channels.tsv
```

or, with sessions:

```text
sub-0001/ses-20260523/meg/sub-0001_ses-20260523_task-rest_channels.tsv
```

using the BIDS columns:

```text
status
status_description
```

The raw FIF file itself should remain unchanged.

### M/EEG derivatives

All M/EEG processed outputs and explicit pipeline decisions are written to:

```text
derivatives/meeg-pipeline/
```

Derivative files are organized in step-specific subfolders below each
subject/session/datatype folder:

```text
derivatives/meeg-pipeline/sub-0001/meg/qc/
derivatives/meeg-pipeline/sub-0001/meg/preprocessing/
derivatives/meeg-pipeline/sub-0001/meg/annotations/
derivatives/meeg-pipeline/sub-0001/meg/cleaning/
derivatives/meeg-pipeline/sub-0001/meg/events/
derivatives/meeg-pipeline/sub-0001/meg/epochs/
derivatives/meeg-pipeline/sub-0001/meg/evokeds/
derivatives/meeg-pipeline/sub-0001/meg/coregistration/
```

With BIDS sessions, the same step folders live under the session level:

```text
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/qc/
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/preprocessing/
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/annotations/
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/cleaning/
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/events/
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/epochs/
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/evokeds/
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/coregistration/
```

Examples:

```text
derivatives/meeg-pipeline/sub-0001/meg/qc/
  sub-0001_task-rest_desc-badchannels.json

derivatives/meeg-pipeline/sub-0001/meg/preprocessing/
  sub-0001_task-rest_desc-filtered_meg.fif

derivatives/meeg-pipeline/sub-0001/meg/annotations/
  sub-0001_task-rest_desc-badsegments_annotations.fif

derivatives/meeg-pipeline/sub-0001/meg/cleaning/
  sub-0001_task-rest_desc-ica_ica.fif
  sub-0001_task-rest_desc-icadecision.json
  sub-0001_task-rest_desc-cleaned_meg.fif

derivatives/meeg-pipeline/sub-0001/meg/events/
  sub-0001_task-rest_desc-analysis_events.tsv
  sub-0001_task-rest_desc-analysis_events.json

derivatives/meeg-pipeline/sub-0001/meg/epochs/
  sub-0001_task-rest_desc-cleaned_epo.fif

derivatives/meeg-pipeline/sub-0001/meg/evokeds/
  sub-0001_task-rest_desc-evoked_ave.fif

derivatives/meeg-pipeline/sub-0001/meg/coregistration/
  sub-0001_task-rest_desc-coreg_trans.fif
```

The raw BIDS FIF files should not be modified during preprocessing.

Raw outputs are intended to be BIDS-compliant. Derivative outputs follow a
BIDS-Derivatives-style organization and MNE naming conventions.

### FreeSurfer derivatives

FreeSurfer outputs should not be stored inside the FreeSurfer installation
folder. Keep software and project outputs separate:

```text
/Applications/freesurfer/
  # FreeSurfer software installation

my-meeg-project/
  derivatives/
    freesurfer/
      subjects/
        sub-0001/
          mri/
          surf/
          bem/
          label/
        fsaverage/
          mri/
          surf/
          label/
```

The project config should point to this project-specific `SUBJECTS_DIR`:

```yaml
freesurfer:
  home: "/Applications/freesurfer"
  subjects_dir: "./derivatives/freesurfer/subjects"
```

`FREESURFER_HOME` identifies the FreeSurfer software installation.
`SUBJECTS_DIR` identifies the project-specific FreeSurfer subject database.

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

For anatomy notebooks, use the same subject labels consistently in `sourcedata/`,
`sourcedata/mri`, raw BIDS, and FreeSurfer. If your project uses `sub-0001` in
folder names, set the anatomy patterns accordingly, for example:

```yaml
anatomy:
  t1_pattern: "sub-{subject}/anat/*T1w*.nii*"
  t2_pattern: "sub-{subject}/anat/*T2w*.nii*"
```

If your project uses bare subject labels such as `0001`, use:

```yaml
anatomy:
  t1_pattern: "{subject}/anat/*T1w*.nii*"
  t2_pattern: "{subject}/anat/*T2w*.nii*"
```

### Sessions

Sessions are optional in BIDS.

Use sessions if the project contains distinct measurement appointments, visits,
timepoints, or repeated acquisitions that should be modeled as BIDS sessions.

If a project is known to contain only one analysis session per participant, the
`ses-...` level can be omitted from BIDS even if `sourcedata/` contains
acquisition-date folders for source-data organization.

Recommended date-like session labels use the pattern `ses-<YYYYMMDD>`, where
`YYYY` is the four-digit year, `MM` is the two-digit month, and `DD` is the
two-digit day.

For example, recordings acquired on May 23, 2026 and June 2, 2026 should use:

```text
ses-20260523
ses-20260602
```

Date-like labels such as `ses-20260523` are valid because the label part is
alphanumeric. Avoid hyphens or underscores inside BIDS labels; use
`ses-20260523` rather than `ses-2026-05-23` or `ses-2026_05_23`.

The `sourcedata.sessions` config decides whether source-data session folders are
included in BIDS output:

```yaml
sourcedata:
  sessions: "ignore"   # source session folders are not written to BIDS
```

or:

```yaml
sourcedata:
  sessions: "include"  # source session folders become BIDS sessions
```

### Tasks

The `task-...` entity describes the experimental paradigm or recording context.

Example:

```text
task-rest
task-auditory
task-visual
```

Even if recordings are passive or share the same acquisition protocol, they can
be represented as different tasks if they correspond to distinct experimental
contexts.

### Runs

Runs are used for repeated recordings of the same task within the same session.

Example:

```text
sub-0001_ses-20260523_task-rest_run-01_meg.fif
sub-0001_ses-20260523_task-rest_run-02_meg.fif
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
  "Authors": ["Your Name"]
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
  mri_raw_root: "./sourcedata/mri_raw"
  mri_root: "./sourcedata/mri"

freesurfer:
  home: "/Applications/freesurfer"
  subjects_dir: "./derivatives/freesurfer/subjects"

anatomy:
  t1_pattern: "{subject}/anat/*T1w*.nii*"
  t2_pattern: "{subject}/anat/*T2w*.nii*"
  conversion:
    converter: "dcm2niix"
    t1_source_pattern: "{subject}/T1"
    t2_source_pattern: "{subject}/T2"
    make_mgz: true
  recon:
    use_t1: true
    use_t2: false
  watershed:
    volume: "T1"
  bem:
    method: "watershed"
    conductivity: [0.3]
    ico: 4
  source_space:
    spacing: "ico5"
    surface: "white"
    add_dist: false
  volume_source_space:
    enabled: false
    spacing: 5.0
  labels:
    morph_from: "fsaverage"
    parcellations:
      - "aparc_sub"

sourcedata:
  sessions: "ignore"  # "ignore" | "include" | "auto"

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

For MEG-only source modeling, a one-layer BEM is usually sufficient:

```yaml
anatomy:
  bem:
    conductivity: [0.3]
```

For EEG or combined MEG+EEG source modeling, use a three-layer BEM:

```yaml
anatomy:
  bem:
    conductivity: [0.3, 0.006, 0.3]
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

Normal pipeline states are reported as status values instead of interrupting the
whole batch process.

Common status values include:

```text
missing_input
missing_t1
unsupported_t2_only
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

## Anatomy preparation workflow

The anatomy workflow lives in `notebooks/1A_anatomy/` and is separate from the
MEG preprocessing workflow.

### `01_convert_mri.ipynb`

This notebook prepares MRI inputs.

Typical input:

```text
sourcedata/mri_raw/sub-0001/T1/
sourcedata/mri_raw/sub-0001/T2/
```

Typical output:

```text
sourcedata/mri/sub-0001/anat/sub-0001_T1w.nii.gz
sourcedata/mri/sub-0001/anat/sub-0001_T2w.nii.gz
sourcedata/mri/sub-0001/anat/T1.mgz
sourcedata/mri/sub-0001/anat/T2.mgz
```

The T2 input is optional. The standard pipeline requires T1 for `recon-all`.

### `02_recon.ipynb`

This notebook runs FreeSurfer `recon-all`.

Supported input scenarios:

```text
T1 only:
  Standard T1-based recon-all.

T1 + T2 with anatomy.recon.use_t2: false:
  T2 exists but is ignored.

T1 + T2 with anatomy.recon.use_t2: true:
  T1-based recon-all with T2 pial refinement.

T2 only:
  Reported as unsupported for the standard recon-all workflow.
```

FreeSurfer subject outputs are written to:

```text
derivatives/freesurfer/subjects/sub-0001/
```

### `03_anatomy_setup.ipynb`

This notebook prepares geometry files required for source modeling:

- watershed BEM surfaces
- dense scalp surfaces for coregistration support
- BEM model and BEM solution
- surface source space
- optional source-space distances
- optional volume source space
- parcellation labels morphed from `fsaverage`

### `04_coregistration.ipynb`

This notebook opens the interactive MNE coregistration GUI for selected subjects
or recordings.

The notebook uses a raw BIDS recording as `inst` and the matching FreeSurfer
subject as the MRI subject. It expects the user to save the transform to the
printed derivative path.

Example output:

```text
derivatives/meeg-pipeline/sub-0001/meg/coregistration/
  sub-0001_task-rest_desc-coreg_trans.fif
```

By default, the GUI is opened only when the expected `trans.fif` file does not
exist. Add `"coregistration"` to `OVERWRITE_STEPS` to rerun coregistration for
existing transforms.

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
  + stimulus or task metadata
  + project-specific timing rules
  -> analysis-ready derivative events.tsv
```

The raw BIDS `events.tsv` files are written by the raw/event notebook and remain
trigger-derived. Optional project-specific notebooks may derive richer analysis
events and write them as derivatives, for example:

```text
derivatives/meeg-pipeline/sub-0001/meg/events/
  sub-0001_task-rest_desc-analysis_events.tsv
  sub-0001_task-rest_desc-analysis_events.json
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
onset    duration    trial_type     event_id    event_index    condition    feature_value
42.000   0.0         condition_a    128         0              A            3
42.500   0.0         condition_b    129         1              B            7
43.000   0.0         condition_a    130         2              A            4
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
sub-0001/meg/sub-0001_task-rest_meg.fif
sub-0001/meg/sub-0001_task-rest_channels.tsv

derivatives/meeg-pipeline/sub-0001/meg/qc/
  sub-0001_task-rest_desc-badchannels.json
```

The raw FIF file remains unchanged. The BIDS sidecar `channels.tsv` is updated
using the columns:

```text
status
status_description
```

Example bad-channel JSON:

```json
{
  "subject": "0001",
  "session": null,
  "task": "rest",
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
derivatives/meeg-pipeline/sub-0001/meg/annotations/
  sub-0001_task-rest_desc-badsegments_annotations.fif
```

These annotations can later be applied to filtered or cleaned data. Downstream
MNE steps can use the standard `reject_by_annotation=True` behavior to ignore bad
spans.

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
derivatives/meeg-pipeline/sub-0001/meg/cleaning/
  sub-0001_task-rest_desc-ica_ica.fif
  sub-0001_task-rest_desc-icadecision.json
  sub-0001_task-rest_desc-cleaned_meg.fif
```

The `desc-cleaned_meg.fif` file is the ICA-cleaned continuous raw derivative. It
is the recommended input for epoching and later analysis steps.

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
6. Optionally apply autoreject-based cleaning.
7. Save `desc-cleaned_epo.fif`.

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
    "condition_a": "trial_type == 'condition_a'",
    "high_feature": "feature_value >= 5",
}
```

Old-style event-code definitions are also possible:

```python
CONDITIONS = {
    "some_condition": [1, 5, 9, 12],
}
```

Condition definitions are project-specific and should usually live in the evoked
notebook rather than in the reusable library.

## Notebook workflow

The recommended project workflow is notebook-oriented.

A project may contain notebooks such as:

```text
notebooks/
  00_project_summary.ipynb

  1A_anatomy/
    01_convert_mri.ipynb
    02_recon.ipynb
    03_anatomy_setup.ipynb
    04_coregistration.ipynb

  1B_meg_preprocessing/
    01_raw_bids_and_events.ipynb
    02_project_specific_events.ipynb
    03_preprocessing.ipynb
    04_artifact_annotation.ipynb
    05_ica_cleaning.ipynb
    06_epoching.ipynb
    07_evokeds.ipynb

  2_source_modeling/
    # Forward solution, noise covariance, inverse operator, source estimates,
    # morphing, and label time courses.

  3_analysis/
    # Project-specific analyses and figures.
```

Suggested roles:

```text
00_project_summary.ipynb
  Read-only dashboard.
  Shows what data exist, what has been computed, event status, bad-channel status,
  filtered-derivative status, bad-segment annotation status, ICA status, cleaned-
  raw status, epoch status, evoked status, and anatomy/source-preparation status.

1A_anatomy/01_convert_mri.ipynb
  Optional MRI conversion notebook.
  Converts raw MRI lab exports such as DICOM series into project-standard T1/T2
  NIfTI and optional MGZ files.

1A_anatomy/02_recon.ipynb
  FreeSurfer reconstruction notebook.
  Runs T1-based recon-all and optionally uses T2 for pial-surface refinement.

1A_anatomy/03_anatomy_setup.ipynb
  Anatomy setup notebook.
  Creates BEM surfaces, BEM model/solution, source spaces, optional source
  distances, optional volume source space, and morphed labels.

1A_anatomy/04_coregistration.ipynb
  Coregistration notebook.
  Opens the interactive MNE coregistration GUI and stores trans.fif derivatives.

1B_meg_preprocessing/01_raw_bids_and_events.ipynb
  Active raw-data and bad-channel notebook.
  Discovers sourcedata, converts to raw BIDS, extracts trigger-derived events,
  inspects channels, performs manual bad-channel QC, and updates channels.tsv.

1B_meg_preprocessing/02_project_specific_events.ipynb
  Optional event-derivation notebook.
  Reads trigger-derived events.tsv files and derives project-specific analysis-
  ready event tables from trigger anchors and stimulus/task metadata. This
  notebook can be skipped when trigger-derived events are already the analysis
  events.

1B_meg_preprocessing/03_preprocessing.ipynb
  Preprocessing notebook.
  Applies saved bad-channel decisions, filters data, and writes filtered raw
  derivatives.

1B_meg_preprocessing/04_artifact_annotation.ipynb
  Bad-segment annotation notebook.
  Loads filtered data, interactively marks BAD_* time spans, and writes bad-
  segment annotation derivatives.

1B_meg_preprocessing/05_ica_cleaning.ipynb
  ICA cleaning notebook.
  Fits ICA models, saves ICA component-exclusion decisions, and writes cleaned
  raw derivatives.

1B_meg_preprocessing/06_epoching.ipynb
  Epoching notebook.
  Creates epochs from cleaned raw data and either analysis-event derivatives or
  raw BIDS events.

1B_meg_preprocessing/07_evokeds.ipynb
  Evoked-response notebook.
  Defines project-specific conditions from epoch metadata and writes evoked
  response files.

2_source_modeling/
  Future source-modeling notebooks.
  These will combine outputs from 1A and 1B: coregistration transforms, BEM
  solutions, source spaces, cleaned data, epochs, evokeds, and noise covariance.

3_analysis/
  Project-specific analysis notebooks.
  These should contain study-specific statistics, plotting, reports, and final
  figures rather than reusable pipeline infrastructure.
```

Notebook steps should call reusable library functions rather than implementing
large processing logic directly inside notebooks.


## Notebook recording selection defaults

Recording-based notebooks use the same selection variables by default:

```python
SUBJECTS = "all"
SESSIONS = "all"
TASKS = "all"
RUNS = "all"
```

The value `"all"` means: use all values that exist in the current project. For
optional BIDS entities such as `session` and `run`, `"all"` also works in
projects that do not use that entity. In that case, the selection resolves to a
single `None` value internally, so no `ses-...` or `run-...` entity is added to
paths.

This makes the same notebooks work for:

```text
single-session projects without run entities
multi-session projects
multi-run projects
multi-task projects
```

Use explicit values only when you want to restrict processing:

```python
SUBJECTS = ["0001", "0002"]
SESSIONS = "all"
TASKS = ["rest"]
RUNS = "all"
```

Use `None` only when you explicitly want to force a missing optional entity. For
normal notebook use, prefer `"all"`.

Anatomy-only notebooks such as `1A_anatomy/01_convert_mri.ipynb`,
`1A_anatomy/02_recon.ipynb`, and `1A_anatomy/03_anatomy_setup.ipynb` operate at
the subject level and therefore usually only need:

```python
SUBJECTS = "all"
```

Coregistration bridges anatomy and MEG recordings and therefore follows the
recording-based selection pattern.

## Existing-output and overwrite policy

By default, pipeline steps should not silently overwrite existing files.

Different steps can use different existing-output policies:

```text
mri_conversion:
  skip / overwrite

recon:
  skip / overwrite

watershed:
  skip / overwrite

dense_scalp:
  skip / overwrite

bem:
  skip / overwrite

source_space:
  skip / overwrite

source_distances:
  skip / overwrite

volume_source_space:
  skip / overwrite

morph_labels:
  skip / overwrite

coregistration:
  skip / overwrite

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
OVERWRITE_STEPS = ["mri_conversion"]
OVERWRITE_STEPS = ["recon"]
OVERWRITE_STEPS = ["watershed", "bem"]
OVERWRITE_STEPS = ["coregistration"]
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
mri_conversion  -> skip existing converted MRI files
recon           -> skip existing FreeSurfer subjects
watershed       -> skip existing watershed/BEM surfaces
dense_scalp     -> skip existing dense scalp surfaces
bem             -> skip existing BEM model/solution
source_space    -> skip existing source spaces
source_distances-> skip existing source spaces with distances
volume_source_space -> skip existing volume source spaces
morph_labels    -> skip existing morphed labels/parcellations
coregistration  -> skip existing trans.fif files
convert_to_bids -> skip existing raw BIDS files
events          -> skip existing events.tsv files
analysis_events -> skip existing derivative analysis-event files
bad_channels    -> load existing bad-channel decisions
annotations     -> load existing bad-segment annotations
filtering       -> skip existing filtered derivatives
ica             -> skip existing ICA files
ica_decision    -> load existing ICA decisions
cleaned_raw     -> skip existing cleaned raw derivatives
epochs          -> skip existing epochs
evokeds         -> skip existing evoked files
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
  --session 20260523 \
  --task rest \
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
  --subject 0001 \
  --task rest
```

Show channel information:

```bash
meegpipe channels-info \
  --config configs/local.yaml \
  --subject 0001 \
  --task rest
```

Extract events and show event information:

```bash
meegpipe events-info \
  --config configs/local.yaml \
  --subject 0001 \
  --task rest
```

Write BIDS-compatible trigger-derived `events.tsv` files:

```bash
meegpipe write-events \
  --config configs/local.yaml \
  --subject 0001 \
  --task rest
```

The CLI is useful for quick checks and later batch/HPC workflows. Interactive QC,
MRI conversion, FreeSurfer reconstruction, and MNE coregistration are currently
better handled in notebooks.

## Recommended first data import step

Before converting to BIDS, place the original files under the configured
`sourcedata_root`.

For one participant with acquisition-date source folders and two tasks:

```bash
cd ~/MEEG/my-meeg-project

mkdir -p sourcedata/sub-0001/ses-20260523/meg/task-rest
mkdir -p sourcedata/sub-0001/ses-20260523/meg/task-auditory
```

Copy the original FIF files into the corresponding `sourcedata/` task folders:

```text
sourcedata/sub-0001/ses-20260523/meg/task-rest/<original_rest_file>.fif
sourcedata/sub-0001/ses-20260523/meg/task-auditory/<original_auditory_file>.fif
```

For projects without source session folders, use:

```text
sourcedata/sub-0001/meg/task-rest/<original_rest_file>.fif
sourcedata/sub-0001/meg/task-auditory/<original_auditory_file>.fif
```

Place raw MRI exports separately, for example:

```text
sourcedata/mri_raw/sub-0001/T1/<many DICOM files>
sourcedata/mri_raw/sub-0001/T2/<many DICOM files>
```

Do not modify these source files.

If `sourcedata.sessions` is `include`, the corresponding raw BIDS files will be
generated under:

```text
sub-0001/ses-20260523/meg/
```

with filenames such as:

```text
sub-0001_ses-20260523_task-rest_meg.fif
sub-0001_ses-20260523_task-auditory_meg.fif
```

If `sourcedata.sessions` is `ignore`, the same source folders generate raw BIDS
files without a session level:

```text
sub-0001/meg/
```

with filenames such as:

```text
sub-0001_task-rest_meg.fif
sub-0001_task-auditory_meg.fif
```

## Checking expected BIDS paths

The CLI can construct expected BIDS paths.

With sessions:

```bash
cd ~/MEEG/my-meeg-project

meegpipe bids-path \
  --config configs/local.yaml \
  --subject 0001 \
  --session 20260523 \
  --task rest \
  --extension .fif
```

Expected output path:

```text
sub-0001/ses-20260523/meg/sub-0001_ses-20260523_task-rest_meg.fif
```

Without sessions:

```bash
meegpipe bids-path \
  --config configs/local.yaml \
  --subject 0001 \
  --task rest \
  --extension .fif
```

Expected output path:

```text
sub-0001/meg/sub-0001_task-rest_meg.fif
```

## Development status

Early development.

Currently implemented:

- Python package structure
- `meegpipe` command-line entry point
- project scaffold creation with `meegpipe init-project`
- project config loading
- configurable `sourcedata_root`
- configurable source-data session handling via `sourcedata.sessions`
- configurable MRI raw/input roots via `paths.mri_raw_root` and `paths.mri_root`
- configurable FreeSurfer paths via `freesurfer.home` and `freesurfer.subjects_dir`
- runtime and analysis defaults in `configs/local.yaml`
- basic BIDS dataset inspection
- participants.tsv inspection
- BIDSPath construction
- sourcedata discovery
- conversion from `sourcedata_root` to raw BIDS
- MRI conversion helpers for DICOM/NIfTI/MGZ preparation
- FreeSurfer recon-all helpers
- watershed BEM and dense scalp surface helpers
- BEM model and BEM solution helpers
- surface and volume source-space helpers
- label morphing helpers
- MNE coregistration helper/status utilities
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
- optional autoreject-based epoch cleaning with training subsets
- evoked-response utilities
- existing-output policies for anatomy preparation, conversion, events,
  analysis events, bad-channel QC, filtering, annotations, ICA, ICA decisions,
  cleaned raw derivatives, epochs, and evokeds

Not yet implemented:

- SSP / empty-room based cleaning
- forward solution workflow
- noise covariance workflow
- inverse operator workflow
- source estimates
- source morphing to fsaverage
- label time courses
- reports
- HPC/Slurm execution
- automated tests
