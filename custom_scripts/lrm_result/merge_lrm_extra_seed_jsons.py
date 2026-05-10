#!/usr/bin/env python3
"""
Merge existing LRM timestep tie JSONs (samples 0–4 only) with a second folder of
``<id>/result.json`` that uses ``seed_{i}.pt`` keys (e.g. i=5..9).

Output matches the same shape as ``resources/lrm_result/scores_t_*.json`` but with
inner keys ``"0"``..``"9"`` (or base keys + whichever extra seed indices appear).

Designed for::

  resources/lrm_result/scores_t_{t}.json
  resource_dirty/LRM_wan13_extra5_score/score/<id>/result.json

Requires ``row_outer_key`` alignment with ``vbench/VBench_full_info.json[row id]``.
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

_SEED_PT_RE = re.compile(r"^seed_(\d+)\.pt$", re.I)


def sample_index_from_seed_key(key: str) -> int:
    m = _SEED_PT_RE.match(key.strip())
    if not m:
        raise ValueError(f"expected key like 'seed_5.pt', got {key!r}")
    return int(m.group(1))


def collect_extra_timesteps(score_root: Path) -> list[str]:
    ts: set[str] = set()
    for child in score_root.iterdir():
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
    return sorted(ts, key=lambda s: int(s) if str(s).isdigit() else 0)


def load_base(path: Path) -> dict[str, dict[str, float]]:
    blob = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(blob, dict):
        raise ValueError(f"{path}: root must be object")
    return {str(k): {str(i): float(v) for i, v in dict(v).items()} for k, v in blob.items()}


def merge_one_timestep(
    base: dict[str, dict[str, float]],
    full_info: list,
    score_root: Path,
    timestep: str,
    align_prompt: dict[str, str] | None,
    label: str,
) -> tuple[dict[str, dict[str, float]], list[str]]:
    warnings: list[str] = []
    out: dict[str, dict[str, float]] = {}
    missing_base = 0
    skipped_incomplete = 0

    for child in sorted(score_root.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 10**9):
        if not child.is_dir() or not child.name.isdigit():
            continue
        sid = child.name
        idx = int(sid, 10)
        if idx < 0 or idx >= len(full_info):
            warnings.append(f"{label}: skip id {sid} (full_info index out of range)")
            continue
        row = full_info[idx]
        if not isinstance(row, dict):
            continue
        if align_prompt is not None:
            if sid not in align_prompt:
                raise KeyError(f"{label}: id {sid!r} not in align JSON")
            if row.get("prompt_en", "").strip() != align_prompt[sid]:
                raise ValueError(
                    f"{label}: id {sid}: align prompt != full_info[{idx}].prompt_en "
                    f"({align_prompt[sid]!r} vs {row.get('prompt_en')!r})"
                )
        key = row_outer_key(row)
        if key not in base:
            missing_base += 1
            continue
        inner_base = dict(base[key])

        rpath = child / "result.json"
        if not rpath.is_file():
            warnings.append(f"{label}: missing {rpath}")
            skipped_incomplete += 1
            continue
        raw = json.loads(rpath.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue

        extras: dict[str, float] = {}
        ok = True
        for hk, hv in sorted(raw.items(), key=lambda x: sample_index_from_seed_key(x[0])):
            try:
                si = sample_index_from_seed_key(hk)
            except ValueError:
                continue
            if not isinstance(hv, dict) or timestep not in hv:
                ok = False
                break
            extras[str(si)] = float(hv[timestep])

        if not ok or not extras:
            skipped_incomplete += 1
            continue

        overlap = set(inner_base.keys()) & set(extras.keys())
        if overlap:
            raise ValueError(
                f"id {sid} key={key[:60]!r}... extra seeds overlap base indices {sorted(overlap)}"
            )
        merged = {**inner_base, **extras}
        out[key] = merged

    # Deterministic numeric key order inside each prompt
    for k in list(out.keys()):
        mk = out[k]
        ordered = {str(i): mk[str(i)] for i in sorted(int(x) for x in mk)}
        out[k] = ordered

    expected = len(base)
    got = len(out)
    if got != expected:
        warnings.append(
            f"{label} timestep={timestep!r}: merged {got}/{expected} prompts "
            f"(missing_base={missing_base}, skipped_incomplete={skipped_incomplete})"
        )
    return out, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge LRM scores_t_*.json (0–4) with seed_5.pt… extra folder.")
    ap.add_argument(
        "--lrm_dir",
        type=Path,
        default=_REPO_ROOT / "resources/lrm_result",
        help="Directory with scores_t_<timestep>.json (0–4).",
    )
    ap.add_argument(
        "--extra_score_root",
        type=Path,
        default=_REPO_ROOT / "resource_dirty/LRM_wan13_extra5_score/score",
        help="Directory with numeric <id>/result.json using seed_<i>.pt keys.",
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
    )
    ap.add_argument(
        "--out_dir",
        type=Path,
        default=_REPO_ROOT / "resources/lrm_n10_result",
    )
    ap.add_argument(
        "--prefix",
        type=str,
        default="scores_t_",
    )
    args = ap.parse_args()

    full_info = json.loads(args.vbench_full_info.read_text(encoding="utf-8"))
    if not isinstance(full_info, list):
        print("error: full_info must be a list", file=sys.stderr)
        return 1

    align: dict[str, str] | None = None
    if not args.no_align_check:
        align = load_align_prompts(args.align)

    ts_base = []
    for p in sorted(args.lrm_dir.glob(f"{args.prefix}*.json")):
        stem = p.stem
        suf = stem[len(args.prefix) :] if stem.startswith(args.prefix) else ""
        if suf:
            ts_base.append(suf)

    ts_extra = collect_extra_timesteps(args.extra_score_root)
    if not ts_extra:
        print(f"error: no timesteps under {args.extra_score_root}", file=sys.stderr)
        return 1

    ts_set_extra = set(ts_extra)
    timesteps_use = [t for t in ts_base if t in ts_set_extra]
    if not timesteps_use:
        print(
            "error: no timestep overlap between "
            f"{args.lrm_dir}/{args.prefix}*.json ({ts_base}) and extra ({ts_extra})",
            file=sys.stderr,
        )
        return 1
    missing_from_extra = sorted(set(ts_base) - ts_set_extra)
    if missing_from_extra:
        print(f"warn: skipping lrm-only timesteps (not in extra): {missing_from_extra}", file=sys.stderr)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    label = args.extra_score_root.name

    total_warn = 0
    for ts in timesteps_use:
        base_path = args.lrm_dir / f"{args.prefix}{ts}.json"
        if not base_path.is_file():
            print(f"warn: skip missing base {base_path}", file=sys.stderr)
            continue
        base_scores = load_base(base_path)
        merged, warns = merge_one_timestep(
            base_scores,
            full_info,
            args.extra_score_root,
            timestep=str(ts),
            align_prompt=align,
            label=label,
        )
        for w in warns:
            print(w, file=sys.stderr)
            total_warn += 1
        dst = args.out_dir / f"{args.prefix}{ts}.json"
        dst.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        n_keys = len(merged)
        sample = next(iter(merged.values()))
        idxs = list(sample.keys())
        print(f"Wrote {n_keys} prompts ({len(idxs)} sample indices each) → {dst}")

    if total_warn:
        print(f"done with {total_warn} warning lines", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
