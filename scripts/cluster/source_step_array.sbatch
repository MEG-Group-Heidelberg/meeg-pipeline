#!/usr/bin/env bash
#SBATCH --job-name=meeg-source
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --array=1-1

set -euo pipefail

# Required/typical runtime settings. Override with sbatch --export=ALL,VAR=value,...
PROJECT_ROOT=${PROJECT_ROOT:-$PWD}
LIB_ROOT=${LIB_ROOT:-}
CONFIG=${CONFIG:-configs/local.yaml}
RECORDINGS_TSV=${RECORDINGS_TSV:-cluster/recordings.tsv}
MEEGPIPE_STEP=${MEEGPIPE_STEP:-source-label-time-courses-epochs}
EXTRA_ARGS=${EXTRA_ARGS:-}
OVERWRITE=${OVERWRITE:-0}
VERBOSE=${VERBOSE:-1}
VENV=${VENV:-}

cd "$PROJECT_ROOT"
mkdir -p logs

if [[ -n "$VENV" ]]; then
  # shellcheck disable=SC1090
  source "$VENV/bin/activate"
fi

if [[ -n "$LIB_ROOT" ]]; then
  export PYTHONPATH="$LIB_ROOT/src:${PYTHONPATH:-}"
fi

if [[ ! -f "$RECORDINGS_TSV" ]]; then
  echo "Missing recordings table: $RECORDINGS_TSV" >&2
  exit 2
fi

ROW=$(awk -v i="$SLURM_ARRAY_TASK_ID" 'BEGIN { FS="\t" } NR == i + 1 { print }' "$RECORDINGS_TSV")
if [[ -z "$ROW" ]]; then
  echo "No row for SLURM_ARRAY_TASK_ID=$SLURM_ARRAY_TASK_ID in $RECORDINGS_TSV" >&2
  exit 2
fi

IFS=$'\t' read -r INDEX RECORDING SUBJECT SESSION TASK RUN <<< "$ROW"

args=("$MEEGPIPE_STEP" --config "$CONFIG" --subject "$SUBJECT")
if [[ -n "${TASK:-}" && "$TASK" != "None" && "$TASK" != "nan" ]]; then
  args+=(--task "$TASK")
fi
if [[ -n "${SESSION:-}" && "$SESSION" != "None" && "$SESSION" != "nan" ]]; then
  args+=(--session "$SESSION")
fi
if [[ -n "${RUN:-}" && "$RUN" != "None" && "$RUN" != "nan" ]]; then
  args+=(--run "$RUN")
fi
if [[ "$OVERWRITE" == "1" ]]; then
  args+=(--overwrite)
fi
if [[ "$VERBOSE" == "1" ]]; then
  args+=(--verbose)
fi

# EXTRA_ARGS is intentionally shell-split so Slurm exports can pass e.g. '--decim 5 --dtype float32'.
# shellcheck disable=SC2206
extra_args_array=($EXTRA_ARGS)
args+=("${extra_args_array[@]}")

echo "Host: $(hostname)"
echo "Date: $(date)"
echo "Project root: $PROJECT_ROOT"
echo "Recording: $RECORDING"
echo "Command: meegpipe ${args[*]}"

meegpipe "${args[@]}"

echo "Done: $(date)"
