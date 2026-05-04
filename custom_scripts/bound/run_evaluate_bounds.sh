#!/usr/bin/env bash
# Same dimension <-> folder alignment as repo root evaluate.sh.
# Usage: bash custom_scripts/bound/run_evaluate_bounds.sh <base_path> <model> <dimension> [output_dir]
# Example: bash custom_scripts/bound/run_evaluate_bounds.sh ./vbench_videos/ lavie aesthetic_quality

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

dimensions=("subject_consistency" "background_consistency" "aesthetic_quality" "imaging_quality" "object_class" "multiple_objects" "color" "spatial_relationship" "scene" "temporal_style" "overall_consistency" "human_action" "temporal_flickering" "motion_smoothness" "dynamic_degree" "appearance_style")
folders=("subject_consistency" "scene" "overall_consistency" "overall_consistency" "object_class" "multiple_objects" "color" "spatial_relationship" "scene" "temporal_style" "overall_consistency" "human_action" "temporal_flickering" "subject_consistency" "subject_consistency" "appearance_style")

base_path="${1:?base_path}"
model="${2:?model}"
dimension="${3:?dimension}"
output_dir="${4:-./evaluation_results}"

folder=""
for i in "${!dimensions[@]}"; do
  if [[ "${dimensions[$i]}" == "$dimension" ]]; then
    folder="${folders[$i]}"
    break
  fi
done
if [[ -z "$folder" ]]; then
  echo "unknown dimension: $dimension (not in list)" >&2
  exit 1
fi

videos_path="${base_path%/}/${model}/${folder}"
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

python evaluate.py --videos_path "$videos_path" --dimension "$dimension" --output_path "$output_dir"

latest_eval="$(ls -t "$output_dir"/*_eval_results.json 2>/dev/null | head -1 || true)"
if [[ -z "$latest_eval" ]]; then
  echo "No *_eval_results.json under $output_dir" >&2
  exit 1
fi
stem="${latest_eval%_eval_results.json}"
full_info="${stem}_full_info.json"
if [[ ! -f "$full_info" ]]; then
  echo "Missing: $full_info" >&2
  exit 1
fi

echo "==== bound: max ===="
python custom_scripts/bound/cal_bound_score.py --pair "$full_info" "$latest_eval" --bound max
echo "==== bound: min ===="
python custom_scripts/bound/cal_bound_score.py --pair "$full_info" "$latest_eval" --bound min
