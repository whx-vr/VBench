#!/usr/bin/env python3
"""
Merge multiple infer result roots into one combined videos tree.

Each source root is expected to contain one or more top-level directories named
like ``videos*`` (default: any name starting with ``videos``). Under each:

  videos*/<prompt_id>/<seed-id>.mp4

All files are merged into:

  <out>/<out_videos_dir>/<prompt_id>/<seed-id>.mp4

Typical use: several runs with different random seeds, each holding a disjoint
subset of seed indices (e.g. 0–4 in one run, 5–9 in another).
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import sys
from typing import Dict, Iterable, List, Tuple

MEDIA_EXTS = {".mp4", ".gif", ".webm", ".avi", ".mov", ".mkv"}


def find_videos_dirs(infer_root: str, videos_glob: str) -> List[str]:
    """Top-level directories under infer_root matching videos_glob (fnmatch)."""
    infer_root = os.path.abspath(os.path.expanduser(infer_root))
    if not os.path.isdir(infer_root):
        raise FileNotFoundError(f"not a directory: {infer_root}")

    matches: List[str] = []
    for name in sorted(os.listdir(infer_root)):
        path = os.path.join(infer_root, name)
        if not os.path.isdir(path):
            continue
        if fnmatch.fnmatch(name, videos_glob):
            matches.append(path)
    return matches


def iter_media_under_videos_dir(videos_dir: str) -> Iterable[Tuple[str, str]]:
    """
    Yield (absolute_path, relative_path_under_videos_dir) for media files.
    e.g. videos_dir/prompt_1/0.mp4 -> rel_path prompt_1/0.mp4
    """
    videos_dir = os.path.abspath(videos_dir)
    for cur_dir, _, files in os.walk(videos_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in MEDIA_EXTS:
                continue
            abs_path = os.path.join(cur_dir, name)
            rel_path = os.path.relpath(abs_path, videos_dir)
            yield abs_path, rel_path


def collect_from_sources(
    src_roots: List[str],
    *,
    videos_glob: str,
) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """
    Walk all src roots. Return (items, warnings).

    Each item is (abs_path, rel_key, source_label) where rel_key is
    prompt_id/seed-id.mp4 shared across all videos* dirs.
    """
    items: List[Tuple[str, str, str]] = []
    warnings: List[str] = []

    for src in src_roots:
        src = os.path.abspath(os.path.expanduser(src))
        label = src
        videos_dirs = find_videos_dirs(src, videos_glob)
        if not videos_dirs:
            warnings.append(f"no videos* dirs under {src!r} (glob={videos_glob!r})")
            continue
        for vdir in videos_dirs:
            for abs_path, rel_path in iter_media_under_videos_dir(vdir):
                items.append((abs_path, rel_path, label))

    return items, warnings


def merge_sources(
    src_roots: List[str],
    dst: str,
    *,
    videos_glob: str,
    out_videos_dir: str,
    method: str,
    overwrite: bool,
    dry_run: bool,
) -> Dict[str, int]:
    dst = os.path.abspath(os.path.expanduser(dst))
    out_root = os.path.join(dst, out_videos_dir)

    items, warnings = collect_from_sources(src_roots, videos_glob=videos_glob)

    for w in warnings:
        print(w, file=sys.stderr)

    if not items:
        raise RuntimeError(
            "No media files found. Check --src paths and --videos-glob."
        )

    # rel_key -> (abs_path, source_label); detect conflicts
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
        "src_roots": len(src_roots),
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
            "Merge videos*/prompt_id/seed-id.mp4 from multiple infer roots "
            "into one output tree."
        )
    )
    parser.add_argument(
        "--src",
        nargs="+",
        required=True,
        help="One or more infer result root directories",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output infer root; merged tree is written to {out}/{out_videos_dir}/",
    )
    parser.add_argument(
        "--out-videos-dir",
        default="videos",
        help="Name of merged videos directory under --out (default: videos)",
    )
    parser.add_argument(
        "--videos-glob",
        default="videos*",
        help="fnmatch pattern for top-level videos dirs under each --src (default: videos*)",
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

    stats = merge_sources(
        args.src,
        args.out,
        videos_glob=args.videos_glob,
        out_videos_dir=args.out_videos_dir,
        method=args.method,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    print("merge done:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
