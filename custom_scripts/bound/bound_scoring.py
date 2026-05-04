"""
Re-aggregate VBench per-video scores into per-dimension scalars using
max/min within each prompt (from *_full_info.json), then mean across prompts.

This is a custom bound analysis; it does not match the official VBench
per-dimension aggregation in vbench.compute_*.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

BoundMode = Literal["max", "min"]


def normalize_path(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(os.path.expanduser(p))))


def _scalar_from_video_results(raw: Any) -> Optional[float]:
    """Map one entry's 'video_results' to a float for ordering."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return 1.0 if raw else 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, list):
        if not raw:
            return None
        try:
            return float(sum(raw) / len(raw))
        except (TypeError, ValueError):
            return None
    return None


def _video_dict_from_dimension_result(dim_result: Any) -> Tuple[Optional[float], Dict[str, float]]:
    """
    Parse one dimension's evaluate() return as stored in JSON (tuple -> list).
    Returns (official_scalar_or_none, path_norm -> per_video_scalar).
    """
    official: Optional[float] = None
    out: Dict[str, float] = {}
    if not isinstance(dim_result, (list, tuple)) or len(dim_result) < 2:
        return official, out
    head = dim_result[0]
    if isinstance(head, bool):
        official = 1.0 if head else 0.0
    elif isinstance(head, (int, float)):
        official = float(head)
    else:
        try:
            official = float(head)  # numpy scalar etc. from some json pipelines
        except (TypeError, ValueError):
            official = None
    per_video = dim_result[1]
    if not isinstance(per_video, list):
        return official, out
    for entry in per_video:
        if not isinstance(entry, dict):
            continue
        path = entry.get("video_path")
        if not path:
            continue
        s = _scalar_from_video_results(entry.get("video_results"))
        if s is None:
            capv = entry.get("cor_num_per_video")
            if isinstance(capv, bool):
                s = 1.0 if capv else 0.0
            elif isinstance(capv, (int, float)):
                s = float(capv)
        if s is None:
            continue
        out[normalize_path(str(path))] = s
    return official, out


def _pick_agg(mode: BoundMode) -> Callable[[List[float]], float]:
    if mode == "max":
        return max
    return min


def aggregate_one_dimension(
    full_info: List[dict],
    video_to_score: Dict[str, float],
    mode: BoundMode,
) -> Optional[float]:
    """
    For one dimension: for each prompt row in full_info, take max or min of
    per-video scores over that row's video_list; return mean across prompts
    that have at least one scored video.
    """
    pick = _pick_agg(mode)
    per_prompt_values: List[float] = []
    for row in full_info:
        if not isinstance(row, dict):
            continue
        vlist = row.get("video_list") or []
        if isinstance(vlist, str):
            vlist = [vlist]
        scores: List[float] = []
        for p in vlist:
            key = normalize_path(str(p))
            if key in video_to_score:
                scores.append(video_to_score[key])
        if not scores:
            continue
        per_prompt_values.append(pick(scores))
    if not per_prompt_values:
        return None
    return sum(per_prompt_values) / len(per_prompt_values)


def bound_scores_from_pair(
    full_info_path: str,
    eval_results_path: str,
    mode: BoundMode,
    *,
    fallback_official_scalar: bool = True,
) -> Dict[str, float]:
    """
    Return dimension_name (underscore) -> scalar for each dim in eval JSON.

    Primary: per-prompt max/min over per-video scores, then mean across prompts
    (see aggregate_one_dimension). When ``fallback_official_scalar`` is True and
    there are no usable per-video scores or aggregation yields nothing, fall back
    to the official aggregate ``dim_result[0]`` — same scalar as
    ``cal_final_score_from_eval_dir`` / ``cal_final_score.submission`` use, so
    missing dimensions are not silently scored as 0.0 due to path mismatch alone.
    """
    with open(full_info_path, "r", encoding="utf-8") as f:
        full_info = json.load(f)
    if not isinstance(full_info, list):
        raise ValueError(f"Expected list in full_info: {full_info_path}")
    with open(eval_results_path, "r", encoding="utf-8") as f:
        eval_results = json.load(f)
    if not isinstance(eval_results, dict):
        raise ValueError(f"Expected dict in eval_results: {eval_results_path}")

    out: Dict[str, float] = {}
    for dim_key, dim_result in eval_results.items():
        if not isinstance(dim_key, str):
            continue
        official, video_map = _video_dict_from_dimension_result(dim_result)
        agg: Optional[float] = None
        if video_map:
            agg = aggregate_one_dimension(full_info, video_map, mode)
        if agg is not None:
            out[dim_key] = agg
        elif fallback_official_scalar and official is not None:
            out[dim_key] = float(official)
    return out


def pair_paths_in_dir(results_dir: str) -> List[Tuple[str, str]]:
    """Match results_{name}_eval_results.json with results_{name}_full_info.json."""
    pairs: List[Tuple[str, str]] = []
    if not os.path.isdir(results_dir):
        return pairs
    suffix = "_eval_results.json"
    for name in os.listdir(results_dir):
        if not name.endswith(suffix):
            continue
        stem = name[: -len(suffix)]
        eval_path = os.path.join(results_dir, name)
        full_path = os.path.join(results_dir, f"{stem}_full_info.json")
        if os.path.isfile(full_path):
            pairs.append((full_path, eval_path))
    return pairs


def merge_bound_maps(maps: List[Dict[str, float]]) -> Dict[str, float]:
    """Later files overwrite same dimension keys (should be rare)."""
    merged: Dict[str, float] = {}
    for m in maps:
        merged.update(m)
    return merged
