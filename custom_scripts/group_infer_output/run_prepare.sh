#!/usr/bin/env bash
# Example: build id->dimensions JSON, then materialize for one model.
#   bash custom_scripts/group_infer_output/run_prepare.sh /path/to/infer_root my_model_name
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$REPO/custom_scripts/group_infer_output"
INFER_ROOT="${1:?infer root (contains <id>/0.mp4)}"
MODEL="${2:?model name (subfolder under vbench_videos)}"
OUT_BASE="${3:-$REPO/vbench_videos}"
MAP="${4:-$HERE/id_dimensions.json}"

python3 "$HERE/map_infer_ids.py" -o "$MAP"
python3 "$HERE/materialize_eval_layout.py" \
  --mapping "$MAP" \
  --infer-root "$INFER_ROOT" \
  --out-base "$OUT_BASE" \
  --model "$MODEL" \
  --method symlink \
  --on-duplicate-prompt keep_lowest_id

echo "Next: bash evaluate.sh  or  bash custom_scripts/bound/run_evaluate_bounds.sh $OUT_BASE $MODEL <dimension>"
