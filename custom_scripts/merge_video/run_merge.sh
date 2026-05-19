#!/usr/bin/env bash
# Merge video dirs (each: prompt_id/seed-id.mp4) into one output tree.
#
# Example:
#   bash custom_scripts/merge_video/run_merge.sh \
#     /path/videoa_b /path/videoc_d \
#     /path/merged
#
# Or merge all subdirs under a parent:
#   python3 custom_scripts/merge_video/merge_infer_videos.py \
#     --src-parent /path/infer_runs --src-glob 'video*' \
#     --out /path/merged

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <video_dir1> <video_dir2> ... <out_dir>" >&2
  exit 1
fi

OUT="${@: -1}"
SRCS=("${@:1:$# - 1}")

exec python3 "$REPO/custom_scripts/merge_video/merge_infer_videos.py" \
  --src "${SRCS[@]}" \
  --out "$OUT"
