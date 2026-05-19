#!/usr/bin/env bash
# Merge videos*/prompt_id/seed-id.mp4 from several infer roots into one tree.
#
# Example (seeds 0-4 and 5-9 from two runs):
#   bash custom_scripts/merge_video/run_merge.sh \
#     /path/infer_seed0_4 /path/infer_seed5_9 \
#     /path/merged_infer
#
# Extra args are forwarded to the Python script (--method copy, --dry-run, ...).

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <src_root1> <src_root2> ... <out_root> [-- extra python args]" >&2
  echo "  Merges all videos* under each src into {out_root}/videos/" >&2
  exit 1
fi

OUT="${@: -1}"
SRCS=("${@:1:$# - 1}")

exec python3 "$REPO/custom_scripts/merge_video/merge_infer_videos.py" \
  --src "${SRCS[@]}" \
  --out "$OUT"
