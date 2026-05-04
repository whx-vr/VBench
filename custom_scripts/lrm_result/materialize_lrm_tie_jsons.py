#!/usr/bin/env python3
"""
Materialize LRM per-timestep score JSONs compatible with ``cal_custom_score.py --tie_json``.

Input layout::

  resource_dirty/lrm_result/single/<id>/result.json

Each ``result.json`` maps ``"<i>.pt"`` -> ``{ "<timestep>": score, ... }`` (timesteps are strings,
e.g. training steps 1, 5, 10, 25, 50).

Output (default ``resources/lrm_result/``)::

  scores_t_<timestep>.json

Each file has the same shape as ``resources/previous_rm_result/prompt_idx/*.json``::

  { "{prompt_en}|{dim,...}": { "0": float, "1": float, ... "4": float }, ... }

Row keys come from ``vbench/VBench_full_info.json`` at index ``<id>`` (same convention as
``convert_raw_rm_to_prompt_keys.py``). Optional align file validates ``prompt`` vs ``prompt_en``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RESULT_CLEAN = _REPO_ROOT / "custom_scripts" / "result_clean"
if str(_RESULT_CLEAN) not in sys.path:
    sys.path.insert(0, str(_RESULT_CLEAN))

from _prompt_rm_pipeline import load_align_prompts, row_outer_key  # noqa: E402

_PT_KEY_RE = re.compile(r"^(\d+)\.pt$")


def sample_index_from_pt_key(key: str) -> int:
    m = _PT_KEY_RE.match(key.strip())
    if not m:
        raise ValueError(f"expected key like '0.pt', got {key!r}")
    return int(m.group(1))


def collect_timesteps(single_root: Path) -> list[str]:
    ts: set[str] = set()
    for child in single_root.iterdir():
        if not child.is_dir() or not child.name.isdigit():
            continue
        rj = child / "result.json"
        if not rj.is_file():
            continue
        data = json.loads(rj.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data:
            continue
        first = next(iter(data.values()))
        if isinstance(first, dict):
            ts.update(first.keys())
    return sorted(ts, key=lambda s: int(s) if s.isdigit() else 0)


def safe_filename_timestep(ts: str) -> str:
    return ts.replace("/", "_").replace("\\", "_")


def build_one_timestep(
    single_root: Path,
    full_info: list,
    align_prompt: dict[str, str] | None,
    timestep: str,
    source_label: str,
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for child in sorted(single_root.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 10**9):
        if not child.is_dir() or not child.name.isdigit():
            continue
        sid = child.name
        idx = int(sid, 10)
        if idx < 0 or idx >= len(full_info):
            print(f"warning: {source_label}: skip id {sid} (full_info index out of range)", file=sys.stderr)
            continue
        row = full_info[idx]
        if not isinstance(row, dict):
            continue
        if align_prompt is not None:
            if sid not in align_prompt:
                raise KeyError(f"{source_label}: id {sid!r} not in align")
            if row.get("prompt_en", "").strip() != align_prompt[sid]:
                raise ValueError(
                    f"{source_label}: id {sid}: align prompt != full_info[{idx}].prompt_en "
                    f"({align_prompt[sid]!r} vs {row.get('prompt_en')!r})"
                )
        rpath = child / "result.json"
        if not rpath.is_file():
            print(f"warning: {source_label}: missing {rpath}", file=sys.stderr)
            continue
        data = json.loads(rpath.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        inner: dict[str, float] = {}
        ok = True
        for k in ("0.pt", "1.pt", "2.pt", "3.pt", "4.pt"):
            if k not in data:
                ok = False
                break
            per_ts = data[k]
            if not isinstance(per_ts, dict) or timestep not in per_ts:
                ok = False
                break
            inner[str(sample_index_from_pt_key(k))] = float(per_ts[timestep])
        if not ok:
            print(f"warning: {source_label}: id {sid} incomplete at timestep {timestep!r}", file=sys.stderr)
            continue
        key = row_outer_key(row)
        if key in out:
            raise ValueError(f"duplicate row key {key!r} at id {sid}")
        out[key] = inner
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="LRM single/result.json -> per-timestep tie JSONs.")
    ap.add_argument(
        "--single_root",
        type=Path,
        default=_REPO_ROOT / "resource_dirty/lrm_result/single",
    )
    ap.add_argument(
        "--vbench_full_info",
        type=Path,
        default=_REPO_ROOT / "vbench/VBench_full_info.json",
    )
    ap.add_argument(
        "--align",
        type=Path,
        default=_REPO_ROOT / "resources/vbench_prompt_align_gpt.json",
    )
    ap.add_argument(
        "--no_align_check",
        action="store_true",
        help="Skip align vs full_info prompt_en validation.",
    )
    ap.add_argument(
        "--out_dir",
        type=Path,
        default=_REPO_ROOT / "resources/lrm_result",
    )
    ap.add_argument(
        "--prefix",
        type=str,
        default="scores_t_",
        help="Output filename prefix before timestep (default: scores_t_ -> scores_t_10.json).",
    )
    args = ap.parse_args()

    full_info = json.loads(args.vbench_full_info.read_text(encoding="utf-8"))
    if not isinstance(full_info, list):
        print("error: full_info root must be a list", file=sys.stderr)
        return 1

    align_prompt: dict[str, str] | None = None
    if not args.no_align_check:
        align_prompt = load_align_prompts(args.align)

    timesteps = collect_timesteps(args.single_root)
    if not timesteps:
        print(f"error: no timesteps found under {args.single_root}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    label = args.single_root.name
    for ts in timesteps:
        blob = build_one_timestep(
            args.single_root,
            full_info,
            align_prompt,
            ts,
            source_label=label,
        )
        fn = f"{args.prefix}{safe_filename_timestep(ts)}.json"
        dst = args.out_dir / fn
        dst.write_text(json.dumps(blob, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(blob)} prompts → {dst}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
