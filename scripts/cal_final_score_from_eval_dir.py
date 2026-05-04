"""
Aggregate VBench final scores from evaluate.py output on disk (no zip).

evaluate.py writes a single JSON: {output_path}/{name}_eval_results.json
with one key per dimension (underscore names) and values typically
[aggregate_score, per_video_details].
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

    If results_json is None, picks the newest *_eval_results.json under output_dir.
    """
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"Not a directory: {output_dir}")

    if results_json:
        path = (
            results_json
            if os.path.isabs(results_json)
            else os.path.join(output_dir, results_json)
        )
    else:
        candidates = glob.glob(os.path.join(output_dir, "*_eval_results.json"))
        if not candidates:
            raise FileNotFoundError(
                f"No '*_eval_results.json' under {output_dir}. "
                "Set --results_json to the file from evaluate.py (e.g. results_*_eval_results.json)."
            )
        path = max(candidates, key=os.path.getmtime)

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Results file not found: {path}")

    with open(path, encoding="utf-8") as f:
        cur_json = json.load(f)

    if not isinstance(cur_json, dict):
        raise ValueError(f"Expected a JSON object in {path}, got {type(cur_json)}")

    upload_data = {}
    for key in cur_json:
        upload_data[key.replace("_", " ")] = _scalar_from_dimension_value(cur_json[key])

    for key in TASK_INFO:
        if key not in upload_data:
            upload_data[key] = 0

    return upload_data, path


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
        help="Optional: exact results file name or path. "
        "If relative, resolved under --output_dir. "
        "If omitted, uses the newest *_eval_results.json in output_dir.",
    )
    args = parser.parse_args()

    upload_dict, used_path = load_from_eval_output(args.output_dir, args.results_json)
    print(f"Loaded results from: {used_path}")
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
