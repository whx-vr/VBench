"""
Shared logic: raw id-keyed RM dumps -> composite row key -> per-sample float scores.

Output shape matches resources/previous_rm_result/clean/*.json:

  { "{prompt_en}|{dim,...}": { "0": float, ... "4": float }, ... }
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Dict

RowCleaner = Callable[[dict], dict[str, float]]

FINAL_SCORE_RE = re.compile(
    r"Final\s+Score\s*:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
    re.IGNORECASE | re.MULTILINE,
)


def dimension_sig(dim: object) -> str:
    if not isinstance(dim, list) or not dim:
        return ""
    return ",".join(sorted(str(x) for x in dim))


def row_outer_key(row: dict) -> str:
    pe = row.get("prompt_en")
    if not isinstance(pe, str) or not pe.strip():
        p2 = row.get("prompt")
        if isinstance(p2, str) and p2.strip():
            pe = p2
        else:
            raise ValueError(f"row missing prompt_en / prompt: {row!r}")
    pe = pe.strip()
    sig = dimension_sig(row.get("dimension"))
    if sig:
        return f"{pe}|{sig}"
    return pe


def load_align_prompts(align_path: Path) -> dict[str, str]:
    raw = json.loads(align_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("align JSON root must be an object")
    out: dict[str, str] = {}
    for iid, obj in raw.items():
        if not isinstance(obj, dict):
            continue
        if "prompt" not in obj or obj["prompt"] is None:
            raise KeyError(f"align[{iid!r}] missing string field 'prompt'")
        out[str(iid)] = str(obj["prompt"]).strip()
    return out


def extract_final_score(text: str) -> float:
    m = FINAL_SCORE_RE.search(text)
    if not m:
        raise ValueError(f"No Final Score found in text: {text[:200]!r}...")
    return float(m.group(1))


def clean_ur_variants(variants: dict) -> dict[str, float]:
    row: dict[str, float] = {}
    for k in ("0", "1", "2", "3", "4"):
        if k not in variants:
            raise KeyError(f"missing variant {k}")
        v = variants[k]
        if isinstance(v, (int, float)):
            row[k] = float(v)
        elif isinstance(v, str):
            row[k] = extract_final_score(v)
        else:
            raise TypeError(f"variant {k}: expected str or number, got {type(v)}")
    return row


def _vr_overall_from_leaf(leaf: object) -> float:
    if isinstance(leaf, list):
        if not leaf:
            raise ValueError("empty list (expected at least one score dict)")
        first = leaf[0]
        if not isinstance(first, dict):
            raise TypeError(f"list[0] must be dict, got {type(first)}")
        if "Overall" not in first:
            raise KeyError(f"missing Overall in {first!r}")
        return float(first["Overall"])
    if isinstance(leaf, dict):
        if "Overall" in leaf:
            return float(leaf["Overall"])
        raise KeyError(f"dict leaf missing Overall: {leaf!r}")
    raise TypeError(f"unexpected leaf type {type(leaf)}")


def clean_vr_variants(variants: dict) -> dict[str, float]:
    row: dict[str, float] = {}
    for k in ("0", "1", "2", "3", "4"):
        if k not in variants:
            raise KeyError(f"missing variant {k}")
        row[k] = _vr_overall_from_leaf(variants[k])
    return row


def _vs2_overall_from_leaf(leaf: object) -> float:
    if not isinstance(leaf, dict):
        raise TypeError(f"expected dict leaf, got {type(leaf)}")
    for key in ("overall", "Overall"):
        if key in leaf:
            return float(leaf[key])
    raise KeyError(f"no overall/Overall in leaf keys: {list(leaf)}")


def clean_vs2_variants(variants: dict) -> dict[str, float]:
    row: dict[str, float] = {}
    for k in ("0", "1", "2", "3", "4"):
        if k not in variants:
            raise KeyError(f"missing variant {k}")
        row[k] = _vs2_overall_from_leaf(variants[k])
    return row


CLEANERS: Dict[str, RowCleaner] = {
    "ur.json": clean_ur_variants,
    "vr.json": clean_vr_variants,
    "vs2.json": clean_vs2_variants,
}


def rekey_raw_to_prompt_clean(
    raw: dict,
    *,
    full_info: list,
    align_prompt: dict[str, str],
    source_name: str,
    clean_variants: RowCleaner,
) -> dict[str, dict[str, float]]:
    """Map numeric id -> composite row key; replace raw leaves with float scores."""
    out: dict[str, dict[str, float]] = {}
    for iid, variants in raw.items():
        if not isinstance(variants, dict):
            raise TypeError(f"{source_name}: id {iid!r}: expected dict payload")
        sid = str(iid)
        if sid not in align_prompt:
            raise KeyError(f"{source_name}: id {sid!r} not in align")
        idx = int(sid, 10)
        if idx < 0 or idx >= len(full_info):
            raise IndexError(f"{source_name}: id {sid!r} out of range for full_info ({len(full_info)} rows)")
        row = full_info[idx]
        if not isinstance(row, dict):
            raise TypeError(f"full_info[{idx}] not an object")
        if row.get("prompt_en", "").strip() != align_prompt[sid]:
            raise ValueError(
                f"{source_name}: id {sid}: align prompt != full_info[{idx}].prompt_en "
                f"({align_prompt[sid]!r} vs {row.get('prompt_en')!r})"
            )
        key = row_outer_key(row)
        if key in out:
            raise ValueError(f"{source_name}: duplicate composite key {key!r}")
        out[key] = clean_variants(variants)
    return out
