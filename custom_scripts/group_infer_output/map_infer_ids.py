#!/usr/bin/env python3
"""
Build id -> VBench prompt_en + dimensions by matching the align map's
``prompt`` field to VBench_full_info.json ``prompt_en`` (exact string match).

Default align file: resources/vbench_prompt_align_gpt.json
If multiple full_info rows share the same prompt_en, dimension lists are merged.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Set


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_dimensions(rows: List[dict]) -> List[str]:
    s: Set[str] = set()
    for r in rows:
        for d in r.get("dimension") or []:
            s.add(str(d))
    return sorted(s)


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="Map infer prompt ids to VBench dimensions")
    parser.add_argument(
        "--prompt-map",
        default=os.path.join(root, "resources", "vbench_prompt_align_gpt.json"),
        help="Align JSON: id -> {prompt, prompt_en, ...} (prompt must match full_info prompt_en)",
    )
    parser.add_argument(
        "--full-info",
        default=os.path.join(root, "vbench", "VBench_full_info.json"),
        help="VBench full_info list JSON",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output JSON path (id table + unmatched + collisions)",
    )
    args = parser.parse_args()

    prompt_map: Dict[str, Any] = load_json(args.prompt_map)
    full_info: List[dict] = load_json(args.full_info)
    if not isinstance(full_info, list):
        raise SystemExit("--full-info must be a JSON list")

    # prompt_en -> list of rows (for collision detection)
    by_pe: Dict[str, List[dict]] = {}
    for row in full_info:
        if not isinstance(row, dict):
            continue
        pe = row.get("prompt_en")
        if pe is None:
            continue
        by_pe.setdefault(str(pe), []).append(row)

    entries: Dict[str, Any] = {}
    unmatched: List[Dict[str, Any]] = []
    collisions: List[Dict[str, Any]] = []

    def _pid_sort_key(item: tuple) -> tuple:
        pid = item[0]
        try:
            return (0, int(str(pid)))
        except ValueError:
            return (1, str(pid))

    for pid, meta in sorted(prompt_map.items(), key=_pid_sort_key):
        if not isinstance(meta, dict):
            continue
        prompt_key = meta.get("prompt")
        if prompt_key is None or str(prompt_key).strip() == "":
            unmatched.append({"id": pid, "reason": "missing_or_empty_prompt_field"})
            continue
        prompt_key = str(prompt_key)
        rows = by_pe.get(prompt_key, [])
        if not rows:
            unmatched.append({"id": pid, "prompt": prompt_key, "reason": "no_VBench_full_info_row_with_same_prompt_en"})
            continue

        if len(rows) > 1:
            collisions.append(
                {
                    "id": pid,
                    "prompt": prompt_key,
                    "num_rows": len(rows),
                    "note": "merged_dimensions_union",
                }
            )

        dims = merge_dimensions(rows)
        canonical = rows[0].get("prompt_en")
        canonical = str(canonical) if canonical is not None else prompt_key

        entries[str(pid)] = {
            "prompt": prompt_key,
            "prompt_en_vbench": canonical,
            "dimensions": dims,
            "num_full_info_rows": len(rows),
        }

    out = {
        "meta": {
            "prompt_map": os.path.abspath(args.prompt_map),
            "full_info": os.path.abspath(args.full_info),
            "match_key": 'prompt_map["prompt"] == full_info["prompt_en"]',
        },
        "entries": entries,
        "stats": {
            "num_ids_in_prompt_map": len([k for k in prompt_map if isinstance(prompt_map[k], dict)]),
            "num_matched": len(entries),
            "num_unmatched": len(unmatched),
            "num_collision_ids": len(collisions),
        },
        "unmatched": unmatched,
        "collisions": collisions,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(json.dumps(out["stats"], indent=2))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
