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
      conditions.py
      connectivity.py
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
      source_modeling.py
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
including `mne-qt-browser`, `pyqt6`, `pyqtgraph`, and `pyvistaqt`.

### External anatomy tools

The Python package does not install large external neuroimaging command-line
tools automatically. Anatomy preparation requires FreeSurfer, and DICOM-based
MRI conversion additionally requires `dcm2niix`.

Install FreeSurfer separately from the official FreeSurfer download page. A
registration key is not needed to download the installer, but FreeSurfer commands
require a `license.txt` file before the software is fully operational. The
license is free and is requested through the official FreeSurfer registration
form.

For this project we recommend pinning the FreeSurfer installation to a versioned
directory. On macOS, for FreeSurfer 8.2.0 this is for example:

```text
/Applications/freesurfer/8.2.0
```

Store the license outside the application directory and point FreeSurfer to it
with `FS_LICENSE`. For example, after downloading the emailed `license.txt` file:

```bash
mkdir -p ~/.freesurfer
cp ~/Downloads/license.txt ~/.freesurfer/license.txt
```

In project configs, point `freesurfer.home` to the versioned FreeSurfer
installation and `freesurfer.subjects_dir` to the project-specific FreeSurfer
output directory:

```yaml
freesurfer:
  home: "/Applications/freesurfer/8.2.0"
  subjects_dir: "./derivatives/freesurfer/subjects"
```

`freesurfer.home` is the software installation. It is not where project anatomy
outputs should be written. Project-specific FreeSurfer outputs go into
`freesurfer.subjects_dir`. Do not use the default
`/Applications/freesurfer/8.2.0/subjects` directory for project outputs.

The pipeline sets `FREESURFER_HOME`, `FS_LICENSE`, and project-specific
`SUBJECTS_DIR` values for the commands it runs from the config and current
environment. For manual terminal use of FreeSurfer commands, and for checking
that the installation works, set up the shell environment explicitly:

```bash
export FREESURFER_HOME=/Applications/freesurfer/8.2.0
export FS_LICENSE=$HOME/.freesurfer/license.txt
source "$FREESURFER_HOME/SetUpFreeSurfer.sh"

echo "$FREESURFER_HOME"
echo "$FS_LICENSE"
test -f "$FS_LICENSE" && echo "FreeSurfer license found"
which recon-all
which mri_convert
which freeview
recon-all --version
mri_convert --version
freeview -h | head
```

Some FreeSurfer versions do not support `freeview --version`; use `which
freeview` or `freeview -h | head` as a basic check instead.

If `FREESURFER_HOME` is not set, FreeSurfer wrappers can fail even when the
binaries exist, for example with messages such as `FREESURFER_HOME: Undefined
variable` or by looking for `Freeview.app` in the wrong location. If `FS_LICENSE`
is not set or does not point to an existing file, FreeSurfer commands can fail
with messages such as `FreeSurfer license file ... not found`.

To make FreeSurfer available in new terminal sessions, add the setup to your
shell startup file, for example on macOS with zsh:

```bash
cat >> ~/.zshrc <<'EOF'
export FREESURFER_HOME=/Applications/freesurfer/8.2.0
export FS_LICENSE=$HOME/.freesurfer/license.txt
source "$FREESURFER_HOME/SetUpFreeSurfer.sh"
EOF
```

Then open a new terminal or run:

```bash
source ~/.zshrc
```

After changing shell setup, restart VS Code or Jupyter so notebook kernels inherit
the updated environment. Inside a notebook, check:

```python
import os
import shutil

print(os.environ.get("FREESURFER_HOME"))
print(os.environ.get("FS_LICENSE"))
print(shutil.which("recon-all"))
print(shutil.which("mri_convert"))
print(shutil.which("dcm2niix"))
```

If `1A_anatomy/01_convert_mri.ipynb` should convert raw DICOM folders into
NIfTI/MGZ inputs, install `dcm2niix`. On macOS with Homebrew:

```bash
brew install dcm2niix
```

Check `dcm2niix` from the same terminal or Jupyter environment that will run the
notebooks:

```bash
dcm2niix --version
```

`dcm2niix` may recommend installing `pigz` for faster compression. This is
optional; the conversion works without it. To install it with Homebrew:

```bash
brew install pigz
```

If you already place standardized MRI inputs such as `T1.mgz` or
`*T1w*.nii.gz` under `paths.mri_root` for all subjects, `dcm2niix` is not needed
for those subjects. It is only required for subjects where raw DICOM folders need
to be converted.

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

  rawdata/
    README
    dataset_description.json
    participants.tsv
    participants.json
    sub-0001/
      meg/
        sub-0001_task-example_meg.fif

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
      01_raw_bids_import.ipynb
      02_bad_channels_and_events.ipynb
      03_project_specific_events.ipynb
      04_preprocessing.ipynb
      05_artifact_annotation.ipynb
      06_ica_cleaning.ipynb
      07_epoching.ipynb

    2_sensor_analysis/
      01_evokeds.ipynb
      02_time_frequency.ipynb
      03_sensor_decoding.ipynb

    3_source_modeling/
      01_forward_solution.ipynb
      02_noise_covariance.ipynb
      03_inverse_operator.ipynb
      04_apply_inverse_evokeds.ipynb
      05_morph_evoked_source_estimates_to_fsaverage.ipynb
      06_extract_label_time_courses_evokeds.ipynb
      07_extract_label_time_courses_epochs.ipynb

    4_connectivity/
      01_connectivity_inputs.ipynb
      02_source_label_spectral_connectivity.ipynb
      03_connectivity_qc_and_export.ipynb
      04_connectivity_plots.ipynb

    5_decoding/
      01_sensor_decoding.ipynb
      02_label_time_course_decoding.ipynb

  sourcedata/
    sub-0001/
      meg/
        task-example/
          README.md
      ses-20260523/
        meg/
          task-example/
            README.md

    emptyroom/
      ses-YYYYMMDD/
        <original_empty_room_file>.fif

    mri_raw/
      sub-0001/
        T1/
          README.md
        T2/
          README.md

    mri/
      sub-0001/
        anat/
          README.md

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
  bids_root: "./rawdata"
  sourcedata_root: "./sourcedata"
  derivatives_root: "./derivatives/meeg-pipeline"
  mri_raw_root: "./sourcedata/mri_raw"
  mri_root: "./sourcedata/mri"

