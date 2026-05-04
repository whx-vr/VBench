#!/usr/bin/env python3
"""
Aggregate VBench *_eval_results.json (+ *_full_info.json) into per-dimension scalars,
then apply the same normalization / quality / semantic / total pipeline as
scripts/cal_final_score.py (or I2V variant).

Compared to custom_scripts/bound/cal_bound_score.py:
- No zip input; use --pair or --results_dir like cal_bound_score.
- Optional sample index filter [index_lo, index_hi] (inclusive) on parsed ``-{i}.ext`` suffix.
- Optional tie-breaker JSON (prompt_en -> {"0": score, ...}): per prompt pick the sample
  index in-range with maximum *JSON* score; ties broken at random; reported dim score uses
  *eval* score at that index.
- Optional per-dimension prompt subsampling: only a fraction of prompts (rows in full_info)
  contribute, chosen with a RNG keyed by (seed, dimension). If a prompt is selected, all
  in-range samples still participate unless tie JSON forces a single index.
- --seed controls all stochastic parts (subsample + tie breaks).

Tie JSON outer keys match ``*_full_info.json`` rows: ``"{prompt_en}|{dim1},{dim2},..."`` with
dimensions sorted (same as ``convert_raw_rm_to_prompt_keys.py`` output under ``resources/previous_rm_result/prompt_idx/``).
When a row has no ``dimension`` list, the key is just ``prompt_en``. This disambiguates duplicate
captions across different VBench dimension groups.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import zlib
from typing import Any, Dict, List, Literal, Optional, Tuple

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
_BOUND_DIR = os.path.join(_REPO_ROOT, "custom_scripts", "bound")

for _p in (_SCRIPTS_DIR, _BOUND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bound_scoring import (  # noqa: E402
    _video_dict_from_dimension_result,
    normalize_path,
    pair_paths_in_dir,
)
from constant import I2VKEY, TASK_INFO, TASK_INFO_I2V  # noqa: E402

from cal_final_score import (  # noqa: E402
    get_final_score as get_final_score_t2v,
    get_nomalized_score as get_nomalized_score_t2v,
    get_quality_score,
    get_semantic_score,
)

from cal_i2v_final_score import (  # noqa: E402
    get_final_score as get_final_score_i2v,
    get_i2v_quality_score,
    get_i2v_score,
    get_nomalized_score as get_nomalized_score_i2v,
)

WithinAgg = Literal["mean", "max", "min"]


# Last ``-{digits}`` before extension, e.g. ``.../foo bar-3.mp4`` -> 3
_SAMPLE_INDEX_RE = re.compile(r"-(\d+)(\.[^.]+)$")


def sample_index_from_video_path(path: str) -> Optional[int]:
    base = os.path.basename(path)
    m = _SAMPLE_INDEX_RE.search(base)
    if not m:
        return None
    return int(m.group(1))


def _agg_list(xs: List[float], how: WithinAgg) -> float:
    if not xs:
        raise ValueError("empty score list")
    if how == "mean":
        return sum(xs) / len(xs)
    if how == "max":
        return max(xs)
    return min(xs)


def _parse_tie_json(path: str) -> Dict[str, Dict[str, float]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("tie JSON root must be an object")
    out: Dict[str, Dict[str, float]] = {}
    for pid, row in raw.items():
        if not isinstance(row, dict):
            raise ValueError(f"tie JSON[{pid!r}] must be an object")
        inner: Dict[str, float] = {}
        for k, v in row.items():
            inner[str(k).strip()] = float(v)
        out[str(pid).strip()] = inner
    return out


def _dimension_sig(dim: object) -> str:
    if not isinstance(dim, list) or not dim:
        return ""
    return ",".join(sorted(str(x) for x in dim))


def row_tie_key(row: dict) -> str:
    """Match tie JSON / prompt_idx keys (same rule as convert_raw_rm_to_prompt_keys.row_outer_key)."""
    pe = row.get("prompt_en")
    if not isinstance(pe, str) or not pe.strip():
        p2 = row.get("prompt")
        if isinstance(p2, str) and p2.strip():
            pe = p2
        else:
            raise ValueError(f"full_info row has no non-empty prompt_en / prompt: keys={list(row)!r}")
    pe = pe.strip()
    sig = _dimension_sig(row.get("dimension"))
    if sig:
        return f"{pe}|{sig}"
    return pe


def _dim_rng(seed: int, dim_key: str) -> random.Random:
    """Deterministic RNG stream per dimension for prompt subsampling."""
    h = zlib.adler32(dim_key.encode("utf-8")) & 0xFFFFFFFF
    return random.Random((seed + h) & 0xFFFFFFFF)


def _pick_tie_argmax(candidates: List[Tuple[int, float]], rng: random.Random) -> int:
    """candidates: (index, json_score); return chosen index."""
    best = max(s for _, s in candidates)
    tops = [i for i, s in candidates if s == best]
    return rng.choice(tops)


def aggregate_dimension(
    full_info: List[dict],
    video_to_score: Dict[str, float],
    *,
    index_lo: Optional[int],
    index_hi: Optional[int],
    tie_json: Optional[Dict[str, Dict[str, float]]],
    within_prompt_agg: WithinAgg,
    prompt_ratio: float,
    seed: int,
    dim_key: str,
) -> Tuple[Optional[float], Dict[str, int]]:
    """
    One dimension: per-prompt scalar (index filter / tie JSON / within-prompt agg),
    then mean across selected prompts.

    Returns (mean_or_none, stats) where stats counts skipped rows among chosen_rows.
    """
    if not (0.0 < prompt_ratio <= 1.0 + 1e-9):
        raise ValueError("prompt_sample_ratio must be in (0, 1]")

    n_rows = len(full_info)
    if n_rows == 0:
        return None, {"used_prompts": 0, "missing_tie_prompt": 0, "skipped_no_score": 0}

    if prompt_ratio < 1.0 - 1e-12:
        rng_dim = _dim_rng(seed, dim_key)
        k = max(1, min(n_rows, int(round(n_rows * prompt_ratio))))
        chosen_rows = set(rng_dim.sample(range(n_rows), k=k))
    else:
        chosen_rows = set(range(n_rows))

    rng_tie = _dim_rng(seed ^ 0xA5A5_A5A5, dim_key + ":tie")

    per_prompt_values: List[float] = []
    missing_tie_prompt = 0
    skipped_no_scores = 0

    for row_idx, row in enumerate(full_info):
        if row_idx not in chosen_rows:
            continue
        if not isinstance(row, dict):
            continue
        vlist = row.get("video_list") or []
        if isinstance(vlist, str):
            vlist = [vlist]

        idx_to_path: Dict[int, str] = {}
        for p in vlist:
            si = sample_index_from_video_path(str(p))
            if si is None:
                continue
            idx_to_path[si] = str(p)

        def in_range(i: int) -> bool:
            if index_lo is None and index_hi is None:
                return True
            assert index_lo is not None and index_hi is not None
            return index_lo <= i <= index_hi

        if tie_json is not None:
            try:
                pkey = row_tie_key(row)
            except ValueError:
                missing_tie_prompt += 1
                continue
            ref = tie_json.get(pkey)
            if ref is None:
                missing_tie_prompt += 1
                continue
            candidates: List[Tuple[int, float]] = []
            for si, path in idx_to_path.items():
                if not in_range(si):
                    continue
                key = str(si)
                if key not in ref:
                    continue
                np = normalize_path(path)
                if np not in video_to_score:
                    continue
                candidates.append((si, ref[key]))
            if not candidates:
                skipped_no_scores += 1
                continue
            pick_si = _pick_tie_argmax(candidates, rng_tie)
            path = idx_to_path[pick_si]
            np = normalize_path(path)
            if np not in video_to_score:
                skipped_no_scores += 1
                continue
            per_prompt_values.append(float(video_to_score[np]))
        else:
            scalars: List[float] = []
            for si, path in idx_to_path.items():
                if not in_range(si):
                    continue
                np = normalize_path(path)
                if np not in video_to_score:
                    continue
                scalars.append(float(video_to_score[np]))
            if not scalars:
                skipped_no_scores += 1
                continue
            per_prompt_values.append(_agg_list(scalars, within_prompt_agg))

    stats = {
        "used_prompts": len(per_prompt_values),
        "missing_tie_prompt": missing_tie_prompt,
        "skipped_no_score": skipped_no_scores,
    }
    if not per_prompt_values:
        return None, stats
    return sum(per_prompt_values) / len(per_prompt_values), stats


def scores_from_pair(
    full_info_path: str,
    eval_results_path: str,
    *,
    index_lo: Optional[int],
    index_hi: Optional[int],
    tie_json: Optional[Dict[str, Dict[str, float]]],
    within_prompt_agg: WithinAgg,
    prompt_ratio: float,
    seed: int,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    with open(full_info_path, "r", encoding="utf-8") as f:
        full_info = json.load(f)
    if not isinstance(full_info, list):
        raise ValueError(f"full_info must be a list: {full_info_path}")
    with open(eval_results_path, "r", encoding="utf-8") as f:
        eval_results = json.load(f)
    if not isinstance(eval_results, dict):
        raise ValueError(f"eval_results must be a dict: {eval_results_path}")

    out: Dict[str, float] = {}
    meta_per_dim: Dict[str, Any] = {}

    for dim_key, dim_result in eval_results.items():
        if not isinstance(dim_key, str):
            continue
        _, video_map = _video_dict_from_dimension_result(dim_result)
        if not video_map:
            continue
        agg, stats = aggregate_dimension(
            full_info,
            video_map,
            index_lo=index_lo,
            index_hi=index_hi,
            tie_json=tie_json,
            within_prompt_agg=within_prompt_agg,
            prompt_ratio=prompt_ratio,
            seed=seed,
            dim_key=dim_key,
        )
        if agg is None:
            continue
        out[dim_key] = agg
        meta_per_dim[dim_key] = stats
    return out, {"dims": meta_per_dim}


def merge_dim_maps(maps: List[Dict[str, float]]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    for m in maps:
        merged.update(m)
    return merged


def upload_dict_from_dim_scores_t2v(dim_scores: Dict[str, float]) -> Dict[str, float]:
    upload: Dict[str, float] = {}
    for key in TASK_INFO:
        under = key.replace(" ", "_")
        upload[key] = float(dim_scores.get(under, 0.0))
    return upload


def upload_dict_from_dim_scores_i2v(dim_scores: Dict[str, float]) -> Dict[str, float]:
    """Map eval_result dimension keys (e.g. subject_consistency) via I2VKEY to TASK_INFO_I2V names."""
    upload: Dict[str, float] = {}
    for task_key in TASK_INFO_I2V:
        eval_keys = [j for j, v in I2VKEY.items() if v == task_key]
        if not eval_keys:
            upload[task_key] = 0.0
        else:
            upload[task_key] = float(dim_scores.get(eval_keys[0], 0.0))
    return upload


def write_submission_json(path: str, dim_scores: Dict[str, float]) -> None:
    payload = {}
    for k, v in dim_scores.items():
        payload[k] = [float(v), []]
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="VBench-style totals from eval JSON + full_info with index / tie-json / prompt sampling options."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--results_dir",
        type=str,
        help="Directory with paired *_eval_results.json and *_full_info.json",
    )
    src.add_argument(
        "--pair",
        nargs=2,
        metavar=("FULL_INFO", "EVAL_RESULTS"),
        help="Single full_info.json and eval_results.json",
    )
    ap.add_argument(
        "--suite",
        choices=("t2v", "i2v"),
        default="t2v",
        help="Which normalization / quality split to use (default: t2v like cal_final_score.py).",
    )
    ap.add_argument(
        "--index_lo",
        type=int,
        default=None,
        help="Inclusive low sample index (must be used with --index_hi). Parsed from video basename …-{i}.mp4",
    )
    ap.add_argument(
        "--index_hi",
        type=int,
        default=None,
        help="Inclusive high sample index (must be used with --index_lo).",
    )
    ap.add_argument(
        "--tie_json",
        type=str,
        default="",
        help='Optional tie JSON: keys = full_info row keys (prompt_en|dim1,dim2,...); argmax tie-break; dim uses eval at chosen index.',
    )
    ap.add_argument(
        "--within_prompt_agg",
        choices=("mean", "max", "min"),
        default="mean",
        help="When no --tie_json: how to combine in-range per-video scores within one prompt (default: mean).",
    )
    ap.add_argument(
        "--prompt_sample_ratio",
        type=float,
        default=1.0,
        help="Fraction of prompts (full_info rows) to include per dimension in (0,1]; 1.0 = all (default).",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed for tie breaks and prompt subsampling.",
    )
    ap.add_argument(
        "--write_submission",
        type=str,
        default="",
        help="Optional path to write {dim: [scalar, []]} JSON.",
    )
    args = ap.parse_args()

    if (args.index_lo is None) ^ (args.index_hi is None):
        print("error: provide both --index_lo and --index_hi, or neither", file=sys.stderr)
        return 2
    index_lo = args.index_lo
    index_hi = args.index_hi

    tie: Optional[Dict[str, Dict[str, float]]] = None
    if args.tie_json:
        tie = _parse_tie_json(args.tie_json)

    if args.pair:
        pairs = [(args.pair[0], args.pair[1])]
    else:
        pairs = pair_paths_in_dir(args.results_dir)
        if not pairs:
            print(f"error: no paired JSON under {args.results_dir!r}", file=sys.stderr)
            return 1
        pairs = sorted(pairs)

    maps: List[Dict[str, float]] = []
    for fp, ep in pairs:
        m, _ = scores_from_pair(
            fp,
            ep,
            index_lo=index_lo,
            index_hi=index_hi,
            tie_json=tie,
            within_prompt_agg=args.within_prompt_agg,  # type: ignore[arg-type]
            prompt_ratio=args.prompt_sample_ratio,
            seed=args.seed,
        )
        maps.append(m)
    merged = merge_dim_maps(maps)

    if args.suite == "t2v":
        upload = upload_dict_from_dim_scores_t2v(merged)
        normalized = get_nomalized_score_t2v(upload)
        q = get_quality_score(normalized)
        s = get_semantic_score(normalized)
        final = get_final_score_t2v(q, s)
        q_label, s_label = "quality score", "semantic score"
    else:
        upload = upload_dict_from_dim_scores_i2v(merged)
        normalized = get_nomalized_score_i2v(upload)  # type: ignore[misc]
        q = get_i2v_quality_score(normalized)  # type: ignore[misc]
        s = get_i2v_score(normalized)  # type: ignore[misc]
        final = get_final_score_i2v(q, s)  # type: ignore[misc]
        q_label, s_label = "quality score", "I2V score"

    print(f"suite: {args.suite}")
    print(f"pairs processed: {len(pairs)}")
    print(f"index range: {index_lo, index_hi}")
    print(f"tie_json: {args.tie_json or '(none)'}")
    print(f"within_prompt_agg: {args.within_prompt_agg}")
    print(f"prompt_sample_ratio: {args.prompt_sample_ratio}")
    print(f"seed: {args.seed}")
    print(f"dimensions with non-zero re-aggregated raw scores: {len(merged)}")
    print("+------------------|------------------+")
    print(f"|     {q_label:14}|{q}|")
    print(f"|    {s_label:14}|{s}|")
    print(f"|       total score|{final}|")
    print("+------------------|------------------+")

    if args.write_submission:
        write_submission_json(args.write_submission, merged)
        print(f"wrote submission-style json: {args.write_submission}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
