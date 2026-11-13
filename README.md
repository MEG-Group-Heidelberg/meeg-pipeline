# meeg-pipeline

A modular, BIDS-oriented M/EEG analysis pipeline built on top of
[MNE-Python](https://mne.tools/stable/index.html) and
[MNE-BIDS](https://mne.tools/mne-bids/stable/index.html).

The package contains reusable pipeline code and a versioned project template.
Concrete research projects should live outside this repository and use this
package as a library.

## Contents

- [What this repository is](#what-this-repository-is)
- [Installation](#installation)
- [Creating a project](#creating-a-project)
- [Project layout](#project-layout)
- [First data import](#first-data-import)
- [Running the workflow](#running-the-workflow)
- [Configuration basics](#configuration-basics)
- [Preprocessing, ICA, and epoching inputs](#preprocessing-ica-and-epoching-inputs)
- [FreeSurfer and MRI setup](#freesurfer-and-mri-setup)
- [Source modeling and connectivity](#source-modeling-and-connectivity)
- [Command-line tools](#command-line-tools)
- [Troubleshooting](#when-something-goes-wrong)
- [Template maintenance](#template-maintenance)
- [Development status](#development-status)

## What this repository is

`meeg-pipeline` is the reusable Python package. It provides:

- reusable M/EEG processing helpers under `src/meeg_pipeline/`
- the `meegpipe` command-line interface
- a bundled project template under `src/meeg_pipeline/templates/project/`
- notebook templates for the current workflow

A typical local workspace should look like this:

```text
~/MEEG/
  .venv/
  meeg-pipeline/       # this repository / library
  my-meeg-project/     # one concrete analysis project
```

The repository should not contain project-specific raw data, derivatives, or
one-off analysis notebooks.

## Design principles

- Keep reusable library code and project-specific analysis separate.
- Preserve original source exports unchanged in `sourcedata/`.
- Treat raw BIDS FIF files as immutable analysis inputs.
- Write processed M/EEG outputs to `derivatives/meeg-pipeline/`.
- Write FreeSurfer outputs to `derivatives/freesurfer/subjects/`.
- Do not overwrite existing outputs by default.
- Report missing inputs and skipped outputs as status values in batch workflows.
- Store manual QC decisions explicitly.
- Keep event handling table-based and metadata-friendly.
- Support notebook-friendly interactive work and CLI-friendly batch work.
- Prepare MEG, EEG, and combined MEG+EEG workflows through explicit config.

## Installation

The result is one folder `~/MEEG` that holds the Python environment, this
repository, and your projects (see
[What this repository is](#what-this-repository-is)).

### Step 1: Check Python and Git

The pipeline needs **Python 3.11 or newer** (3.12 or 3.13 recommended) and
[Git](https://git-scm.com/downloads). The most common installation failure is an
older Python, so check this first.

macOS / Linux:

```bash
python3 --version
```

Windows (PowerShell):

```powershell
py --version
```

If the version is 3.11 or newer, continue with step 2. If it is older (for
example the 3.9 that ships with macOS) or the command is not found, install a
current Python. Choose one way:

| System | Way | Command or link |
| --- | --- | --- |
| Windows | installer | [python.org/downloads](https://www.python.org/downloads/windows/); tick "Add python.exe to PATH" |
| Windows | winget | `winget install Python.Python.3.13` |
| macOS | installer | [python.org/downloads](https://www.python.org/downloads/macos/) |
| macOS | Homebrew ([brew.sh](https://brew.sh)) | `brew install python@3.13` |
| Linux | package manager | `sudo apt install python3 python3-venv python3-pip` (Ubuntu 24.04 or newer ships 3.12); for older releases use the [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa) |
| any | [uv](https://docs.astral.sh/uv/getting-started/installation/) | `uv python install 3.13` |
| any | [Miniforge (conda)](https://github.com/conda-forge/miniforge) | create an environment with `python=3.13` |

Open a **new terminal** afterwards and check again. Several Python versions can
live side by side. If `python3 --version` still shows the old one, call the new
one by its full name: `python3.13` on macOS/Linux, `py -3.13` on Windows. Use
that name in the `venv` line of step 2 instead of `python3` or `py`.

### Step 2: Install the pipeline

macOS / Linux (Terminal), one block, run in order:

```bash
mkdir -p ~/MEEG && cd ~/MEEG
git clone https://github.com/MEG-Group-Heidelberg/meeg-pipeline.git
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
cd meeg-pipeline
pip install -e ".[dev,qt]"
```

Windows (PowerShell), one block, run in order:

```powershell
mkdir ~\MEEG; cd ~\MEEG
git clone https://github.com/MEG-Group-Heidelberg/meeg-pipeline.git
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
cd meeg-pipeline
pip install -e ".[dev,qt]"
```

If PowerShell refuses to run `Activate.ps1`, allow local scripts once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Windows notes

The Python part of the pipeline (BIDS import, events, preprocessing, ICA,
epoching, evokeds, forward/inverse modeling, label time courses, connectivity)
uses portable paths and should run on Windows. It has not been tested there
yet, so report anything that fails.

FreeSurfer does not run natively on Windows. For the steps that need it
(`recon-all`, BEM from watershed, `mri_convert`), use one of:

1. **WSL2** (Ubuntu inside Windows): install FreeSurfer and the pipeline inside
   WSL2 and work from there. Keep the project on the Linux side (`~/MEEG`), not
   under `/mnt/c`, which is slow.
2. **Prepare the anatomy on a Mac or Linux machine** and copy
   `derivatives/freesurfer/subjects/` into the project on Windows.
3. **Skip FreeSurfer** with `anatomy.mode: "scaled_template"` or `"template"`.
   The scaling itself is pure Python.

Practical points on Windows:

- Write paths in `local.yaml` with forward slashes (`D:/data/my-project`) or in
  single quotes. A backslash inside double quotes is an escape character in
  YAML.
- The multi-line commands in this README end lines with `\`. In
  PowerShell, write them on one line (or end lines with a backtick).
- `freesurfer.home` has no useful default on Windows; leave it `null` unless you
  use option 1 or 2.
- Avoid very long project paths (Windows limits them to about 260 characters in
  many programs).

Check the installation (the environment must be active, the prompt starts with
`(.venv)`). The first command must show 3.11 or newer:

```bash
python --version
```

```bash
meegpipe --version
```

In every new terminal, activate the environment again
(`source ~/MEEG/.venv/bin/activate` on macOS/Linux, `~\MEEG\.venv\Scripts\Activate.ps1`
on Windows) before using `meegpipe`.

Optional extras. Each block is complete on its own (macOS/Linux; on Windows
use `cd ~\MEEG\meeg-pipeline` instead). Install only what you need:

Autoreject-based epoch cleaning:

```bash
cd ~/MEEG/meeg-pipeline && pip install -e ".[dev,qt,autoreject]"
```

Anatomy helpers that need VTK/PyVista/nibabel:

```bash
cd ~/MEEG/meeg-pipeline && pip install -e ".[dev,qt,anatomy]"
```

Both:

```bash
cd ~/MEEG/meeg-pipeline && pip install -e ".[dev,qt,autoreject,anatomy]"
```

The `qt` extra installs packages needed for interactive MNE browser windows,
including `mne-qt-browser`, `pyqt6`, `pyqtgraph`, and `pyvistaqt`.

## Creating a project

Create a new project with `meegpipe init-project`.

Default MEG project:

```bash
cd ~/MEEG
meegpipe init-project my-meeg-project
```

Equivalent explicit form:

```bash
meegpipe init-project my-meeg-project --modality meg
```

EEG-only project with individual MRI defaults:

```bash
meegpipe init-project my-eeg-project --modality eeg
```

EEG-only project without individual MRIs, using `fsaverage` and a standard
10-20 montage as template-based source-modeling defaults:

```bash
meegpipe init-project my-eeg-project \
  --modality eeg \
  --anatomy template \
  --montage standard_1020
```

Combined MEG+EEG project, for example EEG channels stored in MEG FIF files:

```bash
meegpipe init-project my-meeg-eeg-project --modality meeg
```

Supported modality values are:

```text
meg   -> BIDS datatype meg, analysis channels meg=true, eeg=false
         creates example sourcedata folders under meg/

eeg   -> BIDS datatype eeg, analysis channels meg=false, eeg=true
         creates example sourcedata folders under eeg/

meeg  -> BIDS datatype meg, analysis channels meg=true, eeg=true
         creates example sourcedata folders under both meg/ and eeg/
```

Supported anatomy defaults are:

```text
individual_mri -> subject-specific MRI workflow with MRI conversion, recon-all,
                  BEM/source-space setup, and recording coregistration

template        -> template anatomy (fsaverage) defaults for projects without individual MRI;
                  intended primarily for EEG projects with a standard montage
```

`--montage` records the intended EEG montage in `configs/local.yaml`, for
example `--montage standard_1020`. For template-based EEG projects, this also
sets `channels.montage.dig: false` because no individual digitization is
expected by default.

For combined MEG+EEG, the template uses `bids.datatype: "meg"` because the
conservative default assumes a MEG FIF file that also contains EEG channels.
Validate concrete datasets with MNE-BIDS and the BIDS validator before treating
them as final.

Create a project on another drive either by changing directory first:

```bash
cd /Volumes/YourDrive/MEEG
meegpipe init-project my-meeg-project --modality meg
```

or by passing `--base-dir`:

```bash
meegpipe init-project my-meeg-project \
  --base-dir /Volumes/YourDrive/MEEG \
  --modality meg
```

Preview without writing anything:

```bash
meegpipe init-project my-meeg-project --dry-run
```

Overwrite existing template files intentionally:

```bash
meegpipe init-project my-meeg-project --overwrite
```

Use `--overwrite` carefully in existing projects. It can replace local notebook
edits. A safe workflow is to run `--dry-run`, inspect the paths, commit or back
up project changes, and only then overwrite generated files.

After creation, enter the project:

```bash
cd ~/MEEG/my-meeg-project
```

Then open and edit:

```text
configs/local.yaml
```

At minimum, check paths, modality/channel settings, task names, event extraction
settings, and condition definitions.

## Project layout

`init-project` creates an analysis workspace, not a raw BIDS dataset alone. The
raw BIDS dataset lives inside `rawdata/`.

```text
my-meeg-project/
  README.md
  configs/
    local.yaml

  notebooks/
    00_project_summary.ipynb
    1A_anatomy/
    1B_preprocessing/
    2_sensor_analysis/
    3_source_modeling/
    4_connectivity/
    5_decoding/

  sourcedata/
    sub-0001/
      meg/                  # for --modality meg or --modality meeg
        task-example/
      eeg/                  # for --modality eeg or --modality meeg
        task-example/
      ses-20260523/
        meg/                # for --modality meg or --modality meeg
          task-example/
        eeg/                # for --modality eeg or --modality meeg
          task-example/
    emptyroom/              # created for MEG-only defaults
      ses-YYYYMMDD/
    mri_raw/
      sub-0001/
        T1/
        T2/
    mri/
      sub-0001/
        anat/

  rawdata/
    README
    dataset_description.json
    participants.tsv
    participants.json

  derivatives/
    meeg-pipeline/
    freesurfer/
      subjects/
```

The example folders under `sourcedata/` are empty starter folders. Their datatype
subfolders follow the selected `--modality`: MEG projects get `meg/`, EEG
projects get `eeg/`, and combined M/EEG projects get both. Replace or extend the
examples with real subject, session, task, run, empty-room, and MRI folders. The
original source filename can usually remain arbitrary; the pipeline infers
entities from the folder structure.

The raw BIDS metadata files belong in `rawdata/`, not in the outer project root:

```text
rawdata/dataset_description.json
rawdata/participants.tsv
rawdata/participants.json
rawdata/README
```

The outer `README.md`, `configs/`, `notebooks/`, `sourcedata/`, and
`derivatives/` folders belong to the analysis workspace.

## First data import

Place original MEG/EEG exports under `sourcedata/`. These files should remain
unchanged.

Without source session folders:

```text
sourcedata/sub-0001/meg/task-rest/<original_rest_file>.fif
sourcedata/sub-0001/meg/task-auditory/<original_auditory_file>.fif
```

With acquisition-date source folders:

```text
sourcedata/sub-0001/ses-20260523/meg/task-rest/<original_rest_file>.fif
sourcedata/sub-0001/ses-20260523/meg/task-auditory/<original_auditory_file>.fif
```

With runs:

```text
sourcedata/sub-0001/ses-20260523/meg/task-rest/run-01/<original_file>.fif
sourcedata/sub-0001/ses-20260523/meg/task-rest/run-02/<original_file>.fif
```

The source-data session handling is configured in `configs/local.yaml`:

```yaml
sourcedata:
  sessions: "ignore"  # "ignore" | "include" | "auto"
```

Use:

- `ignore` for one-session analyses where `ses-*` folders are only acquisition
  date folders in `sourcedata/`.
- `include` when `ses-*` folders should become BIDS session entities.
- `auto` only when you deliberately want subjects with multiple source sessions
  to become BIDS sessions automatically.

Empty-room source recordings are stored separately:

```text
sourcedata/emptyroom/ses-YYYYMMDD/<original_empty_room_file>.fif
```

MRI exports are also separate from MEG/EEG source FIF files:

```text
sourcedata/mri_raw/sub-0001/T1/<many DICOM files>
sourcedata/mri_raw/sub-0001/T2/<many DICOM files>
```

or, if another lab already prepared standardized anatomy inputs:

```text
sourcedata/mri/sub-0001/anat/T1.mgz
sourcedata/mri/sub-0001/anat/T2.mgz
```

Inspect source data and the current raw BIDS tree:

```bash
meegpipe config-info --config configs/local.yaml
meegpipe sourcedata-info --config configs/local.yaml
meegpipe bids-info --config configs/local.yaml
```

Convert source recordings to raw BIDS either through the first preprocessing
notebook or via CLI:

```bash
meegpipe convert-to-bids --config configs/local.yaml
```

## Running the workflow

The template is notebook-oriented. Use the notebooks as auditable workflow steps
and keep reusable processing logic in the library.

```text
notebooks/
  00_project_summary.ipynb

  1A_anatomy/
    01_convert_mri.ipynb
    02_recon.ipynb
    03_anatomy_setup.ipynb
    04_coregistration.ipynb

  1B_preprocessing/
    01_raw_bids_import.ipynb
    02_bad_channels_and_events.ipynb
    03_project_specific_events.ipynb
    03b_join_stimulus_log.ipynb
    04_preprocessing.ipynb
    05_artifact_annotation.ipynb
    06_ica_cleaning.ipynb
    07_epoching.ipynb

  2_sensor_analysis/
    01_evokeds.ipynb

  3_source_modeling/
    01_forward_solution.ipynb
    02_noise_covariance.ipynb
    03_inverse_operator.ipynb
    04_apply_inverse_evokeds.ipynb
    05_morph_evoked_source_estimates_to_fsaverage.ipynb
    06_extract_label_time_courses_evokeds.ipynb
    07_extract_label_time_courses_epochs.ipynb
    08_apply_inverse_raw_labels.ipynb

  4_connectivity/
    01_connectivity_inputs.ipynb
    02_source_label_spectral_connectivity.ipynb
    03_connectivity_qc_and_export.ipynb
    04_connectivity_plots.ipynb

  5_decoding/
    01_sensor_decoding.ipynb
    02_label_time_course_decoding.ipynb
```

`1A_anatomy` and `1B_preprocessing` can often be started independently.
Source modeling needs outputs from anatomy, preprocessing/epoching, evokeds, and
noise covariance. Connectivity uses epoch-level label time courses from source
modeling. The ICA-cleaning notebook can be skipped for projects that set
`cleaning.ica.enabled: false`; in that case epoching can use filtered raw
derivatives directly via `epochs.input: auto` or `epochs.input: filtered`.

`5_decoding/` is currently scaffold-only. Treat those notebooks as placeholders
until the decoding workflow is hardened.

### Step by step

Replace `configs/local.yaml` paths and IDs with your own. Run all commands from
the project folder.

| # | Goal | Notebook | Command | You set / check |
| --- | --- | --- | --- | --- |
| 1 | Create the project | - | `meegpipe init-project my-project` | modality, anatomy (`--anatomy template` if no MRIs) |
| 2 | Put the original files in place | - | - | `sourcedata/sub-XXXX/meg/task-NAME/*.fif`, empty-room files in `sourcedata/emptyroom/` |
| 3 | Fill in the config | - | `meegpipe config-info --config configs/local.yaml` | the [required fields](#required-config-fields) |
| 4 | Check what was found | `00_project_summary` | `meegpipe sourcedata-info --config configs/local.yaml` | every recording you expect is listed |
| 5 | Convert to BIDS | `1B_preprocessing/01_raw_bids_import` | `meegpipe convert-to-bids --config configs/local.yaml` | `rawdata/` now contains the recordings |
| 6 | Mark bad channels, write trigger events | `1B_preprocessing/02_bad_channels_and_events` | `meegpipe write-events --config configs/local.yaml --subject XXXX --task NAME` | trigger channels in `events.extraction`; event counts look right |
| 7 | Optional: project-specific events or stimulus log | `03_project_specific_events`, `03b_join_stimulus_log` | `meegpipe events-join-stimulus-log ...` | only if the trigger alone does not describe the trial |
| 8 | Filter, mark bad segments, clean with ICA | `04_preprocessing`, `05_artifact_annotation`, `06_ica_cleaning` | - | filter limits in `preprocessing.filtering`; ICA can be switched off with `cleaning.ica.enabled: false` |
| 9 | Anatomy | `1A_anatomy/01` to `04` | `meegpipe anatomy-info --config configs/local.yaml` | see [Using fsaverage without individual MRIs](#using-fsaverage-without-individual-mris) |
| 10 | Epoch | `1B_preprocessing/07_epoching` | - | `epochs.tmin`, `epochs.tmax`, `conditions.definitions` |
| 11 | Evoked responses | `2_sensor_analysis/01_evokeds` | - | condition definitions |
| 12 | Forward solution | `3_source_modeling/01_forward_solution` | `meegpipe source-forward ...` | transform and BEM exist (status table) |
| 13 | Noise covariance, inverse | `02_noise_covariance`, `03_inverse_operator` | `meegpipe source-noise-cov ...`, `meegpipe source-inverse ...` | `source.noise_cov.mode` |
| 14 | Source estimates and label time courses | `04` to `07` | `meegpipe source-apply-inverse ...`, `source-label-time-courses ...` | `source.labels.parcellation` |
| 15 | Continuous source time courses (e.g. reverse correlation) | `08_apply_inverse_raw_labels` | `meegpipe source-apply-inverse-raw ...` | `source.apply_inverse.raw` |

Run notebook `00_project_summary` at any time. It is read-only and shows which
steps are finished for which recording.

### Interactive plotting setup

In Jupyter or VS Code, select the Python kernel from the environment where the
package was installed, for example:

```text
~/MEEG/.venv/bin/python
```

Before interactive MNE plots, run:

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

Interactive windows include:

```python
raw.plot(block=True)
ica.plot_sources(raw_for_ica, block=True)
mne.gui.coregistration(...)
```

If plots do not open externally, restart the notebook kernel and run the Qt setup
cell before any plotting command.

## Configuration basics

The project config lives at:

```text
configs/local.yaml
```

Important path defaults:

```yaml
paths:
  bids_root: "./rawdata"
  sourcedata_root: "./sourcedata"
  derivatives_root: "./derivatives/meeg-pipeline"
  mri_raw_root: "./sourcedata/mri_raw"
  mri_root: "./sourcedata/mri"
```

Relative paths are resolved relative to the project root.

### Required config fields

`meegpipe init-project` writes a working `configs/local.yaml`. These are the
values you normally have to touch; everything else has a sensible default.

| Field | Meaning |
| --- | --- |
| `freesurfer.home` | FreeSurfer installation, only for anatomy from MRI |
| `bids.datatype` | `meg` or `eeg` |
| `events.extraction.stim_channels` | trigger channels of your system |
| `events.extraction.min_gap_s` | drop triggers closer than this (seconds); 0 keeps all |
| `preprocessing.filtering` | notch frequencies and band limits |
| `epochs.tmin`, `epochs.tmax` | epoch window in seconds |
| `conditions.definitions` | names and rules of your conditions |
| `anatomy.mode`, `anatomy.subjects` | where each subject's anatomy comes from |
| `source.noise_cov.mode` | `erm` (empty room) for MEG; `baseline` for EEG |

All time values in the config end in `_s` and are in seconds. MNE-style
`tmin`, `tmax` and `baseline` keep their names. If you mistype a key or use an
old one, `meegpipe` prints a warning such as
`local.yaml contains keys the pipeline does not use (renamed or misspelled?):
events.extraction.min_gap`; fix the key, because the setting is otherwise
ignored.

### Modality and channel defaults

`bids.datatype` controls the raw BIDS datatype directory and filename suffix.
`channels.analysis` controls which channel types are selected in analysis steps.

MEG-only:

```yaml
bids:
  datatype: "meg"
channels:
  analysis:
    meg: true
    eeg: false
```

EEG-only:

```yaml
bids:
  datatype: "eeg"
channels:
  analysis:
    meg: false
    eeg: true
```

Combined MEG+EEG stored in MEG FIF files:

```yaml
bids:
  datatype: "meg"
channels:
  analysis:
    meg: true
    eeg: true
```

For EEG and MEG+EEG source modeling, use a three-layer BEM and a covariance
strategy that includes EEG channels. Do not use MEG empty-room covariance as a
silent default for EEG channels.

### Conditions

Reusable condition definitions live in the config:

```yaml
conditions:
  definitions:
    condition_a: "trial_type == 'condition_a'"
    event_1: [1]
```

These names can be reused by evokeds, source modeling, connectivity, and later
decoding workflows.

### Preprocessing, ICA, and epoching inputs

The preprocessing workflow can run either with an ICA-cleaning step or directly
from filtered raw derivatives. This is controlled in the project config.

By default, new projects use ICA-cleaned data for epoching:

```yaml
cleaning:
  ica:
    enabled: true

epochs:
  input: "auto"  # "auto" | "cleaned" | "filtered"
```

With `epochs.input: "auto"`, the epoching input is resolved from the ICA
setting:

```text
cleaning.ica.enabled: true   -> use desc-cleaned_<datatype>.fif
cleaning.ica.enabled: false  -> use desc-filtered_<datatype>.fif
```

For test runs or projects that intentionally skip ICA, either disable ICA and
keep `epochs.input: "auto"`:

```yaml
cleaning:
  ica:
    enabled: false

epochs:
  input: "auto"
```

or override the epoching input explicitly:

```yaml
epochs:
  input: "filtered"
```

Use `epochs.input: "cleaned"` to require ICA-cleaned raw derivatives even when
`cleaning.ica.enabled` is false. Epoch outputs include the resolved input stage
in their descriptor, for example `desc-cleaned_epo.fif` or
`desc-filtered_epo.fif`, so downstream analyses can distinguish whether epochs
were created from ICA-cleaned or only filtered data.

Autoreject can use a longer QC window than the final saved epochs:

```yaml
epochs:
  input: "auto"
  tmin: -0.25
  tmax: 0.75
  baseline: null
  bad_interpolation: epochs

autoreject:
  enabled: true
  use: Interpolation
  subset: 4
  tmin: -1.0
  tmax: 1.0
  crop_to_epochs: true
```

Here, AutoReject is fit/applied on `-1.0..1.0 s` epochs, and the cleaned epochs
are cropped to the saved `epochs.tmin..epochs.tmax` window before writing.
`autoreject.subset` is a pipeline convenience setting for fitting AutoReject on
a subset of epochs; in the current workflow, an integer value means every n-th
epoch is used for the AutoReject fit. Set it to `null` to fit on all epochs.

### Existing-output policy

Notebooks should not silently overwrite existing files. They use an
`OVERWRITE_STEPS` variable, usually with this default:

```python
OVERWRITE_STEPS = []
```

To recompute a specific step, either delete the corresponding output or add the
step name explicitly, for example:

```python
OVERWRITE_STEPS = ["filtering"]
OVERWRITE_STEPS = ["ica", "ica_decision", "cleaned_raw"]
OVERWRITE_STEPS = "all"
```

Common step names include:

```text
mri_conversion, recon, watershed, dense_scalp, bem, source_space,
source_distances, volume_source_space, morph_labels, coregistration,
freesurfer_provenance, convert_to_bids, empty_room_to_bids, events,
analysis_events, bad_channels, annotations, filtering, ica, ica_decision,
cleaned_raw, epochs, evokeds, forward, noise_covariance, inverse_operator,
source_estimates, source_morph, label_time_courses_evokeds,
label_time_courses_epochs, connectivity
```

## Using fsaverage without individual MRIs

The default template still assumes subject-specific MRI anatomy for source
modeling. For projects without individual MRIs, `init-project` can record a
template-based anatomy strategy instead:

```bash
meegpipe init-project my-eeg-project \
  --modality eeg \
  --anatomy template \
  --montage standard_1020
```

This writes the intended strategy into `configs/local.yaml`:

```yaml
anatomy:
  mode: "template"
channels:
  montage:
    kind: "standard_1020"
    dig: false
```

Conceptually, this changes the anatomy/source-modeling assumptions:

```text
with individual MRI:
  subject T1 -> recon-all -> subject BEM/source space -> recording coregistration

with fsaverage/template anatomy:
  fsaverage anatomy -> template source space and BEM -> montage/template-based transform
```

For `anatomy.mode: "template"`, the MRI-preparation notebooks are not all
required:

```text
1A_anatomy/01_convert_mri.ipynb      not required
1A_anatomy/02_recon.ipynb            not required
1A_anatomy/03_anatomy_setup.ipynb    still relevant: ensure fsaverage geometry
1A_anatomy/04_coregistration.ipynb   different strategy: standard montage /
                                     template-based alignment, not individual
                                     MEG-style coregistration
```

This is most plausible for pure EEG projects with a standard or approximately
equidistant cap. It is much less appropriate as a silent default for MEG without
individual MRI, where sensor-head geometry and head-position information are
more critical. Source-level results based on `fsaverage` should be reported as
template-based and less anatomically precise than individual MRI-based source
localization.

The anatomy can also be chosen per subject. `anatomy.mode` is the project default;
`anatomy.subjects` overrides it for single subjects, for example a MEG subject
without MRI:

```yaml
anatomy:
  mode: "individual_mri"
  subjects:
    "5055":
      mode: "scaled_template"   # fsaverage scaled to the head digitisation
```

`scaled_template` scales fsaverage to the digitised head points of the recording
(`meegpipe anatomy-scaled-template`), writes the result as a normal FreeSurfer
subject and records scaling factors and fit quality in
`sub-*/meeg-pipeline-anatomy.json`. `meegpipe anatomy-info` shows the mode and
status of every subject. The forward, inverse and label steps then run without a
special case.

The init/config support is intentionally separate from the full source-modeling
implementation. Forward-solution notebooks and downstream source steps must still
check `anatomy.mode` and handle fsaverage/template geometry explicitly before a
project treats fsaverage source estimates as fully reviewed pipeline outputs.

## FreeSurfer and MRI setup

You can initialize a project before FreeSurfer is installed. FreeSurfer is only
needed once you run the anatomy/source-modeling workflow.

The Python package does not install large external neuroimaging command-line
tools automatically. Anatomy preparation requires FreeSurfer. DICOM conversion
requires `dcm2niix` only when raw MRI folders need conversion.

Recommended macOS layout for FreeSurfer 8.2.0:

```text
/Applications/freesurfer/8.2.0
```

Store the license outside the application directory:

```bash
mkdir -p ~/.freesurfer
cp ~/Downloads/license.txt ~/.freesurfer/license.txt
```

Project config:

```yaml
freesurfer:
  home: "/Applications/freesurfer/8.2.0"
  subjects_dir: "./derivatives/freesurfer/subjects"
```

`freesurfer.home` is the software installation. `freesurfer.subjects_dir` is the
project-specific FreeSurfer output directory. Do not write project outputs to
`/Applications/freesurfer/.../subjects`.

For manual terminal use, set up the shell environment:

```bash
export FREESURFER_HOME=/Applications/freesurfer/8.2.0
export FS_LICENSE=$HOME/.freesurfer/license.txt
source "$FREESURFER_HOME/SetUpFreeSurfer.sh"

which recon-all
which mri_convert
which freeview
recon-all --version
mri_convert --version
```

To make this persistent on macOS/zsh:

```bash
cat >> ~/.zshrc <<'SHELL_EOF'
export FREESURFER_HOME=/Applications/freesurfer/8.2.0
export FS_LICENSE=$HOME/.freesurfer/license.txt
source "$FREESURFER_HOME/SetUpFreeSurfer.sh"
SHELL_EOF
```

Then restart your terminal, VS Code, and Jupyter kernels.

Install `dcm2niix` only if `1A_anatomy/01_convert_mri.ipynb` should convert raw
DICOM folders:

```bash
brew install dcm2niix
```

On Linux, use the package manager (e.g. `sudo apt install dcm2niix`).

Optional faster compression:

```bash
brew install pigz
```

Inside a notebook, check the environment:

```python
import os
import shutil

print(os.environ.get("FREESURFER_HOME"))
print(os.environ.get("FS_LICENSE"))
print(shutil.which("recon-all"))
print(shutil.which("mri_convert"))
print(shutil.which("dcm2niix"))
```

## Source modeling and connectivity

Source-modeling outputs are written under:

```text
derivatives/meeg-pipeline/sub-0001/meg/
  forward/
  cov/
  inverse/
  source_estimates/
  source_estimates_fsaverage/
  label_time_course/
  label_time_course_epochs/
```

MEG-only defaults:

```yaml
anatomy:
  bem:
    conductivity: [0.3]
source:
  noise_cov:
    mode: "erm"
```

EEG-only and MEG+EEG projects should use an EEG-capable BEM and a joint
covariance strategy, for example:

```yaml
anatomy:
  bem:
    conductivity: [0.3, 0.006, 0.3]
source:
  noise_cov:
    mode: "baseline"
```

Empty-room covariance is MEG-specific. For EEG-only it should not be used. For
MEG+EEG, avoid silently combining MEG empty-room covariance with EEG channels;
use baseline covariance unless a project-specific covariance strategy is made
explicit.

Connectivity uses epoch-wise label time courses from:

```text
derivatives/meeg-pipeline/.../label_time_course_epochs/
```

The connectivity config controls methods, bands, windows, conditions, and label
selection:

```yaml
connectivity:
  methods:
    - "imcoh"
    - "wpli"
  windows:
    example_window:
      tmin: 0.0
      tmax: 0.5
  conditions: "all"
```

## Command-line tools

Show the installed version:

```bash
meegpipe --version
```

Create projects (each block is one alternative; run only one):

Default MEG project:

```bash
meegpipe init-project my-meeg-project
```

EEG-only project:

```bash
meegpipe init-project my-eeg-project --modality eeg
```

EEG-only project without individual MRIs, using the template anatomy:

```bash
meegpipe init-project my-eeg-project --modality eeg --anatomy template --montage standard_1020
```

Combined MEG+EEG project:

```bash
meegpipe init-project my-meeg-eeg-project --modality meeg
```

Create the project in another folder:

```bash
meegpipe init-project my-meeg-project --base-dir /Volumes/YourDrive/MEEG
```

Preview without writing anything:

```bash
meegpipe init-project my-meeg-project --dry-run
```

Overwrite an existing scaffold:

```bash
meegpipe init-project my-meeg-project --overwrite
```

Inspect config, source data, and BIDS data:

```bash
meegpipe config-info --config configs/local.yaml
meegpipe sourcedata-info --config configs/local.yaml
meegpipe bids-info --config configs/local.yaml
```

Construct a BIDS path:

```bash
meegpipe bids-path \
  --config configs/local.yaml \
  --subject 0001 \
  --session 20260523 \
  --task rest \
  --extension .fif
```

Convert source recordings to raw BIDS:

```bash
meegpipe convert-to-bids --config configs/local.yaml
```

Inspect one recording:

```bash
meegpipe raw-info --config configs/local.yaml --subject 0001 --task rest
meegpipe channels-info --config configs/local.yaml --subject 0001 --task rest
meegpipe events-info --config configs/local.yaml --subject 0001 --task rest
```

Write trigger-derived BIDS events:

```bash
meegpipe write-events --config configs/local.yaml --subject 0001 --task rest
```

Join trigger events with a stimulus log (see `events.stimulus_log`):

```bash
meegpipe events-join-stimulus-log --config configs/local.yaml --subject 0001 --task rest
```

Show the anatomy mode and status per subject, and scale the template to the
digitised head of a subject without MRI:

```bash
meegpipe anatomy-info --config configs/local.yaml
meegpipe anatomy-scaled-template --config configs/local.yaml --subject 0002
```

List recordings and run source-modeling steps for one recording
(`--overwrite` replaces existing outputs, `--verbose` shows MNE output):

```bash
meegpipe list-recordings --config configs/local.yaml
meegpipe source-forward --config configs/local.yaml --subject 0001 --task rest
meegpipe source-noise-cov --config configs/local.yaml --subject 0001 --task rest
meegpipe source-inverse --config configs/local.yaml --subject 0001 --task rest
meegpipe source-apply-inverse --config configs/local.yaml --subject 0001 --task rest
meegpipe source-apply-inverse-raw --config configs/local.yaml --subject 0001 --task rest
meegpipe source-label-time-courses --config configs/local.yaml --subject 0001 --task rest
meegpipe source-label-time-courses-epochs --config configs/local.yaml --subject 0001 --task rest
```

### Which steps have a command

| Area | Command line | Notebook only |
| --- | --- | --- |
| Inspection | `config-info`, `sourcedata-info`, `bids-info`, `list-recordings`, `raw-info`, `channels-info`, `events-info` | summary dashboard |
| Import and events | `convert-to-bids`, `write-events`, `events-join-stimulus-log` | bad channels, project-specific events |
| Anatomy | `anatomy-info`, `anatomy-scaled-template` | MRI conversion, `recon-all`, BEM, source space, coregistration |
| Preprocessing | - | filtering, artifact annotation, ICA, epoching, evokeds |
| Source modeling | `source-forward`, `source-noise-cov`, `source-inverse`, `source-apply-inverse`, `source-apply-inverse-raw`, `source-label-time-courses`, `source-label-time-courses-epochs` | morphing to fsaverage |
| Connectivity, decoding | - | all notebooks (decoding is a placeholder) |

The interactive steps (bad channels, artifact annotation, ICA, coregistration)
need a person looking at the data and stay in notebooks on purpose.

## When something goes wrong

| Symptom | Likely cause and fix |
| --- | --- |
| `ERROR: Package 'meeg-pipeline' requires a different Python: 3.9.6 not in '>=3.11'` during `pip install` | the environment was built with an old Python. Install Python 3.11 or newer ([Step 1](#step-1-check-python-and-git)), delete the folder `~/MEEG/.venv`, and recreate it with the versioned command (`python3.13 -m venv .venv`, Windows `py -3.13 -m venv .venv`) |
| `python --version` inside the environment is still old | the environment keeps the Python it was created with, also after you install a newer one; delete `.venv` and create it again |
| `python: command not found` (macOS/Linux) | use `python3`; inside an active environment `python` works |
| Windows opens the Microsoft Store when you type `python` | turn off the "App execution aliases" for python.exe in Windows Settings, or use `py` |
| Linux: `ensurepip is not available` or `No module named venv` | `sudo apt install python3-venv` (for a specific version, e.g. `python3.13-venv`) |
| `python3.13: command not found` right after installing | open a new terminal; with Homebrew run `brew link python@3.13` |
| `meegpipe: command not found` (Windows: `not recognized`) | the environment is not active; activate it as described under [Installation](#installation) |
| warning `contains keys the pipeline does not use` | the listed key is misspelled or was renamed; compare with the config template |
| a recording is missing from `sourcedata-info` | wrong folder layout; compare with [First data import](#first-data-import) |
| no or too many events | check `events.extraction.stim_channels` and `min_gap_s`; inspect with `meegpipe events-info` |
| step is skipped with status `exists` | by design; rerun with `OVERWRITE_STEPS` or `--overwrite` |
| `scale_mri` or FreeSurfer fails on files like `._xyz` | macOS metadata files on external drives; delete them on the Mac: `find <project> -name '._*' -delete` |
| interactive plot does not open | restart the kernel and run the Qt setup cell first ([Interactive plotting setup](#interactive-plotting-setup)) |
| source step reports a missing input | the previous step has not run for this recording; the status table names it |

## Template maintenance

`meegpipe init-project` copies the bundled template from:

```text
src/meeg_pipeline/templates/project/
```

The template is a maintained starting point, not a frozen example. Recommended
workflow:

```text
real project notebooks, e.g. tonalkey/notebooks/
  -> active project-specific workflow and experiments

meeg-pipeline template notebooks
  -> reviewed, generic starting point for new projects
```

When a change proves generally useful, port it into the template and remove
project-specific assumptions such as local paths, subject IDs, task names,
condition names, or exploratory plot choices.

Template directories that should exist in newly initialized projects are kept in
the library with internal `_template_keep` files. `init-project` creates the
directories but deliberately skips these internal files, so new projects do not
get placeholder README files in every example folder.

## Development status

Current stable internal milestone:

```text
v0.1.0  Initial project template release
v0.1.1  Improved project init templates and modality defaults
```

Implemented:

- Python package structure and `meegpipe` CLI
- `meegpipe init-project` with bundled templates
- `--dry-run`, `--overwrite`, modality-aware defaults, and anatomy init defaults
- configurable project paths and raw BIDS root under `rawdata/`
- source-data discovery and conversion to raw BIDS
- empty-room discovery/import and matching for MEG covariance
- M/EEG channel-analysis configuration
- MRI conversion helpers and FreeSurfer workflow helpers
- BEM/source-space/coregistration helpers
- bad-channel QC, annotations, filtering, optional ICA, configurable epoching
  input stages, split AutoReject/saved epoch windows, and evokeds
- source-modeling workflow through label time courses
- label-level spectral connectivity workflow
- notebook templates for project summary, anatomy, preprocessing, sensor
  analysis, source modeling, and connectivity

Important TODOs:

- reviewed decoding notebook templates beyond scaffold placeholders
- stronger automated tests for newer source/connectivity helpers
- project reports and provenance summaries
- robust group-level statistics and multiple-comparison correction helpers
- directed connectivity workflows such as PSI
- explicit ERM-specific QC derivatives
- end-to-end CLI commands for all notebook steps
- hardened Slurm/HPC workflows
- continuous integration across supported Python/MNE versions