freesurfer:
  home: "/Applications/freesurfer/8.2.0"
  subjects_dir: "./derivatives/freesurfer/subjects"

sourcedata:
  sessions: "ignore"  # "ignore" | "include" | "auto"

empty_room:
  enabled: true
  subject: "emptyroom"
  task: "noise"
  sourcedata_root: "./sourcedata/emptyroom"
  sessions: "from_folders"
  session_pattern: "ses-*"
  file_patterns:
    - "*.fif"
    - "*.fif.gz"
  matching:
    strategy: "meas_date_nearest"  # "auto" | "meas_date_nearest" | "session_exact" | "session_date_nearest"
    max_time_diff_hours: 24
    allow_fallback: true
    fallback_strategy: "session_date_nearest"
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

- a raw BIDS dataset in `rawdata/`, configured as `paths.bids_root`
- project-specific configuration in `configs/`
- workflow notebooks in `notebooks/`
- original source files in `sourcedata/`
- BIDS-compatible raw MEG/EEG files under `rawdata/sub-*/...`
- M/EEG processed outputs in `derivatives/meeg-pipeline/`
- FreeSurfer anatomy outputs in `derivatives/freesurfer/subjects/`

### Project root versus raw BIDS root

The outer project folder is an analysis workspace. It contains project-specific
code, notebooks, configs, original source exports, and derivatives. The raw BIDS
dataset lives one level lower in `rawdata/`, and `paths.bids_root` should point
to that folder.

Use this convention consistently:

```text
my-meeg-project/
  README.md                         # project/workspace README, not a BIDS file
  configs/local.yaml
  notebooks/
  scripts/
  stimuli/
  sourcedata/                       # original acquisition exports, unchanged
  rawdata/                          # raw BIDS dataset root
    README                          # optional BIDS dataset README
    dataset_description.json        # BIDS dataset metadata
    participants.tsv                # BIDS participant table
    participants.json               # sidecar describing participants.tsv columns
    sub-0001/
    sub-emptyroom/
  derivatives/
    meeg-pipeline/
    freesurfer/
```

The files `dataset_description.json`, `participants.tsv`, `participants.json`,
and the BIDS `sub-*` folders belong in `rawdata/`, not next to `configs/` or
`notebooks/`. The project-level `README.md` belongs in the outer project folder.
If a BIDS dataset README is desired, place it as `rawdata/README` so it belongs
to the raw BIDS dataset.

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

  2_sensor_analysis/
    01_evokeds.ipynb
    02_time_frequency.ipynb
    03_sensor_decoding.ipynb

  3_source_modeling/
    01_forward_solution.ipynb
    02_noise_covariance.ipynb
    03_inverse_operator.ipynb
    04_apply_inverse_evokeds.ipynb
    05_morph_evoked_source_estimates_to_fsaverage.ipynb
    06_extract_label_time_courses_evokeds.ipynb
    07_extract_label_time_courses_epochs.ipynb

  4_connectivity/
    01_connectivity_inputs.ipynb
    02_source_label_spectral_connectivity.ipynb
    03_connectivity_qc_and_export.ipynb
    04_connectivity_plots.ipynb

  5_decoding/
    01_sensor_decoding.ipynb
    02_label_time_course_decoding.ipynb
```

`1A_anatomy` and `1B_meg_preprocessing` can often be run independently.
`1B_meg_preprocessing` ends with cleaned epochs. `2_sensor_analysis` derives
sensor-level products such as evoked responses. Anatomy, cleaned M/EEG
derivatives, sensor-level evokeds, and empty-room or baseline noise data come
together in `3_source_modeling`, where MEG/EEG recordings need anatomical source
spaces, BEM solutions, coregistration transforms, noise covariance matrices,
inverse operators, source estimates, fsaverage morphs, and label time courses.

Downstream workflows should treat source modeling as a feature-generation layer:
evoked source estimates support source visualization, while epoch-level label
time courses provide the main bridge to later label-level connectivity and
source/label-level decoding workflows.

## Empty-room measurements

For MEG source modeling, empty-room measurements are the preferred default input
for the noise covariance matrix. If empty-room data are not available, projects
may fall back to baseline covariance from cleaned epochs or, for technical tests
only, an ad-hoc covariance matrix. Missing empty-room inputs should be reported
as status values instead of aborting an entire batch workflow.

### Empty-room source data

Store original empty-room recordings under `sourcedata/emptyroom/`. The source
filename itself may be arbitrary; the session is inferred from the `ses-*`
folder. This mirrors the regular source-data principle that folder structure,
not original filenames, defines pipeline entities.

Recommended source layout:

```text
sourcedata/
  emptyroom/
    ses-YYYYMMDD/
      <original_empty_room_file>.fif
```

Example:

```text
sourcedata/
  emptyroom/
    ses-20250305/
      4859_erm-raw.fif
    ses-20250313/
      1409_erm-raw.fif
    ses-20250430/
      2827_erm-raw.fif
```

If multiple empty-room recordings exist for the same day, encode runs either as
run folders or in the filename:

```text
sourcedata/
  emptyroom/
    ses-20250313/
      run-01/
        <original_empty_room_file>.fif
      run-02/
        <original_empty_room_file>.fif
```

or:

```text
sourcedata/
  emptyroom/
    ses-20250313/
      run-01_emptyroom.fif
      run-02_emptyroom.fif
```

The raw BIDS/event notebook converts these source files to a dedicated BIDS
empty-room subject. Empty-room recordings do not require `events.tsv` files.

### Empty-room raw BIDS output

After import, empty-room recordings are stored in the configured raw BIDS tree
using a dedicated empty-room subject and acquisition-date session. With the
recommended `paths.bids_root: "./rawdata"` layout:

```text
rawdata/
  sub-emptyroom/
    ses-YYYYMMDD/
      meg/
        sub-emptyroom_ses-YYYYMMDD_task-noise_meg.fif
        sub-emptyroom_ses-YYYYMMDD_task-noise_channels.tsv
        sub-emptyroom_ses-YYYYMMDD_task-noise_meg.json
