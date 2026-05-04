"""
Aggregate VBench final scores from evaluate.py output on disk (no zip).

evaluate.py typically writes one pair per run:
  {output_path}/results_<time>_eval_results.json
Often each file has one dimension key when running one dimension at a time
(e.g. evaluate.sh). This script merges all ``*_eval_results.json`` under
``--output_dir``, matching scripts/cal_final_score.py behavior over multiple
JSON files (later files overwrite duplicate dimension keys).
"""

import argparse
import glob
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from constant import TASK_INFO  # noqa: E402

from cal_final_score import (  # noqa: E402
    get_final_score,
    get_nomalized_score,
    get_quality_score,
    get_semantic_score,
)


def _scalar_from_dimension_value(val):
    """Match cal_final_score.submission: use first element when value is a list/tuple."""
    if isinstance(val, (list, tuple)):
        if len(val) == 0:
            raise ValueError("empty list/tuple in eval results")
        return float(val[0])
    return float(val)


def load_from_eval_output(output_dir, results_json=None):
    """
    Build upload_data dict (space-separated dimension names) from evaluate output.

    If results_json is None: load and merge every ``*_eval_results.json`` under
    output_dir (sorted paths for stable merge order; same dimension in multiple
    files keeps the last file's value).

    If results_json is set: load that single file only.
    """
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"Not a directory: {output_dir}")

    if results_json:
        paths = [
            results_json
            if os.path.isabs(results_json)
            else os.path.join(output_dir, results_json)
        ]
    else:
        paths = sorted(glob.glob(os.path.join(output_dir, "*_eval_results.json")))
        if not paths:
            raise FileNotFoundError(
                f"No '*_eval_results.json' under {output_dir}. "
                "Set --results_json to a specific file from evaluate.py."
            )

    upload_data = {}
    for path in paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Results file not found: {path}")
        with open(path, encoding="utf-8") as f:
            cur_json = json.load(f)
        if not isinstance(cur_json, dict):
            raise ValueError(f"Expected a JSON object in {path}, got {type(cur_json)}")
        for key in cur_json:
            upload_data[key.replace("_", " ")] = _scalar_from_dimension_value(cur_json[key])

    for key in TASK_INFO:
        if key not in upload_data:
            upload_data[key] = 0

    return upload_data, paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Final score from evaluate.py output directory (no zip)."
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="Same as evaluate.py --output_path (directory containing *_eval_results.json).",
    )
    parser.add_argument(
        "--results_json",
        type=str,
        default=None,
        help="Optional: exact results file name or path (single file). "
        "If relative, resolved under --output_dir. "
        "If omitted, merges every *_eval_results.json in output_dir.",
    )
    args = parser.parse_args()

    upload_dict, used_paths = load_from_eval_output(args.output_dir, args.results_json)
    print(f"Loaded results from {len(used_paths)} file(s):")
    for p in used_paths:
        print(f"  {p}")
    print(f"your submission info: \n{upload_dict} \n")

    normalized_score = get_nomalized_score(upload_dict)
    quality_score = get_quality_score(normalized_score)
    semantic_score = get_semantic_score(normalized_score)
    final_score = get_final_score(quality_score, semantic_score)
    print("+------------------|------------------+")
    print(f"|     quality score|{quality_score}|")
    print(f"|    semantic score|{semantic_score}|")
    print(f"|       total score|{final_score}|")
    print("+------------------|------------------+")
