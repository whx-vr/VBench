#!/usr/bin/env python3
"""
Build prompt-keyed clean score JSON from raw id-keyed bon_rewards.json.

Input leaf format per id:
  {
    "0": {"VQ": ..., "MQ": ..., "TA": ..., "Overall": ...},
    ...
    "9": {...}
  }

Output format:
  {
    "{prompt_en}|{dim,...}": {"0": float, ... "9": float},
    ...
  }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _prompt_rm_pipeline import load_align_prompts, rekey_raw_to_prompt_clean
from _repo_root import REPO_ROOT


def _overall_from_leaf(leaf: object) -> float:
    if isinstance(leaf, list):
        if not leaf:
            raise ValueError("empty list leaf")
        first = leaf[0]
        if not isinstance(first, dict):
            raise TypeError(f"list leaf[0] must be dict, got {type(first)}")
        if "Overall" not in first:
            raise KeyError(f"missing Overall in list leaf[0]: {first!r}")
        return float(first["Overall"])
    if isinstance(leaf, dict):
        if "Overall" not in leaf:
            raise KeyError(f"missing Overall in dict leaf: {leaf!r}")
        return float(leaf["Overall"])
    raise TypeError(f"unsupported leaf type: {type(leaf)}")


def clean_bon_variants(variants: dict) -> dict[str, float]:
    rows: dict[str, float] = {}
    numeric_keys = sorted((k for k in variants.keys() if str(k).isdigit()), key=lambda x: int(str(x)))
    if not numeric_keys:
        raise ValueError("no numeric sample keys found in id payload")
    for k in numeric_keys:
        rows[str(k)] = _overall_from_leaf(variants[k])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Raw id-keyed bon_rewards.json -> prompt-keyed clean scores.")
    ap.add_argument(
        "--align",
        type=Path,
        default=REPO_ROOT / "resources/vbench_prompt_align_gpt.json",
    )
    ap.add_argument(
        "--vbench_full_info",
        type=Path,
        default=REPO_ROOT / "vbench/VBench_full_info.json",
    )
    ap.add_argument(
        "--in",
        dest="inp",
        type=Path,
        default=REPO_ROOT / "resource_dirty/previous_rm_result/bon_rewards.json",
    )
    ap.add_argument(
        "--out_prompt_idx",
        type=Path,
        default=REPO_ROOT / "resources/previous_rm_result/prompt_idx/bon_rewards.json",
    )
    ap.add_argument(
        "--out_clean",
        type=Path,
        default=REPO_ROOT / "resources/previous_rm_result/clean/bon_rewards.json",
    )
    args = ap.parse_args()

    align_prompt = load_align_prompts(args.align)
    full_info = json.loads(args.vbench_full_info.read_text(encoding="utf-8"))
    if not isinstance(full_info, list):
        print("full_info root must be a list", file=sys.stderr)
        return 1
    data = json.loads(args.inp.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("Root JSON must be an object", file=sys.stderr)
        return 1

    cleaned = rekey_raw_to_prompt_clean(
        data,
        full_info=full_info,
        align_prompt=align_prompt,
        source_name="bon_rewards.json",
        clean_variants=clean_bon_variants,
    )
    text = json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n"

    args.out_prompt_idx.parent.mkdir(parents=True, exist_ok=True)
    args.out_prompt_idx.write_text(text, encoding="utf-8")
    print(f"Wrote {len(cleaned)} prompts -> {args.out_prompt_idx}")

    args.out_clean.parent.mkdir(parents=True, exist_ok=True)
    args.out_clean.write_text(text, encoding="utf-8")
    print(f"Wrote {len(cleaned)} prompts -> {args.out_clean}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