```

If multiple empty-room recordings exist for the same day, BIDS runs are added:

```text
rawdata/
  sub-emptyroom/
    ses-YYYYMMDD/
      meg/
        sub-emptyroom_ses-YYYYMMDD_task-noise_run-01_meg.fif
        sub-emptyroom_ses-YYYYMMDD_task-noise_run-02_meg.fif
```

### Empty-room config

Empty-room import and matching are configured separately from regular subject
source-data session handling:

```yaml
empty_room:
  enabled: true
  subject: "emptyroom"
  task: "noise"
  sourcedata_root: "./sourcedata/emptyroom"
  sessions: "from_folders"
  session_pattern: "ses-*"
  file_patterns:
    - "*.fif"
    - "*.fif.gz"
  matching:
    strategy: "meas_date_nearest"
    max_time_diff_hours: 24
    allow_fallback: true
    fallback_strategy: "session_date_nearest"
```

Supported matching strategies for source modeling are:

```text
meas_date_nearest:
  Match each recording to the empty-room recording with the nearest FIF
  raw.info["meas_date"]. This is the recommended default when measurement dates
  are preserved in the FIF files.

session_exact:
  Match by identical BIDS session labels. This is useful for projects where
  subject recordings and empty-room recordings deliberately share session names,
  such as ses-001 or ses-20250313.

session_date_nearest:
  Interpret session labels of the form ses-YYYYMMDD as dates and select the
  nearest empty-room session date.

auto:
  Try measurement-date matching first, then exact session matching, then
  date-like session matching.
```

For one-session projects, regular subject recordings may remain sessionless in
BIDS while empty-room recordings use date-like sessions. In that case,
`meas_date_nearest` can still match subject recordings to empty-room recordings
because the recording date is read from the FIF metadata rather than from the
BIDS session label.

The source configuration controls which covariance mode is used:

```yaml
source:
  noise_cov:
    mode: "erm"
```

The older flat alias `source.noise_cov_mode` is still accepted for backward
compatibility, but new configs should use `source.noise_cov.mode`.

Empty-room data should be processed with a strategy compatible with the analyzed
MEG recordings, including comparable channel selection, filtering, bad-channel
handling, and any project-specific preprocessing decisions that affect the data
rank. Source-space workflows then match the covariance channels to the recording
used for the forward and inverse operators.


### Empty-room preprocessing model

Empty-room recordings are imported into raw BIDS as `sub-emptyroom`, but they are
not processed through the regular subject preprocessing, ICA, epoching, or evoked
workflow. For ERM-based covariance, the selected raw BIDS empty-room FIF is
loaded during the noise-covariance step, MEG channels are picked, and the
project-level notch, high-pass, and low-pass filter settings from
`preprocessing.filtering` are applied in memory before `mne.compute_raw_covariance`
is called.

In other words, the regular experimental recordings follow this path:

```text
sourcedata -> raw BIDS -> preprocessing -> cleaning -> epochs -> evokeds/source
```

Empty-room recordings follow this shorter path:

```text
sourcedata/emptyroom -> raw BIDS sub-emptyroom -> in-memory filtering during noise covariance
```

The filtered empty-room raw object is not written as a derivative. If filter
settings change, the raw BIDS empty-room FIF does not need to be regenerated, but
all filter-dependent products derived from it should be recomputed, especially:

```text
cov/
inverse/
source_estimates/
source_estimates_fsaverage/
label_time_course/
label_time_course_epochs/
connectivity/
derivatives/meeg-pipeline/qc/connectivity/
```

Regular experimental derivatives such as `preprocessing/`, `cleaning/`,
`epochs/`, and `evokeds/` also need recomputation after a filter change. Geometry
products such as BEM solutions, source spaces, forward solutions, and
coregistration transforms usually do not depend on the filter settings and can be
kept unless the anatomy or MEG-to-MRI transform changed.

ERM-specific bad-channel QC is currently less explicit than regular recording
QC. The covariance step matches covariance channels to the analyzed recording
info, but a dedicated ERM-QC derivative is still a future improvement.

## Source modeling derivatives

Source-modeling derivatives are written under the regular pipeline derivatives
tree, using BIDS-like entities and dedicated derivative folders:

```text
derivatives/meeg-pipeline/sub-0001/ses-01/meg/
  forward/
    sub-0001_ses-01_task-example_run-01_space-ico5_desc-meg-fwd.fif
  cov/
    sub-0001_ses-01_task-example_run-01_desc-erm-cov.fif
  inverse/
    sub-0001_ses-01_task-example_run-01_space-ico5_desc-ermDspm-inv.fif
  source_estimates/
    sub-0001_ses-01_task-example_run-01_space-source_desc-standardDspm-stc.h5
  source_estimates_fsaverage/
    sub-0001_ses-01_task-example_run-01_space-fsaverage_desc-standardDspm-stc.h5
  label_time_course/
    sub-0001_ses-01_task-example_run-01_space-label_parc-aparcSub_desc-standardDspmmeanFlip-ltc.tsv
  label_time_course_epochs/
    sub-0001_ses-01_task-example_run-01_space-label_parc-aparcSub_desc-epochDspmmeanFlipdecim5-ltc.npy
    sub-0001_ses-01_task-example_run-01_space-label_parc-aparcSub_desc-epochDspmmeanFlipdecim5-ltc_labels.tsv
    sub-0001_ses-01_task-example_run-01_space-label_parc-aparcSub_desc-epochDspmmeanFlipdecim5-ltc_times.tsv
    sub-0001_ses-01_task-example_run-01_space-label_parc-aparcSub_desc-epochDspmmeanFlipdecim5-ltc_epochs.tsv
