#!/usr/bin/env bash
# Map infer id tree -> VBench folder layout, with configurable sample indices.
#
# Usage (same as run_prepare.sh + optional indices):
#   bash custom_scripts/group_infer_output/run_prepare_with_indices.sh \
#     <infer_root> <model> [out_base] [mapping.json] [indices_csv]
#
# Examples:
#   # default indices 0-4 (same as run_prepare.sh)
#   bash custom_scripts/group_infer_output/run_prepare_with_indices.sh \
#     /path/to/infer_root my_model
#
#   # BoN 10: infer has 0..9 per id
#   bash custom_scripts/group_infer_output/run_prepare_with_indices.sh \
#     /path/to/infer_root my_model ./vbench_videos "" "0,1,2,3,4,5,6,7,8,9"
#
# After this, evaluate with custom seed range, e.g.:
#   python3 custom_scripts/eval_custom/evaluate_custom.py \
#     --videos_path <out_base>/<model>/<folder_from_evaluate_sh> \
#     --dimension subject_consistency \
#     --seed_start 0 --seed_end 9

set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$REPO/custom_scripts/group_infer_output"

INFER_ROOT="${1:?infer root (contains <id>/<i>.mp4)}"
MODEL="${2:?model name (subfolder under vbench_videos)}"
OUT_BASE="${3:-$REPO/vbench_videos}"
MAP="${4:-$HERE/id_dimensions.json}"
INDICES="${5:-0,1,2,3,4}"

python3 "$HERE/map_infer_ids.py" -o "$MAP"
python3 "$HERE/materialize_eval_layout.py" \
  --mapping "$MAP" \
  --infer-root "$INFER_ROOT" \
  --out-base "$OUT_BASE" \
  --model "$MODEL" \
  --method symlink \
  --on-duplicate-prompt keep_lowest_id \
  --indices "$INDICES"

echo "materialized indices: $INDICES"
echo "Next: python3 custom_scripts/eval_custom/evaluate_custom.py --videos_path ... --dimension <dim> --seed_start <lo> --seed_end <hi>"
echo "  (lo/hi must match the indices you materialized, e.g. 0 and 9 for BoN=10)"
