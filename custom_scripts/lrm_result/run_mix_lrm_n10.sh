#!/usr/bin/env bash
# Regenerate resources/lrm_n10_new (mixed step5 / step10 tie JSONs).
# All extra args are forwarded to the Python script (--seed, --src_dir, --out_dir, ...).
#
# Examples (from anywhere):
#   bash /path/to/VBench/custom_scripts/lrm_result/run_mix_lrm_n10.sh
#   bash .../run_mix_lrm_n10.sh --seed 0
#   bash .../run_mix_lrm_n10.sh --seed 7 --out_dir /tmp/lrm_n10_run7

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$REPO/custom_scripts/lrm_result/mix_lrm_n10_prompt_timesteps.py" "$@"