```

The default source-modeling prerequisites are:

```text
1A_anatomy:
  derivatives/freesurfer/subjects/sub-*/bem/sub-*-ico5-src.fif
  derivatives/freesurfer/subjects/sub-*/bem/sub-*-4-1layer-bem-sol.fif
  derivatives/freesurfer/subjects/sub-*/label/lh.aparc_sub.annot
  derivatives/freesurfer/subjects/sub-*/label/rh.aparc_sub.annot
  derivatives/meeg-pipeline/.../coregistration/*_trans.fif

1B_meg_preprocessing:
  derivatives/meeg-pipeline/.../cleaning/*desc-cleaned_meg.fif
  derivatives/meeg-pipeline/.../epochs/*desc-cleaned_epo.fif

2_sensor_analysis:
  derivatives/meeg-pipeline/.../evokeds/*desc-*_ave.fif
```

The recommended source configuration uses nested blocks. The older flat keys
such as `noise_cov_mode`, `inverse_method`, `parcellation`, `extract_mode`, and
`target_labels` are still accepted as compatibility aliases, but new projects
should prefer the nested structure:

```yaml
source:
  spacing: "ico5"

  inverse:
    method: "dSPM"
    snr: 3.0
    lambda2: null
    pick_ori: null

  labels:
    parcellation: "aparc_sub"
    extract_mode: "mean_flip"
    target_labels: null

  noise_cov:
    mode: "erm"       # "erm" | "baseline" | "ad_hoc"

  apply_inverse:
    apply_to: "evoked"
    pick_conditions: "all"
    save_stcs: true
    stc_format: "h5"

  morph:
    enabled: true
    subject_to: "fsaverage"
    spacing: null
    smooth: null
    method: null
    pick_conditions: "all"
    stc_format: "h5"

  label_time_courses_epochs:
    enabled: true
    decim: 5
    tmin: null
    tmax: null
    dtype: "float32"
    save_format: "npy"
```

`mean_flip` is the recommended default for label time courses extracted from
surface source estimates. It reduces cancellation that can occur when source
orientations differ within a label. `mean` may be useful for special cases, but
it is usually not the safest default for cortical-label time courses.

Existing source-modeling outputs are skipped by default unless the corresponding
step name is included in notebook-level `OVERWRITE_STEPS`. Missing inputs are
reported in status tables rather than interrupting the whole batch.

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

Empty-room source data are handled separately from regular subject source data.
They live under `sourcedata/emptyroom` and always use session folders to encode
acquisition dates or matching labels:

```text
sourcedata/
  emptyroom/
    ses-YYYYMMDD/
      <original_empty_room_file>.fif
```

These files are converted by `1B_meg_preprocessing/01_raw_bids_and_events.ipynb`
to `rawdata/sub-emptyroom/ses-YYYYMMDD/meg/` when `paths.bids_root: "./rawdata"` is used.
The original empty-room filename is arbitrary.

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

The `1A_anatomy/01_convert_mri.ipynb` notebook prepares a predictable project
layout. It converts raw MRI inputs when needed, but it also skips subjects that
already have a standardized anatomical input such as `T1.mgz` or a BIDS-like
`*T1w*.nii.gz` file under `paths.mri_root`:

```text
sourcedata/
  mri/
    sub-0001/
      anat/
        T1.mgz
        T2.mgz
        sub-0001_T1w.nii.gz
        sub-0001_T1w.json
        sub-0001_T2w.nii.gz
        sub-0001_T2w.json
```

`T1` is the required input for the standard `recon-all` workflow. `T2` is
optional and can be used as an additional input for pial-surface refinement when
configured. A subject with only T2 and no T1 is reported as an unsupported or
missing-input case in the standard workflow.

Projects can mix both input styles across subjects. For example, `sub-0001` may
already have `sourcedata/mri/sub-0001/anat/T1.mgz` supplied by another lab,
whereas `sub-0002` may only have raw DICOM folders under
`sourcedata/mri_raw/sub-0002/T1/`. The conversion notebook first checks for a
standardized input under `mri_root`; if it exists, conversion is skipped for that
subject/modality. Otherwise it attempts to create the standardized input from
`mri_raw_root`. The recon notebook only requires a usable T1 input under
`mri_root` and does not depend on how that file was created.

These MRI paths are configured with:

```yaml
paths:
  mri_raw_root: "./sourcedata/mri_raw"
  mri_root: "./sourcedata/mri"

anatomy:
  t1_patterns:
    - "{subject}/anat/T1.mgz"
    - "{subject}/anat/*T1w*.nii*"
  t2_patterns:
    - "{subject}/anat/T2.mgz"
    - "{subject}/anat/*T2w*.nii*"
  conversion:
    converter: "dcm2niix"
    t1_source_pattern: "{subject}/T1"
    t2_source_pattern: "{subject}/T2"
    make_mgz: true
```

### Raw BIDS data

The BIDS-formatted raw MEG/EEG data are stored outside `sourcedata/`, using BIDS
naming. The recommended project layout keeps the raw BIDS dataset in a dedicated
`rawdata/` folder:

```yaml
paths:
  bids_root: "./rawdata"
```

In this layout, the project root is a working directory and `rawdata/` is the BIDS
dataset root. BIDS tools should be pointed to `rawdata/`, not to the outer project
folder. This keeps `sourcedata/`, `derivatives/`, `configs/`, and `notebooks/`
as project-level siblings instead of mixing `sub-*` raw-data folders directly
with workflow files.

With BIDS sessions:

```text
rawdata/
  dataset_description.json
  participants.tsv
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
rawdata/
  dataset_description.json
  participants.tsv
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

Using `rawdata/` is BIDS-compatible as long as `rawdata/` itself is treated as the BIDS
dataset root and contains the required top-level BIDS files such as
`dataset_description.json` and `participants.tsv`. The outer project folder is
then a convenience workspace, not the BIDS dataset root.

### BIDS sidecars

Some BIDS sidecar files are part of the raw BIDS dataset and may be updated when
metadata decisions are made.

For example, manual bad-channel decisions should update the `channels.tsv` file
inside the configured raw BIDS root:

```text
rawdata/sub-0001/meg/sub-0001_task-rest_channels.tsv
```

or, with sessions:

```text
rawdata/sub-0001/ses-20260523/meg/sub-0001_ses-20260523_task-rest_channels.tsv
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
/Applications/freesurfer/8.2.0/
  # FreeSurfer software installation

my-meeg-project/
  derivatives/
    freesurfer/
      freesurfer_provenance.json
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
  home: "/Applications/freesurfer/8.2.0"
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
  t1_patterns:
    - "sub-{subject}/anat/T1.mgz"
    - "sub-{subject}/anat/*T1w*.nii*"
  t2_patterns:
    - "sub-{subject}/anat/T2.mgz"
    - "sub-{subject}/anat/*T2w*.nii*"
```

If your project uses bare subject labels such as `0001`, use:

```yaml
anatomy:
  t1_patterns:
    - "{subject}/anat/T1.mgz"
    - "{subject}/anat/*T1w*.nii*"
  t2_patterns:
    - "{subject}/anat/T2.mgz"
    - "{subject}/anat/*T2w*.nii*"
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

In the recommended layout, BIDS metadata files live at the root of the raw BIDS
dataset, i.e. under `rawdata/`. They do not live in the outer project folder.

The outer project folder has its own project README:

```text
my-meeg-project/README.md
```

This is for project notes, workflow instructions, local analysis documentation,
or collaborator-facing explanations. It is not part of the raw BIDS dataset.

The raw BIDS dataset has these metadata files:

```text
my-meeg-project/rawdata/README
my-meeg-project/rawdata/dataset_description.json
my-meeg-project/rawdata/participants.tsv
my-meeg-project/rawdata/participants.json
```

`rawdata/README` is optional but useful as the README for the raw BIDS dataset.
`rawdata/dataset_description.json` is the BIDS dataset description. Example:

```json
{
  "Name": "my-meeg-project",
  "BIDSVersion": "1.10.0",
  "DatasetType": "raw",
  "Authors": ["Your Name"]
}
```

`rawdata/participants.tsv` is the participant table. Example:

```text
participant_id
sub-0001
sub-0002
```

The participant IDs in `rawdata/participants.tsv` should match the
`rawdata/sub-*` folders.

`rawdata/participants.json` is the sidecar that documents the columns in
`participants.tsv`. It is the right place to describe fields such as `age`,
`sex`, `hand`, `height`, or `weight`, including units and allowed levels.

For example, do this:

```text
my-meeg-project/
  README.md
  rawdata/
    dataset_description.json
    participants.tsv
    participants.json
    sub-0001/
```

Do not do this:

```text
my-meeg-project/
  dataset_description.json
  participants.tsv
  participants.json
  sub-0001/
  configs/
  notebooks/
```

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
  bids_root: "./rawdata"
  sourcedata_root: "./sourcedata"
  derivatives_root: "./derivatives/meeg-pipeline"
  mri_raw_root: "./sourcedata/mri_raw"
  mri_root: "./sourcedata/mri"

freesurfer:
  home: "/Applications/freesurfer/8.2.0"
  subjects_dir: "./derivatives/freesurfer/subjects"

anatomy:
  coregistration:
    transform_scope: "recording"       # "recording" | "session" | "subject"
    allow_compatible_fallback: true
  t1_patterns:
    - "{subject}/anat/T1.mgz"
    - "{subject}/anat/*T1w*.nii*"
  t2_patterns:
    - "{subject}/anat/T2.mgz"
    - "{subject}/anat/*T2w*.nii*"
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

bids:
  datatype: "meg"
  task: null
  session: null
  run: null

empty_room:
  enabled: true
  subject: "emptyroom"
  task: "noise"
  sourcedata_root: "./sourcedata/emptyroom"
  sessions: "from_folders"
  session_pattern: "ses-*"
  file_patterns:
    - "*.fif"
    - "*.fif.gz"
  matching:
    strategy: "meas_date_nearest"
    max_time_diff_hours: 24
    allow_fallback: true
    fallback_strategy: "session_date_nearest"

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

runtime:
  n_jobs: 4
  thread_limits: true

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

conditions:
  definitions:
    first_deviant: "deviant == 1"
    condition_a: "trial_type == 'condition_a'"

source:
  spacing: "ico5"
  inverse:
    method: "dSPM"
    snr: 3.0
    lambda2: null
    pick_ori: null
  labels:
    parcellation: "aparc_sub"
    extract_mode: "mean_flip"
    target_labels: null
  noise_cov:
    mode: "erm"
  apply_inverse:
    apply_to: "evoked"
    pick_conditions: "all"
    save_stcs: true
    stc_format: "h5"
  morph:
    enabled: true
    subject_to: "fsaverage"
    spacing: null
    smooth: null
    method: null
    pick_conditions: "all"
    stc_format: "h5"
  label_time_courses_epochs:
    enabled: true
    decim: 5
    tmin: null
    tmax: null
    dtype: "float32"
    save_format: "npy"

connectivity:
  enabled: true
  input: "label_time_course_epochs"
  space: "label"
  parcellation: "aparc_sub"
  methods:
    - "imcoh"
    - "wpli"
  mode: "multitaper"
  windows:
    pre_window:
      tmin: -0.75
      tmax: 0.0
    post_window:
      tmin: 0.0
      tmax: 0.75
  bands:
    beta:
      fmin: 13.0
      fmax: 30.0
    low_gamma:
      fmin: 30.0
      fmax: 70.0
  faverage: true
  conditions:
    - "first_deviant"
  label_patterns:
    - "transversetemporal"
    - "superiortemporal"
    - "bankssts"
    - "middletemporal"
    - "inferiortemporal"
    - "supramarginal"
    - "insula"
  block_size: 1000
  n_jobs: 4
  save_format: "npz"
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
missing_t1_source
missing_optional_t2_source
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

This notebook prepares MRI inputs. It can be skipped or partially skipped for
subjects that already have standardized MRI inputs under `paths.mri_root`.

Typical raw input:

```text
sourcedata/mri_raw/sub-0001/T1/
sourcedata/mri_raw/sub-0001/T2/
```

Typical standardized input/output:

```text
sourcedata/mri/sub-0001/anat/T1.mgz
sourcedata/mri/sub-0001/anat/T2.mgz
sourcedata/mri/sub-0001/anat/sub-0001_T1w.nii.gz
sourcedata/mri/sub-0001/anat/sub-0001_T2w.nii.gz
```

The standardized files may be created by this notebook or placed there manually
when another lab has already prepared them.

The T2 input is optional. The standard pipeline requires T1 for `recon-all`.
If raw DICOM folders need to be converted, `dcm2niix` must be installed and
available on `PATH`. If `dcm2niix` is missing, the notebook reports
`missing_converter` for those subjects instead of treating this as a valid MRI
input state.

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

The notebook also writes project-level FreeSurfer software provenance to:

```text
derivatives/freesurfer/freesurfer_provenance.json
```

This JSON file records the configured `FREESURFER_HOME`, `SUBJECTS_DIR`, command
paths, `recon-all --version`, `freeview --version`, `mri_convert --version`, the
MNE version, Python version, and platform information. FreeSurfer additionally
writes detailed per-subject logs inside each subject's `scripts/` directory.

### `03_anatomy_setup.ipynb`

This notebook prepares geometry files required for source modeling:

- watershed BEM surfaces
- dense scalp surfaces for coregistration support
- BEM model and BEM solution
- surface source space
- optional source-space distances
- optional volume source space
- parcellation labels morphed from `fsaverage`


### Project-local `fsaverage`

Some anatomy steps fetch additional `fsaverage` parcellations, for example
`aparc_sub`, and write them into `fsaverage/label/`. For this reason, the
project `SUBJECTS_DIR` should contain a writable, project-local copy of
`fsaverage`, not only a symlink to the read-only FreeSurfer installation.

The pipeline checks this before fetching parcellations. If
`derivatives/freesurfer/subjects/fsaverage` is a symlink to something like
`/Applications/freesurfer/8.2.0/subjects/fsaverage`, it is replaced by a
project-local copy. This keeps `/Applications/freesurfer/...` unchanged and
allows MNE to write project-specific parcellation files.

Manual equivalent:

```bash
cd /path/to/my-meeg-project
rm derivatives/freesurfer/subjects/fsaverage
cp -a /Applications/freesurfer/8.2.0/subjects/fsaverage derivatives/freesurfer/subjects/
chown -R "$(id -un):$(id -gn)" derivatives/freesurfer/subjects/fsaverage
chmod -R u+rwX derivatives/freesurfer/subjects/fsaverage
```

Use `sudo chown` only if the copied files are not owned by the current user.

### `04_coregistration.ipynb`

This notebook opens the interactive MNE coregistration GUI and creates one
manual `*_trans.fif` transform per MEG/EEG recording. The transform links the
digitized head points, HPI coils, and sensor geometry from the raw BIDS
recording to the subject's FreeSurfer MRI anatomy.

Coregistration is recording-based, not only subject-based. The raw BIDS file is
passed to MNE as `inst`, so the matching digitization, head-shape, and HPI
information are loaded automatically for each selected recording. For this
reason, the notebook can run through pending recordings in a controlled batch
mode, while still opening only one GUI window at a time.

The GUI is opened with `block=True`. After the user closes the current GUI
window, the notebook automatically writes the current transform to the printed
`Transform target` path and then continues with the next pending recording. The
user does not need to choose the output path manually in the GUI.

Typical workflow:

```text
1. Keep MAX_COREGISTRATION_GUIS = 1 for the first test run.
2. Open the GUI for the first pending recording.
3. Perform the coregistration in the GUI.
4. Do not use the GUI save button.
5. Close the GUI window.
6. If the GUI asks whether to save before closing, dismiss or ignore this warning.
7. The notebook writes the transform automatically to the printed Transform target.
8. Check that trans_exists_after is True.
9. Set MAX_COREGISTRATION_GUIS = None to process all pending recordings.
```

The save warning from the GUI is expected in this workflow. MNE's GUI does not
know that the notebook will write the transform after the window is closed. The
notebook saves the transform explicitly with MNE after the GUI returns.

Transforms are stored as pipeline derivatives:

```text
derivatives/meeg-pipeline/sub-0001/meg/coregistration/
  sub-0001_task-rest_desc-coreg_trans.fif
```

With sessions and runs, the corresponding entities are included:

```text
derivatives/meeg-pipeline/sub-0001/ses-20260523/meg/coregistration/
  sub-0001_ses-20260523_task-rest_run-01_desc-coreg_trans.fif
```

FreeSurfer subjects should use a single `sub-...` prefix, for example
`sub-0001`, not `sub-sub-0001`. The printed `Transform target` path should also
contain only one `sub-...` prefix.

Recommended quality guidelines:

```text
Fiducial distances:
  Ideal: below 5 mm.
  Acceptable: up to 10 mm if the head-shape fit is good.
  If one fiducial is clearly higher than the others, adjust the fiducial point
  in the MRI or digitized head shape if possible.

HSP + HPI fit after ICP:
  Mean below 2 mm is very good.
  Example of an excellent fit: 1.4 ± 1.0 mm.

HSP-to-MRI surface distance:
  Mean below 2 mm is very good.
  Maximum values below about 10 mm are usually acceptable when they represent
  only a few outlier points.
  Outlier points can often be deleted in the GUI before saving the transform.
```

Common troubleshooting:

```text
No valid 3D backend:
  Install the qt extra and make sure pyvistaqt is available.

No standard head model found:
  Run the anatomy setup first and check that head-surface files exist under
  derivatives/freesurfer/subjects/sub-*/bem/.

