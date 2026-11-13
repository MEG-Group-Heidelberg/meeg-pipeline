# Getting started

A step-by-step path from an original MEG recording to source-space label time
courses. It assumes no programming experience beyond typing commands into a
terminal and clicking through Jupyter notebooks. The [README](../README.md) is
the reference; this page is the recipe.

## What you need

- A Mac or Linux computer with Python 3.11 or newer (`python3 --version`).
- The package installed as described in the README (`meegpipe --version` must
  print a version).
- For anatomy from MRI: [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/) and
  `dcm2niix`. Not needed if you only use the template anatomy (step 9).
- VS Code or JupyterLab. In both, choose the kernel from the environment where
  you installed the package, e.g. `~/MEEG/.venv/bin/python`.

## Two ways to work

- **Notebooks** (`notebooks/`): open one, read the text at the top, change the
  values in the first code cell ("settings"), run the cells from top to bottom.
  Every notebook shows a status table before it writes anything.
- **Command line** (`meegpipe ...`): the same functions as one-line commands,
  useful for many recordings or a cluster. Not every step has a command yet; see
  [Which steps have a command](#which-steps-have-a-command).

Both ways write the same files, so you can mix them. Existing outputs are never
overwritten unless you ask for it (`OVERWRITE_STEPS` in the notebooks,
`--overwrite` on the command line).

## The path, step by step

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
| 9 | Anatomy | `1A_anatomy/01` to `04` | `meegpipe anatomy-info --config configs/local.yaml` | see [Anatomy](#anatomy-with-or-without-mri) |
| 10 | Epoch | `1B_preprocessing/07_epoching` | - | `epochs.tmin`, `epochs.tmax`, `conditions.definitions` |
| 11 | Evoked responses | `2_sensor_analysis/01_evokeds` | - | condition definitions |
| 12 | Forward solution | `3_source_modeling/01_forward_solution` | `meegpipe source-forward ...` | transform and BEM exist (status table) |
| 13 | Noise covariance, inverse | `02_noise_covariance`, `03_inverse_operator` | `meegpipe source-noise-cov ...`, `meegpipe source-inverse ...` | `source.noise_cov.mode` |
| 14 | Source estimates and label time courses | `04` to `07` | `meegpipe source-apply-inverse ...`, `source-label-time-courses ...` | `source.labels.parcellation` |
| 15 | Continuous source time courses (e.g. reverse correlation) | `08_apply_inverse_raw_labels` | `meegpipe source-apply-inverse-raw ...` | `source.apply_inverse.raw` |

Run notebook `00_project_summary` at any time. It is read-only and shows which
steps are finished for which recording.

## Required config fields

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

## Anatomy: with or without MRI

Each subject gets its anatomy from one of three sources, set in
`anatomy.mode` (project default) or per subject in `anatomy.subjects`:

| Mode | When | What happens |
| --- | --- | --- |
| `individual_mri` | the subject has an MRI | notebooks `1A_anatomy/01` to `04`: convert, `recon-all`, BEM and source space, coregistration |
| `scaled_template` | no MRI, but head points were digitised | the template (fsaverage) is scaled to the head shape; `meegpipe anatomy-scaled-template --config configs/local.yaml --subject XXXX` |
| `template` | no MRI, no scaling | the unscaled template is used |

`meegpipe anatomy-info --config configs/local.yaml` shows the mode and the
preparation status of every subject. A scaled template is less accurate than an
individual MRI; check the quality values in notebook `1A_anatomy/04_coregistration`
and say in your methods which mode was used.

## Which steps have a command

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
| `meegpipe: command not found` | the environment is not active: `source ~/MEEG/.venv/bin/activate` |
| warning `contains keys the pipeline does not use` | the listed key is misspelled or was renamed; compare with the config template |
| a recording is missing from `sourcedata-info` | wrong folder layout; compare with the README section "First data import" |
| no or too many events | check `events.extraction.stim_channels` and `min_gap_s`; inspect with `meegpipe events-info` |
| step is skipped with status `exists` | by design; rerun with `OVERWRITE_STEPS` or `--overwrite` |
| `scale_mri` or FreeSurfer fails on files like `._xyz` | macOS metadata files on external drives; delete them: `find <project> -name '._*' -delete` |
| interactive plot does not open | restart the kernel and run the Qt setup cell first (README, "Interactive plotting setup") |
| source step reports a missing input | the previous step has not run for this recording; the status table names it |

## Where to go next

- [README](../README.md): installation, layout, configuration, all commands.
- `notebooks/00_project_summary.ipynb`: overview of your project's progress.
