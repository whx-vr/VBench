#!/usr/bin/env python3
"""
Compute VBench-style total / quality / semantic scores.

Modes:
  1) Default (--bound max|min): per-prompt max/min over per-video scores, then
     mean across prompts (custom bound). When per-video data is missing or
     aggregation fails, falls back to official dim_result[0] (same as
     cal_final_score_from_eval_dir) so dimensions are not silently 0.
  2) --eval-scalars-only: merge official [0] from *_eval_results.json only —
     matches scripts/cal_final_score_from_eval_dir.py (no full_info / bound).

Example:
  python custom_scripts/bound/cal_bound_score.py \\
    --results_dir ./evaluation_results --bound max

  python custom_scripts/bound/cal_bound_score.py \\
    --results_dir ./evaluation_results --eval-scalars-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from bound_scoring import (  # noqa: E402
    bound_scores_from_pair,
    merge_bound_maps,
    pair_paths_in_dir,
)
from constant import TASK_INFO  # noqa: E402
from cal_final_score import (  # noqa: E402
    get_final_score,
    get_nomalized_score,
    get_quality_score,
    get_semantic_score,
)


def upload_dict_from_dim_scores(dim_scores: dict) -> dict:
    """TASK_INFO keys (spaces); missing dims -> 0.0 like leaderboard submission."""
    upload: dict = {}
    for key in TASK_INFO:
        # eval JSON uses underscores
        under = key.replace(" ", "_")
        upload[key] = float(dim_scores.get(under, 0.0))
    return upload


def write_submission_json(path: str, dim_scores: dict) -> None:
    """Format compatible with scripts/cal_final_score.py (value[0] is scalar)."""
    payload = {}
    for k, v in dim_scores.items():
        payload[k] = [float(v), []]
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-prompt max/min bound or official eval scalars")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--results_dir",
        type=str,
        help="Directory containing paired *_eval_results.json and *_full_info.json",
    )
    src.add_argument(
        "--pair",
        nargs=2,
        metavar=("FULL_INFO", "EVAL_RESULTS"),
        help="Single full_info.json and eval_results.json path",
    )
    parser.add_argument(
        "--bound",
        choices=("max", "min"),
        default=None,
        help="Within each prompt, take max or min over sample videos (ignored with --eval-scalars-only)",
    )
    parser.add_argument(
        "--eval-scalars-only",
        action="store_true",
        help="Use merged official [0] from *_eval_results.json only (same as cal_final_score_from_eval_dir.py)",
    )
    parser.add_argument(
        "--index_lo",
        type=int,
        default=None,
        help="Inclusive low sample index from basename ...-{i}.mp4 (bound mode only).",
    )
    parser.add_argument(
        "--index_hi",
        type=int,
        default=None,
        help="Inclusive high sample index from basename ...-{i}.mp4 (bound mode only).",
    )
    parser.add_argument(
        "--write_submission",
        type=str,
        default="",
        help="Optional path to write JSON {dim: [scalar, []]} for zip / cal_final_score.py",
    )
    args = parser.parse_args()

    if (args.index_lo is None) ^ (args.index_hi is None):
        parser.error("Provide both --index_lo and --index_hi, or neither.")

    if args.eval_scalars_only:
        if args.bound is not None:
            parser.error("Do not pass --bound together with --eval-scalars-only")
        if args.index_lo is not None or args.index_hi is not None:
            parser.error("--index_lo/--index_hi are only valid in --bound mode")
        from cal_final_score_from_eval_dir import load_from_eval_output  # noqa: E402

        if args.pair:
            eval_path = os.path.abspath(args.pair[1])
            out_dir = os.path.dirname(eval_path)
            base = os.path.basename(eval_path)
            upload, used_paths = load_from_eval_output(out_dir, base)
        else:
            upload, used_paths = load_from_eval_output(args.results_dir, None)
        merged = {k.replace(" ", "_"): float(upload[k]) for k in TASK_INFO}
        print("mode: eval_json [0] scalars only (matches cal_final_score_from_eval_dir)")
        print(f"Loaded {len(used_paths)} eval result file(s)")
        for p in used_paths:
            print(f"  {p}")
    else:
        if args.bound is None:
            parser.error("Pass --bound max|min, or use --eval-scalars-only")
        if args.pair:
            full_info_path, eval_path = args.pair
            merged = bound_scores_from_pair(
                full_info_path,
                eval_path,
                args.bound,
                index_lo=args.index_lo,
                index_hi=args.index_hi,
            )
        else:
            pairs = pair_paths_in_dir(args.results_dir)
            if not pairs:
                raise SystemExit(
                    f"No paired *_eval_results.json + *_full_info.json under {args.results_dir!r}"
                )
            maps = [
                bound_scores_from_pair(
                    fp,
                    ep,
                    args.bound,
                    index_lo=args.index_lo,
                    index_hi=args.index_hi,
                )
                for fp, ep in sorted(pairs)
            ]
            merged = merge_bound_maps(maps)
        print(f"bound mode: {args.bound} (with official [0] fallback when per-video bound is unavailable)")
        if args.index_lo is not None:
            print(f"sample index filter: [{args.index_lo}, {args.index_hi}]")

    upload = upload_dict_from_dim_scores(merged)
    normalized = get_nomalized_score(upload)
    quality = get_quality_score(normalized)
    semantic = get_semantic_score(normalized)
    final = get_final_score(quality, semantic)

    print(f"dimensions with non-zero raw scores in dict: {sum(1 for k in TASK_INFO if upload[k] != 0.0)}")
    if len(merged) < len(TASK_INFO):
        missing = [k.replace(" ", "_") for k in TASK_INFO if k.replace(" ", "_") not in merged]
        print(f"warning: missing {len(missing)} dimension keys in merged; they count as 0.0")
    print("+------------------|------------------+")
    print(f"|     quality score|{quality}|")
    print(f"|    semantic score|{semantic}|")
    print(f"|       total score|{final}|")
    print("+------------------|------------------+")

    if args.write_submission:
        write_submission_json(args.write_submission, merged)
        print(f"wrote submission-style json: {args.write_submission}")


if __name__ == "__main__":
    main()
