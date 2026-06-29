#!/usr/bin/env bash
set -euo pipefail

CONFIG=${CONFIG:-configs/local.yaml}
OUT=${OUT:-cluster/recordings.tsv}

mkdir -p "$(dirname "$OUT")"
meegpipe list-recordings --config "$CONFIG" --tsv > "$OUT"

N=$(( $(wc -l < "$OUT") - 1 ))
echo "Wrote $OUT with $N recording(s)."
echo "Use --array=1-$N in Slurm."