GUI updates only after moving the camera:
  This is usually a Qt/PyVista redraw issue. The selected point is updated
  internally, but the 3D view may redraw only after a small camera movement.
```

By default, existing `trans.fif` files are skipped. Add `"coregistration"` to
`OVERWRITE_STEPS` if you intentionally want to rerun and overwrite existing
transforms.

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
rawdata/sub-0001/meg/sub-0001_task-rest_meg.fif
rawdata/sub-0001/meg/sub-0001_task-rest_channels.tsv

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
definitions. Conditions can be simple event labels, old-style event-code lists,
or pandas metadata queries.

Recommended workflow:

1. Load `desc-cleaned_epo.fif`.
2. Inspect `epochs.metadata`.
3. Define named condition definitions in `configs/local.yaml` when the same
   selections should be reused across evokeds, source modeling, connectivity, or
   decoding.
4. Average selected epochs per condition.
5. Save `desc-evoked_ave.fif`.

Example central condition definitions:

```yaml
conditions:
  definitions:
    first_deviant: "deviant == 1"
    key_change: "note_index == 0"
    condition_a: "trial_type == 'condition_a'"
```

Downstream notebooks can then refer to the named conditions:

```python
from meeg_pipeline.conditions import condition_definitions_from_config
from meeg_pipeline.evokeds import configured_conditions

