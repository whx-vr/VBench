#!/usr/bin/env bash
# Raw id-keyed RM JSON -> prompt-keyed clean scores in prompt_idx/ and clean/ (ur, vr, vs2).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$REPO/custom_scripts/result_clean"
cd "$HERE"
python3 convert_raw_rm_to_prompt_keys.py
echo "Done. prompt_idx + clean: $REPO/resources/previous_rm_result/{prompt_idx,clean}/"
