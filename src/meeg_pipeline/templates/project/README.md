# {{ project_name }}

This is a M/EEG analysis project initialized with `meegpipe init-project`.

The outer project folder is an analysis workspace. It contains configs,
notebooks, original source exports, and derivatives. The raw BIDS dataset lives
inside `rawdata/`.

## Folder layout

```text
{{ project_name }}/
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
  rawdata/
  derivatives/
    meeg-pipeline/
    freesurfer/
```

## First steps

1. Edit `configs/local.yaml`.
2. Put original M/EEG acquisition exports under `sourcedata/`.
3. Put raw MRI exports under `sourcedata/mri_raw/`, or standardized MRI inputs
   under `sourcedata/mri/`.
4. Check the config and project layout:

   ```bash
   meegpipe config-info --config configs/local.yaml
   meegpipe sourcedata-info --config configs/local.yaml
   meegpipe bids-info --config configs/local.yaml
   ```

5. Open `notebooks/00_project_summary.ipynb` and then proceed through the
   workflow notebooks.

## Raw BIDS root

`rawdata/` is the raw BIDS dataset root. BIDS metadata files such as
`dataset_description.json`, `participants.tsv`, and `participants.json` belong in
`rawdata/`, not in the outer project folder.

## Source data

`sourcedata/` contains original acquisition exports and should remain unchanged.
The source-data folder structure encodes subject, optional source session, task,
and optional run information.

Examples for a MEG project:

```text
sourcedata/sub-0001/meg/task-example/<original_file>.fif
sourcedata/sub-0001/ses-20260523/meg/task-example/<original_file>.fif
```

Examples for an EEG project:

```text
sourcedata/sub-0001/eeg/task-example/<original_file>.vhdr
sourcedata/sub-0001/eeg/task-example/<original_file>.eeg
sourcedata/sub-0001/eeg/task-example/<original_file>.vmrk
sourcedata/sub-0001/ses-20260523/eeg/task-example/<original_file>.vhdr
```

For a combined M/EEG project, `init-project --modality meeg` creates both `meg/`
and `eeg/` example folders. Use the folder matching the original source export
for each recording.

By default, `sourcedata.sessions` is set to `ignore`, so source `ses-*` folders
can be used for local organization without becoming BIDS session entities. Set
`sourcedata.sessions: "include"` for true multi-session BIDS datasets.

## MEG, EEG, and combined MEG+EEG

Two config layers are intentionally separate:

- `bids.datatype` describes the raw BIDS datatype directory and file suffix
  currently used for IO, usually `meg` or `eeg`.
- `channels.analysis` describes which channel types should be used in analysis
  steps such as filtering, ICA, epoching, and source-modeling channel flags.

The default project is conservative MEG-only unless `--modality` is passed:

```yaml
bids:
  datatype: "meg"
channels:
  analysis:
    meg: true
    eeg: false
```

For pure EEG raw BIDS data, use `bids.datatype: "eeg"` and enable EEG analysis
channels. For combined MEG+EEG in a MEG FIF recording, keep `bids.datatype:
"meg"` and enable both `channels.analysis.meg` and `channels.analysis.eeg`.
Validate concrete datasets with MNE-BIDS and the BIDS validator before treating a
layout as final.

## Anatomy and source modeling

The `anatomy.mode` field in `configs/local.yaml` records whether the project is
intended to use subject-specific anatomy or template anatomy:

```yaml
anatomy:
  mode: "individual_mri"  # "individual_mri" | "fsaverage"
```

With `anatomy.mode: "individual_mri"`, the normal anatomy sequence is:

```text
1A_anatomy/01_convert_mri.ipynb
1A_anatomy/02_recon.ipynb
1A_anatomy/03_anatomy_setup.ipynb
1A_anatomy/04_coregistration.ipynb
```

With `anatomy.mode: "fsaverage"`, individual MRI conversion and recon-all are
not required. Treat the anatomy notebooks as:

```text
1A_anatomy/01_convert_mri.ipynb      not required
1A_anatomy/02_recon.ipynb            not required
1A_anatomy/03_anatomy_setup.ipynb    still relevant: ensure fsaverage geometry
1A_anatomy/04_coregistration.ipynb   different strategy: standard montage /
                                     template-based alignment
```

`fsaverage` is most plausible for pure EEG projects with a standard or
approximately equidistant cap, for example a project initialized with:

```bash
meegpipe init-project my-eeg-project \
  --modality eeg \
  --anatomy fsaverage \
  --montage standard_1020
```

MEG-only source modeling can use a one-layer BEM when scientifically appropriate.
EEG-only and combined MEG+EEG source modeling require an EEG-capable, typically
three-layer, BEM and valid electrode positions from digitization points or an
explicit montage.

Empty-room covariance is MEG-specific. For EEG-only or combined MEG+EEG source
models, prefer a project-specific baseline covariance strategy until the
covariance model is explicit.

Source-level results based on `fsaverage` should be reported as template-based
and less anatomically precise than individual MRI-based source localization.

## Notebook template status

The notebook tree is part of the project template. The current folder name
`1B_preprocessing/` is retained for backward compatibility, but the workflow
is intended to become the shared M/EEG preprocessing workflow. Do not create a
separate `1C_eeg_processing/` workflow unless a future project has a strong
reason to diverge.

Notebook steps should stay thin: use reusable functions from `meeg_pipeline` for
processing logic and keep project-specific choices in `configs/local.yaml` or in
clearly marked project-specific notebook sections.