condition_definitions = condition_definitions_from_config(config)
conditions = configured_conditions(config)
```

Projects that do not need derived metadata queries can still work directly with
trigger/event labels such as `trial_type == 'tone'`, `event_name == 'deviant'`,
or MNE event IDs. The central `conditions.definitions` block is optional, but it
is recommended when a condition is reused by multiple analysis stages.

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

  2_sensor_analysis/
    01_evokeds.ipynb
    02_time_frequency.ipynb
    03_sensor_decoding.ipynb

  3_source_modeling/
    01_forward_solution.ipynb
    02_noise_covariance.ipynb
    03_inverse_operator.ipynb
    04_apply_inverse_evokeds.ipynb
    05_morph_evoked_source_estimates_to_fsaverage.ipynb
    06_extract_label_time_courses_evokeds.ipynb
    07_extract_label_time_courses_epochs.ipynb

  4_connectivity/
    01_connectivity_inputs.ipynb
    02_source_label_spectral_connectivity.ipynb
    03_connectivity_qc_and_export.ipynb
    04_connectivity_plots.ipynb

  5_decoding/
    01_sensor_decoding.ipynb
    02_label_time_course_decoding.ipynb
```

Suggested roles:

```text
00_project_summary.ipynb
  Read-only dashboard.
  Shows what data exist, what has been computed, event status, bad-channel status,
  filtered-derivative status, bad-segment annotation status, ICA status, cleaned-
  raw status, epoch status, evoked status, and anatomy/source-preparation status.

1A_anatomy/01_convert_mri.ipynb
  Optional MRI input-preparation notebook.
  Converts raw MRI lab exports such as DICOM series into project-standard T1/T2
  NIfTI and optional MGZ files, while skipping subjects that already have
  standardized inputs such as T1.mgz under paths.mri_root.

1A_anatomy/02_recon.ipynb
  FreeSurfer reconstruction notebook.
  Runs T1-based recon-all from whichever standardized T1 input is available
  under paths.mri_root and optionally uses T2 for pial-surface refinement.

1A_anatomy/03_anatomy_setup.ipynb
  Anatomy setup notebook.
  Creates BEM surfaces, BEM model/solution, source spaces, optional source
  distances, optional volume source space, and morphed labels.

1A_anatomy/04_coregistration.ipynb
  Coregistration notebook.
  Opens the interactive MNE coregistration GUI and stores trans.fif derivatives.

1B_meg_preprocessing/01_raw_bids_and_events.ipynb
  Active raw-data, empty-room import, and bad-channel notebook.
  Discovers regular sourcedata, converts it to raw BIDS, imports empty-room
  recordings as `sub-emptyroom`, extracts trigger-derived events for regular
  task recordings, inspects channels, performs manual bad-channel QC, and
  updates channels.tsv.

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

2_sensor_analysis/01_evokeds.ipynb
  Evoked-response notebook.
  Uses conditions from `configs/local.yaml` when available and writes evoked
  response files.

3_source_modeling/01_forward_solution.ipynb
  Creates or checks MEG forward solutions from anatomy, source space,
  coregistration transform, and recording info.

3_source_modeling/02_noise_covariance.ipynb
  Computes noise covariance matrices, preferably from matched empty-room
  recordings. Empty-room data are filtered in memory using the project
  preprocessing filter settings.

3_source_modeling/03_inverse_operator.ipynb
  Creates inverse operators from forward solution, covariance, and recording
  info.

3_source_modeling/04_apply_inverse_evokeds.ipynb
  Applies inverse operators to evoked responses and writes native-space source
  estimates.

3_source_modeling/05_morph_evoked_source_estimates_to_fsaverage.ipynb
  Morphs evoked source estimates to `fsaverage` for group-level visualization or
  common-space summaries.

3_source_modeling/06_extract_label_time_courses_evokeds.ipynb
  Extracts label time courses from evoked source estimates.

3_source_modeling/07_extract_label_time_courses_epochs.ipynb
  Applies the inverse operator epoch-by-epoch and writes compact epoch-level
  label time courses. These files are the preferred input for label-level
  connectivity and source/label-level decoding.

4_connectivity/01_connectivity_inputs.ipynb
  Checks whether epoch-level label time courses, labels, metadata, and configured
  windows/conditions are available.

4_connectivity/02_source_label_spectral_connectivity.ipynb
  Computes spectral connectivity from epoch-level label time courses for the
  configured conditions, time windows, frequency bands, and methods.

4_connectivity/03_connectivity_qc_and_export.ipynb
  Summarizes connectivity outputs and writes QC tables.

4_connectivity/04_connectivity_plots.ipynb
  Creates project-specific exploratory plots and contrasts, for example
  `post_window - pre_window` within a configured condition.
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

freesurfer_provenance:
  skip / overwrite

convert_to_bids:
  skip / overwrite

empty_room_to_bids:
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

forward:
  skip / overwrite

noise_covariance:
  skip / overwrite

inverse_operator:
  skip / overwrite

source_estimates:
  skip / overwrite

source_morph:
  skip / overwrite

label_time_courses_evokeds:
  skip / overwrite

label_time_courses_epochs:
  skip / overwrite

connectivity:
  skip / overwrite
```

