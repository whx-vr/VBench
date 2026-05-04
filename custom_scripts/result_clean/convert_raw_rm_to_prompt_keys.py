#!/usr/bin/env python3
"""
Build prompt-keyed **clean** RM score JSON (same shape as resources/previous_rm_result/clean/).

Reads id-keyed **raw** dumps from resource_dirty/previous_rm_result/raw/{ur,vr,vs2}.json,
maps each id to a VBench ``full_info`` row key ``{prompt_en}|{dimension,...}``, extracts
final numeric scores per sample (UR: Final Score regex; VR: Overall; VS2: overall), then writes:

- ``resources/previous_rm_result/prompt_idx/{ur,vr,vs2}.json``
- ``resources/previous_rm_result/clean/{ur,vr,vs2}.json`` (same content; for --tie_json etc.)

Requires ``resources/vbench_prompt_align_gpt.json`` and ``vbench/VBench_full_info.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _prompt_rm_pipeline import CLEANERS, load_align_prompts, rekey_raw_to_prompt_clean
from _repo_root import REPO_ROOT

RAW_NAMES = ("ur.json", "vr.json", "vs2.json")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Raw id-keyed RM JSON → prompt-keyed clean floats (prompt_idx + clean)."
    )
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
        "--raw_dir",
        type=Path,
        default=REPO_ROOT / "resource_dirty/previous_rm_result/raw",
    )
    ap.add_argument(
        "--out_dir_prompt_idx",
        type=Path,
        default=REPO_ROOT / "resources/previous_rm_result/prompt_idx",
    )
    ap.add_argument(
        "--out_dir_clean",
        type=Path,
        default=REPO_ROOT / "resources/previous_rm_result/clean",
    )
    ap.add_argument(
        "--no_clean",
        action="store_true",
        help="Only write prompt_idx; skip writing resources/previous_rm_result/clean/.",
    )
    args = ap.parse_args()

    align_prompt = load_align_prompts(args.align)
    full_info = json.loads(args.vbench_full_info.read_text(encoding="utf-8"))
    if not isinstance(full_info, list):
        print(f"error: {args.vbench_full_info} root must be a list", file=sys.stderr)
        return 1

    args.out_dir_prompt_idx.mkdir(parents=True, exist_ok=True)
    if not args.no_clean:
        args.out_dir_clean.mkdir(parents=True, exist_ok=True)

    for name in RAW_NAMES:
        cleaner = CLEANERS.get(name)
        if cleaner is None:
            continue
        src = args.raw_dir / name
        if not src.is_file():
            print(f"skip (missing): {src}", file=sys.stderr)
            continue
        data = json.loads(src.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            print(f"error: {src} root must be object", file=sys.stderr)
            return 1

        cleaned = rekey_raw_to_prompt_clean(
            data,
            full_info=full_info,
            align_prompt=align_prompt,
            source_name=name,
            clean_variants=cleaner,
        )
        text = json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n"
        p1 = args.out_dir_prompt_idx / name
        p1.write_text(text, encoding="utf-8")
        print(f"Wrote {len(cleaned)} rows → {p1}")
        if not args.no_clean:
            p2 = args.out_dir_clean / name
            p2.write_text(text, encoding="utf-8")
            print(f"Wrote {len(cleaned)} rows → {p2}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
