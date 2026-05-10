#!/usr/bin/env python3
"""
Merge two infer result trees into one output tree with the same relative layout.

Typical use:
  - group A: prompt-0..4.mp4
  - group B: prompt-5..9.mp4
After merge, run evaluate_custom.py once with --seed_start 0 --seed_end 9.
"""
from __future__ import annotations

import argparse
import os
import shutil
from typing import Dict, Iterable, List, Tuple

MEDIA_EXTS = {".mp4", ".gif", ".webm", ".avi", ".mov", ".mkv"}


def iter_media_files(root: str) -> Iterable[Tuple[str, str]]:
    """
    Yield (absolute_path, relative_path_from_root) for media files under root.
    Relative paths use os.sep of current platform.
    """
    root_abs = os.path.abspath(os.path.expanduser(root))
    for cur_dir, _, files in os.walk(root_abs):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in MEDIA_EXTS:
                continue
            abs_path = os.path.join(cur_dir, name)
            rel_path = os.path.relpath(abs_path, root_abs)
            yield abs_path, rel_path


def merge_two_groups(
    src_a: str,
    src_b: str,
    dst: str,
    *,
    method: str,
    overwrite: bool,
) -> Dict[str, int]:
    src_a = os.path.abspath(os.path.expanduser(src_a))
    src_b = os.path.abspath(os.path.expanduser(src_b))
    dst = os.path.abspath(os.path.expanduser(dst))
    os.makedirs(dst, exist_ok=True)

    files_a = list(iter_media_files(src_a))
    files_b = list(iter_media_files(src_b))

    rel_to_src: Dict[str, str] = {}
    conflicts: List[str] = []

    for abs_path, rel_path in files_a + files_b:
        if rel_path in rel_to_src and rel_to_src[rel_path] != abs_path:
            conflicts.append(rel_path)
        else:
            rel_to_src[rel_path] = abs_path

    if conflicts and not overwrite:
        preview = "\n".join(conflicts[:20])
        more = "" if len(conflicts) <= 20 else f"\n... and {len(conflicts) - 20} more"
        raise RuntimeError(
            "Found path conflicts between two groups. "
            "Use --overwrite to let later source replace earlier.\n"
            f"{preview}{more}"
        )

    # deterministic order
    merged_items = sorted(files_a + files_b, key=lambda x: x[1])
    created = 0
    replaced = 0
    skipped = 0

    for abs_path, rel_path in merged_items:
        dst_path = os.path.join(dst, rel_path)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)

        if os.path.lexists(dst_path):
            if not overwrite:
                skipped += 1
                continue
            os.remove(dst_path)
            replaced += 1

        if method == "symlink":
            os.symlink(abs_path, dst_path)
        else:
            shutil.copy2(abs_path, dst_path)
        created += 1

    return {
        "src_a_files": len(files_a),
        "src_b_files": len(files_b),
        "created": created,
        "replaced": replaced,
        "skipped": skipped,
        "conflicts_detected": len(conflicts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge two infer result directories into one tree."
    )
    parser.add_argument("--src_a", required=True, help="First infer root path")
    parser.add_argument("--src_b", required=True, help="Second infer root path")
    parser.add_argument("--out", required=True, help="Output merged root path")
    parser.add_argument(
        "--method",
        choices=("symlink", "copy"),
        default="symlink",
        help="How to materialize merged files in output path",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="If same relative path exists from both groups, keep later one",
    )
    args = parser.parse_args()

    stats = merge_two_groups(
        args.src_a, args.src_b, args.out, method=args.method, overwrite=args.overwrite
    )
    print("merge done:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

