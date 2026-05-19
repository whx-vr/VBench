#!/usr/bin/env python3
"""
Merge multiple infer video directories into one output tree.

Each --src is a directory whose layout is already:

  <src>/<prompt_id>/<seed-id>.mp4

e.g. videoa_b/42/0.mp4 and videoc_d/42/5.mp4 from different seed runs.

Merged output:

  <out>/<prompt_id>/<seed-id>.mp4
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import sys
from typing import Dict, Iterable, List, Tuple

MEDIA_EXTS = {".mp4", ".gif", ".webm", ".avi", ".mov", ".mkv"}


def iter_media_under_root(root: str) -> Iterable[Tuple[str, str]]:
    """Yield (absolute_path, rel_path) for media under root (prompt_id/seed.mp4)."""
    root = os.path.abspath(os.path.expanduser(root))
    for cur_dir, _, files in os.walk(root):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in MEDIA_EXTS:
                continue
            abs_path = os.path.join(cur_dir, name)
            rel_path = os.path.relpath(abs_path, root)
            yield abs_path, rel_path


def resolve_src_dirs(
    src_dirs: List[str] | None,
    *,
    src_parent: str | None,
    src_glob: str | None,
) -> List[str]:
    """Return absolute paths of source video directories to merge."""
    if src_dirs and src_parent:
        raise ValueError("Use either --src or --src-parent, not both")

    if src_parent:
        parent = os.path.abspath(os.path.expanduser(src_parent))
        if not os.path.isdir(parent):
            raise FileNotFoundError(f"not a directory: {parent}")
        pattern = src_glob or "*"
        found: List[str] = []
        for name in sorted(os.listdir(parent)):
            path = os.path.join(parent, name)
            if os.path.isdir(path) and fnmatch.fnmatch(name, pattern):
                found.append(path)
        if not found:
            raise RuntimeError(
                f"No subdirs matching {pattern!r} under {parent!r}"
            )
        return found

    if not src_dirs:
        raise ValueError("Provide --src and/or --src-parent")

    resolved: List[str] = []
    for src in src_dirs:
        path = os.path.abspath(os.path.expanduser(src))
        if not os.path.isdir(path):
            raise FileNotFoundError(f"not a directory: {path}")
        resolved.append(path)
    return resolved


def collect_from_sources(src_roots: List[str]) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    items: List[Tuple[str, str, str]] = []
    warnings: List[str] = []

    for src in src_roots:
        count = 0
        for abs_path, rel_path in iter_media_under_root(src):
            items.append((abs_path, rel_path, src))
            count += 1
        if count == 0:
            warnings.append(f"no media files under {src!r}")

    return items, warnings


def merge_sources(
    src_roots: List[str],
    dst: str,
    *,
    method: str,
    overwrite: bool,
    dry_run: bool,
) -> Dict[str, int]:
    out_root = os.path.abspath(os.path.expanduser(dst))

    items, warnings = collect_from_sources(src_roots)

    for w in warnings:
        print(w, file=sys.stderr)

    if not items:
        raise RuntimeError("No media files found. Check --src paths.")

    rel_to_item: Dict[str, Tuple[str, str]] = {}
    conflicts: List[str] = []

    for abs_path, rel_key, label in items:
        if rel_key in rel_to_item and rel_to_item[rel_key][0] != abs_path:
            conflicts.append(rel_key)
        rel_to_item[rel_key] = (abs_path, label)

    if conflicts and not overwrite:
        preview = "\n".join(conflicts[:20])
        more = "" if len(conflicts) <= 20 else f"\n... and {len(conflicts) - 20} more"
        raise RuntimeError(
            "Duplicate prompt_id/seed file across sources. "
            "Use --overwrite to keep the last source.\n"
            f"{preview}{more}"
        )

    if not dry_run:
        os.makedirs(out_root, exist_ok=True)

    created = 0
    replaced = 0
    skipped = 0

    for rel_key in sorted(rel_to_item.keys()):
        abs_path, _label = rel_to_item[rel_key]
        dst_path = os.path.join(out_root, rel_key)

        if dry_run:
            print(f"would {method}: {abs_path} -> {dst_path}")
            created += 1
            continue

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
        "src_dirs": len(src_roots),
        "source_files": len(items),
        "unique_keys": len(rel_to_item),
        "created": created,
        "replaced": replaced,
        "skipped": skipped,
        "conflicts_detected": len(conflicts),
        "warnings": len(warnings),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Merge <src>/prompt_id/seed-id.mp4 from multiple video dirs "
            "(e.g. videoa_b, videoc_d) into one output dir."
        )
    )
    parser.add_argument(
        "--src",
        nargs="*",
        default=[],
        help="Video dirs to merge, each already prompt_id/seed-id.mp4",
    )
    parser.add_argument(
        "--src-parent",
        help="Parent dir; merge all immediate subdirs matching --src-glob",
    )
    parser.add_argument(
        "--src-glob",
        default="*",
        help="fnmatch for subdir names under --src-parent (default: *)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory: {out}/prompt_id/seed-id.mp4",
    )
    parser.add_argument(
        "--method",
        choices=("symlink", "copy"),
        default="symlink",
        help="How to materialize merged files (default: symlink)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="If the same prompt_id/seed file exists in multiple sources, keep the last",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned operations without writing",
    )
    args = parser.parse_args()

    src_roots = resolve_src_dirs(
        args.src or None,
        src_parent=args.src_parent,
        src_glob=args.src_glob,
    )

    stats = merge_sources(
        src_roots,
        args.out,
        method=args.method,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    print("merge done:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