For notebooks, a central variable can be used:

```python
OVERWRITE_STEPS = []
OVERWRITE_STEPS = ["mri_conversion"]
OVERWRITE_STEPS = ["recon"]
OVERWRITE_STEPS = ["watershed", "bem"]
OVERWRITE_STEPS = ["coregistration"]
OVERWRITE_STEPS = ["freesurfer_provenance"]
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
OVERWRITE_STEPS = ["noise_covariance"]
OVERWRITE_STEPS = ["inverse_operator"]
OVERWRITE_STEPS = ["source_estimates"]
OVERWRITE_STEPS = ["source_morph"]
OVERWRITE_STEPS = ["label_time_courses_epochs"]
OVERWRITE_STEPS = ["connectivity"]
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
freesurfer_provenance -> skip existing software-provenance JSON
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
noise_covariance -> skip existing covariance files
inverse_operator -> skip existing inverse operators
source_estimates -> skip existing source estimates
source_morph     -> skip existing morphed source estimates
label_time_courses_evokeds -> skip existing evoked label time courses
label_time_courses_epochs  -> skip existing epoch label time courses
connectivity     -> skip existing connectivity outputs
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
generated under the configured raw BIDS root:

```text
rawdata/sub-0001/ses-20260523/meg/
```

with filenames such as:

```text
sub-0001_ses-20260523_task-rest_meg.fif
sub-0001_ses-20260523_task-auditory_meg.fif
```

If `sourcedata.sessions` is `ignore`, the same source folders generate raw BIDS
files without a session level under the configured raw BIDS root:

```text
rawdata/sub-0001/meg/
```

with filenames such as:

```text
sub-0001_task-rest_meg.fif
sub-0001_task-auditory_meg.fif
```

## Moving an existing root-level raw BIDS dataset into `rawdata/`

Older projects may have raw BIDS files directly in the project root, for example
`dataset_description.json`, `participants.tsv`, `sub-0001/`, and
`sub-emptyroom/`. To migrate such a project to the recommended layout, move only
the raw BIDS dataset files into `rawdata/` and then set `paths.bids_root: "./rawdata"`
in `configs/local.yaml`.

Example migration from the project root:

```bash
mkdir -p raw
mv dataset_description.json participants.tsv rawdata/
mv sub-* rawdata/
```

Do not move `sourcedata/`, `derivatives/`, `configs/`, or `notebooks/`. If the
raw BIDS files have already been moved, rerun:

```bash
meegpipe bids-info --config configs/local.yaml
```

The subject folders should then be discovered below `rawdata/`.

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
rawdata/sub-0001/ses-20260523/meg/sub-0001_ses-20260523_task-rest_meg.fif
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
rawdata/sub-0001/meg/sub-0001_task-rest_meg.fif
```

