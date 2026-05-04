#!/usr/bin/env python3
"""
Lay out infer outputs as vbench_standard expects under:

  {out_base}/{model}/{folder}/{prompt_en}-{i}.mp4

where {folder} matches evaluate.sh for any dimension that shares that folder
with this prompt's dimension set (union so evaluate.sh can be run as-is).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Set

from evaluate_layout import folder_to_dimensions, unique_eval_folders


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy/link infer id/{0..4}.mp4 into VBench evaluate folder layout"
    )
    parser.add_argument(
        "--mapping",
        required=True,
        help="JSON produced by map_infer_ids.py (expects top-level 'entries')",
    )
    parser.add_argument(
        "--infer-root",
        required=True,
        help="Root containing <id>/0.mp4 .. <id>/4.mp4",
    )
    parser.add_argument(
        "--out-base",
        required=True,
        help="e.g. ./vbench_videos — creates {out_base}/{model}/...",
    )
    parser.add_argument("--model", required=True, help="Subfolder name, same as evaluate.sh model")
    parser.add_argument(
        "--method",
        choices=("symlink", "copy"),
        default="symlink",
    )
    parser.add_argument(
        "--indices",
        default="0,1,2,3,4",
        help="Comma-separated sample indices (source files {i}.mp4)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    parser.add_argument(
        "--on-duplicate-prompt",
        choices=("error", "keep_lowest_id"),
        default="error",
        help="When two ids share the same VBench prompt_en in one folder: abort, or keep lowest numeric id",
    )
    args = parser.parse_args()

    indices = [int(x.strip()) for x in args.indices.split(",") if x.strip() != ""]

    data = load_json(args.mapping)
    entries: Dict[str, Any] = data.get("entries") or {}
    if not entries:
        raise SystemExit("mapping JSON has no 'entries'")

    infer_root = os.path.abspath(os.path.expanduser(args.infer_root))
    out_base = os.path.abspath(os.path.expanduser(args.out_base))
    model = args.model

    # folder -> set of (canonical prompt_en, id) to materialize
    folder_prompts: Dict[str, Set[tuple]] = {f: set() for f in unique_eval_folders()}

    for pid, info in entries.items():
        if not isinstance(info, dict):
            continue
        dims = info.get("dimensions") or []
        if not isinstance(dims, list):
            continue
        dim_set = set(str(d) for d in dims)
        pe = str(info.get("prompt_en_vbench") or info.get("prompt") or "")
        if not pe:
            continue

        for folder in folder_prompts.keys():
            need_any = set(folder_to_dimensions(folder))
            if dim_set & need_any:
                folder_prompts[folder].add((pe, str(pid)))

    errors: List[str] = []
    warnings: List[str] = []

    def _pid_int(pid: str) -> int:
        try:
            return int(str(pid))
        except ValueError:
            return 0

    # Same VBench filename cannot come from two ids (unless dedup policy)
    for folder, pairs in list(folder_prompts.items()):
        by_pe: Dict[str, List[str]] = {}
        for prompt_en, pid in pairs:
            by_pe.setdefault(prompt_en, []).append(pid)
        new_pairs: Set[tuple] = set()
        for prompt_en, pids in by_pe.items():
            uniq = sorted(set(pids), key=lambda x: (_pid_int(x), str(x)))
            if len(uniq) > 1:
                msg = f"duplicate prompt in folder={folder!r} prompt_en={prompt_en!r} ids={uniq}"
                if args.on_duplicate_prompt == "error":
                    errors.append("ambiguous: " + msg)
                else:
                    keep = uniq[0]  # lowest numeric id first
                    warnings.append(f"dedupe keep_lowest_id: {msg} -> using {keep!r}")
                    new_pairs.add((prompt_en, keep))
            else:
                new_pairs.add((prompt_en, uniq[0]))
        folder_prompts[folder] = new_pairs

    if errors:
        print("--- validation failed ---", file=sys.stderr)
        for line in errors:
            print(line, file=sys.stderr)
        sys.exit(1)

    for w in warnings:
        print(w, file=sys.stderr)

    created = 0
    skipped = 0

    for folder, pairs in folder_prompts.items():
        if not pairs:
            continue
        dest_dir = os.path.join(out_base, model, folder)
        if not args.dry_run:
            os.makedirs(dest_dir, exist_ok=True)

        for prompt_en, pid in sorted(pairs, key=lambda x: (x[0], x[1])):
            src_dir = os.path.join(infer_root, str(pid))
            for i in indices:
                src = os.path.join(src_dir, f"{i}.mp4")
                dst_name = f"{prompt_en}-{i}.mp4"
                dst = os.path.join(dest_dir, dst_name)
                if not os.path.isfile(src):
                    errors.append(f"missing source: {src}")
                    skipped += 1
                    continue
                if args.dry_run:
                    print(f"would {args.method}: {src} -> {dst}")
                    created += 1
                    continue
                if os.path.lexists(dst) or os.path.exists(dst):
                    if os.path.islink(dst) or os.path.isfile(dst):
                        try:
                            os.remove(dst)
                        except OSError as e:
                            errors.append(f"remove failed {dst}: {e}")
                            skipped += 1
                            continue
                try:
                    if args.method == "symlink":
                        os.symlink(src, dst)
                    else:
                        shutil.copy2(src, dst)
                except OSError as e:
                    errors.append(f"{args.method} failed {src} -> {dst}: {e}")
                    skipped += 1
                    continue
                created += 1

    print(f"created_or_would: {created} skipped_missing_or_failed: {skipped}")
    if errors:
        print("--- errors (first 30) ---", file=sys.stderr)
        for line in errors[:30]:
            print(line, file=sys.stderr)
        if len(errors) > 30:
            print(f"... and {len(errors) - 30} more", file=sys.stderr)
        if not args.dry_run and skipped:
            sys.exit(1)


if __name__ == "__main__":
    main()
