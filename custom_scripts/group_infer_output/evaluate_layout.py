"""
Folder layout aligned with repo root evaluate.sh / run_evaluate_bounds.sh.
Index i in parallel arrays: dimensions[i] -> folders[i].
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

# Same order as evaluate.sh
DIMENSIONS: Tuple[str, ...] = (
    "subject_consistency",
    "background_consistency",
    "aesthetic_quality",
    "imaging_quality",
    "object_class",
    "multiple_objects",
    "color",
    "spatial_relationship",
    "scene",
    "temporal_style",
    "overall_consistency",
    "human_action",
    "temporal_flickering",
    "motion_smoothness",
    "dynamic_degree",
    "appearance_style",
)

FOLDERS: Tuple[str, ...] = (
    "subject_consistency",
    "scene",
    "overall_consistency",
    "overall_consistency",
    "object_class",
    "multiple_objects",
    "color",
    "spatial_relationship",
    "scene",
    "temporal_style",
    "overall_consistency",
    "human_action",
    "temporal_flickering",
    "subject_consistency",
    "subject_consistency",
    "appearance_style",
)


def dimension_to_folder(dimension: str) -> str:
    for d, f in zip(DIMENSIONS, FOLDERS):
        if d == dimension:
            return f
    raise KeyError(f"unknown dimension: {dimension}")


def folder_to_dimensions(folder: str) -> List[str]:
    return [d for d, f in zip(DIMENSIONS, FOLDERS) if f == folder]


def unique_eval_folders() -> List[str]:
    seen: List[str] = []
    for f in FOLDERS:
        if f not in seen:
            seen.append(f)
    return seen


def folder_for_prompt_row(dimensions: Sequence[str]) -> Dict[str, str]:
    """Each evaluated dimension maps to one folder; same folder may repeat."""
    return {d: dimension_to_folder(d) for d in dimensions}
