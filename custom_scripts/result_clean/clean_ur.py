#!/usr/bin/env python3
"""
Build ur clean score JSON (prompt row key -> sample floats) from **raw** id-keyed ur.json.

Same output as ``convert_raw_rm_to_prompt_keys.py`` for ur only; use when you refresh a
single modality without re-running the full converter.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _prompt_rm_pipeline import clean_ur_variants, load_align_prompts, rekey_raw_to_prompt_clean
from _repo_root import REPO_ROOT


def main() -> int:
    ap = argparse.ArgumentParser(description="Raw id-keyed ur.json → prompt-keyed clean scores.")
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
        default=REPO_ROOT / "resource_dirty/previous_rm_result/raw/ur.json",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "resources/previous_rm_result/clean/ur.json",
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
        source_name="ur.json",
        clean_variants=clean_ur_variants,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(cleaned)} prompts → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
