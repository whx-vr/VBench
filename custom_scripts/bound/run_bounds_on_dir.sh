#!/usr/bin/env bash
# After all dimensions are evaluated (paired *_eval_results.json + *_full_info.json
# in the same directory), print leaderboard-style scores for max-bound and min-bound.
#
# Usage:
#   bash custom_scripts/bound/run_bounds_on_dir.sh [evaluation_results_dir]
#
# Default evaluation_results_dir: ./evaluation_results

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="${1:-./evaluation_results}"

echo "==== directory: $OUT_DIR | bound: max ===="
python custom_scripts/bound/cal_bound_score.py --results_dir "$OUT_DIR" --bound max

echo "==== directory: $OUT_DIR | bound: min ===="
python custom_scripts/bound/cal_bound_score.py --results_dir "$OUT_DIR" --bound min
