# Cluster batch helpers

This folder contains minimal Slurm helpers for running recording-wise `meegpipe` jobs.

## 1. Create a recordings table

From the project root, after activating the environment in which `meegpipe` is installed:

```
scripts/cluster/make_recordings_tsv.sh
```

This writes:

```
cluster/recordings.tsv
```

The table has one row per BIDS recording and is used by the Slurm array script.

## 2. Submit one source-modeling step as a job array

Example for epoch-wise source-label time courses:

```
N=$(( $(wc -l < cluster/recordings.tsv) - 1 ))

sbatch \
  --array=1-${N} \
  --export=ALL,PROJECT_ROOT=$PWD,LIB_ROOT=/path/to/meeg-pipeline,VENV=/path/to/.venv,MEEGPIPE_STEP=source-label-time-courses-epochs,EXTRA_ARGS='--decim 5 --dtype float32' \
  scripts/cluster/source_step_array.sbatch
```

Adjust `--time`, `--mem`, and `--cpus-per-task` in `source_step_array.sbatch` or pass Slurm overrides on submission.

Supported `MEEGPIPE_STEP` values currently include:

```
source-forward
source-noise-cov
source-inverse
source-apply-inverse
source-label-time-courses
source-label-time-courses-epochs
```

Use `EXTRA_ARGS` for step-specific options, for example:

```
EXTRA_ARGS='--spacing ico5'
EXTRA_ARGS='--noise-cov-mode erm'
EXTRA_ARGS='--conditions keyChange cond1stNonDiatonic'
EXTRA_ARGS='--decim 5 --dtype float32'
```

## 3. Local smoke test before submitting

Run one recording locally first:

```
meegpipe source-label-time-courses-epochs \
  --config configs/local.yaml \
  --subject 1409 \
  --task chords \
  --decim 5 \
  --dtype float32 \
  --verbose
```