## Development status

Early but usable development.

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
- empty-room sourcedata discovery and conversion to `sub-emptyroom` raw BIDS
- empty-room matching for source-modeling covariance
- in-memory empty-room filtering for ERM covariance
- MRI conversion helpers for DICOM/NIfTI/MGZ preparation
- FreeSurfer recon-all helpers
- FreeSurfer software provenance documentation
- watershed BEM and dense scalp surface helpers
- BEM model and BEM solution helpers
- surface and volume source-space helpers
- label morphing helpers
- MNE coregistration helper/status utilities
- configurable subject/session/task/run transform scope for coregistration
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
- central reusable condition definitions via `conditions.definitions`
- forward-solution workflow
- ERM, baseline, and ad-hoc noise-covariance workflow
- inverse-operator workflow
- evoked source-estimate workflow
- morphing evoked source estimates to `fsaverage`
- evoked label-time-course extraction
- epoch-wise label-time-course extraction for connectivity/decoding
- label-level spectral connectivity from epoch-wise label time courses
- connectivity input overview, QC summaries, top-edge tables, and window contrasts
- basic Slurm/HPC helper scripts for future batch workflows

Important TODOs / not yet fully implemented:

- automated tests for the newer source-modeling, condition, and connectivity helpers
- project reports and HTML/PDF summaries
- robust group-level statistics for connectivity and source/label analyses
- permutation/cluster tests and multiple-comparison correction helpers
- directed connectivity workflows such as PSI
- richer time-frequency workflows outside connectivity
- decoding workflows beyond initial notebook scaffolding
- explicit ERM-specific QC derivatives and reporting
- explicit provenance JSON files for each major derivative step
- stronger validation of config migrations and backward-compatible aliases
- end-to-end CLI commands for all notebook steps
- hardened Slurm/HPC execution and job-dependency workflows
- continuous integration across supported Python/MNE versions

## Dense scalp surface dependency

For dense scalp surface creation, the anatomy extra installs nibabel, VTK, and
PyVista. MNE uses VTK/PyVista to decimate the dense head surface into medium and
sparse scalp surfaces. If `mne make_scalp_surfaces` fails with `No module named 'vtkmodules'`,
`No module named 'pyvista'`, or `This function requires the VTK package`, install
or update the anatomy extra:

```bash
pip install -e ".[dev,qt,autoreject,anatomy]"
python -c "import nibabel, vtkmodules, pyvista; print('anatomy dependencies available')"
```


## M/EEG channel and datatype configuration roadmap

The preprocessing workflow is being generalized from a MEG-specific workflow into a shared M/EEG workflow. For now, the existing `1B_meg_preprocessing/` directory remains in place to avoid disrupting current reruns. Conceptually, this workflow should be treated as the future shared M/EEG preprocessing workflow rather than as a reason to create a separate `1C_eeg_processing/` pipeline.

Two configuration layers are intentionally separate:

- `bids.datatype` describes the BIDS datatype directory and filename suffix used for raw BIDS IO, currently `meg` or `eeg`.
- `channels.analysis` describes which channel types are selected for analysis steps such as filtering and ICA.

Conservative examples:

```yaml
# MEG-only, current default
bids:
  datatype: meg
channels:
  analysis:
    meg: true
    eeg: false
```

```yaml
# EEG-only raw BIDS layout
bids:
  datatype: eeg
channels:
  analysis:
    meg: false
    eeg: true
  reference:
    eeg: null
  montage:
    kind: null
    dig: true
```

```yaml
# Combined MEG+EEG when EEG channels are stored in the MEG FIF recording
bids:
  datatype: meg
channels:
  analysis:
    meg: true
    eeg: true
  reference:
    eeg: null
  montage:
    kind: null
    dig: true
```

For combined MEG+EEG data, this repository uses the conservative strategy that the BIDS datatype follows the actual raw BIDS file location/suffix. If the recording is a MEG FIF file that also contains EEG channels, use `bids.datatype: meg` and enable both `channels.analysis.meg` and `channels.analysis.eeg`. Do not assume that this covers every possible BIDS layout; validate concrete datasets with MNE-BIDS and the BIDS validator before treating them as final.

Source modeling requirements differ by modality:

- MEG-only source models can use a single-layer BEM model when scientifically appropriate.
- EEG-only and MEG+EEG source models need an EEG-capable, typically three-layer, BEM model.
- EEG source models require valid electrode positions, usually via digitization points or an explicit montage.

Empty-room covariance (`source.noise_cov.mode: erm`) is MEG-specific. For EEG-only it should not be used. For MEG+EEG, avoid silently mixing MEG empty-room covariance with EEG channels; use a joint baseline covariance such as `source.noise_cov.mode: epochs_baseline` or run a MEG-only source model until a project-specific covariance strategy is explicit.

Current TODOs:

- Thread `channels.analysis` through all preprocessing, cleaning, epoching, evoked, and source-modeling calls.
- Add explicit source-modeling channel flags derived from config.
- Add EEG montage/reference handling only when explicitly configured.
- Add small synthetic unit tests for MEG-only, EEG-only, and MEG+EEG channel-selection behavior.
