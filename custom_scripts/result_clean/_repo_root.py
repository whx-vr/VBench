"""Resolve VBench repo root from this package location."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
