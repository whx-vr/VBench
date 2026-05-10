#!/usr/bin/env python3
"""
Build mixed per-timestep tie JSON under resources/lrm_n10_new/.

Replacement is **per prompt**: all seed keys "0".. for that outer key come from another timestep file.

Outputs (default):

- scores_t_5.json  Base: scores_t_5; ~40% prompts fully replaced by scores_t_1.
- scores_t_10.json Base: scores_t_10; ~30% by scores_t_1 and ~30% by scores_t_50 on disjoint prompts.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_SRC = _REPO / "resources/lrm_n10_result"
_DEFAULT_OUT = _REPO / "resources/lrm_n10_new"


def _load(path: Path) -> dict[str, dict[str, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: root must be object")
    return {str(k): {str(i): float(v) for i, v in dict(v).items()} for k, v in data.items()}  # type: ignore[misc]


def _common_keys(files: dict[str, dict[str, dict[str, float]]]) -> list[str]:
    ks = None
    for name, blob in files.items():
        s = set(blob.keys())
        ks = s if ks is None else ks & s
    if not ks:
        raise SystemExit("no common outer keys across inputs")
    return sorted(ks)


def mix_step5(keys: list[str], t5: dict, t1: dict, pct_t1: float, rng: random.Random) -> dict[str, dict[str, float]]:
    n_t1 = min(len(keys), max(0, int(round(len(keys) * pct_t1))))
    shuffled = list(keys)
    rng.shuffle(shuffled)
    use_t1 = set(shuffled[:n_t1])
    out: dict[str, dict[str, float]] = {}
    for k in keys:
        if k in use_t1:
            out[k] = dict(t1[k])
        else:
            out[k] = dict(t5[k])
    return out


def mix_step10(
    keys: list[str],
    t10: dict,
    t1: dict,
    t50: dict,
    pct_t1: float,
    pct_t50: float,
    rng: random.Random,
) -> dict[str, dict[str, float]]:
    n_t1 = min(len(keys), max(0, int(round(len(keys) * pct_t1))))
    n_t50 = min(len(keys), max(0, int(round(len(keys) * pct_t50))))
    if n_t1 + n_t50 > len(keys):
        raise SystemExit(
            f"n_t1={n_t1} + n_t50={n_t50} exceeds prompt count {len(keys)} -> reduce fractions or overlaps"
        )
    shuffled = list(keys)
    rng.shuffle(shuffled)
    use_t1 = set(shuffled[:n_t1])
    use_t50 = set(shuffled[n_t1 : n_t1 + n_t50])
    out: dict[str, dict[str, float]] = {}
    for k in keys:
        if k in use_t1:
            out[k] = dict(t1[k])
        elif k in use_t50:
            out[k] = dict(t50[k])
        else:
            out[k] = dict(t10[k])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src_dir", type=Path, default=_DEFAULT_SRC)
    ap.add_argument("--out_dir", type=Path, default=_DEFAULT_OUT)
    ap.add_argument("--prefix", type=str, default="scores_t_")
    ap.add_argument("--seed", type=int, default=42, help="RNG for which prompts get replaced.")
    args = ap.parse_args()

    t1_path = args.src_dir / f"{args.prefix}1.json"
    t5_path = args.src_dir / f"{args.prefix}5.json"
    t10_path = args.src_dir / f"{args.prefix}10.json"
    t50_path = args.src_dir / f"{args.prefix}50.json"
    for p in (t1_path, t5_path, t10_path, t50_path):
        if not p.is_file():
            raise SystemExit(f"missing {p}")

    t1 = _load(t1_path)
    t5 = _load(t5_path)
    t10 = _load(t10_path)
    t50 = _load(t50_path)
    keys = _common_keys({"1": t1, "5": t5, "10": t10, "50": t50})
    n = len(keys)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    rng5 = random.Random(args.seed + 999)
    out5 = mix_step5(keys, t5=t5, t1=t1, pct_t1=0.40, rng=rng5)
    p5 = args.out_dir / f"{args.prefix}5.json"
    p5.write_text(json.dumps(out5, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    rng10 = random.Random(args.seed)
    out10 = mix_step10(keys, t10=t10, t1=t1, t50=t50, pct_t1=0.30, pct_t50=0.30, rng=rng10)
    p10 = args.out_dir / f"{args.prefix}10.json"
    p10.write_text(json.dumps(out10, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    n_rep5_t1 = int(round(n * 0.40))
    n_rep10_t1 = int(round(n * 0.30))
    n_rep10_t50 = int(round(n * 0.30))
    print(f"prompts common: {n}")
    print(
        f"Wrote {p5.relative_to(_REPO)} "
        f"(~{100 * n_rep5_t1 / max(n, 1):.1f}% from t=1 replacement, nominal 40%; seed={args.seed + 999})"
    )
    print(
        f"Wrote {p10.relative_to(_REPO)} "
        f"(~30% from t=1 + ~30% from t=50, disjoint + rest t=10; seed={args.seed})"
    )
    print(f"t1 keys used: exact counts {n_rep5_t1} (in t5 mix), disjoint in t10: {n_rep10_t1} + {n_rep10_t50} <= {n}")

    manifest = {
        "seed_step5_variant": args.seed + 999,
        "seed_step10_variant": args.seed,
        "common_prompt_keys_n": n,
        "scores_t_5": {"base": str(t5_path), "fraction_from_timestep_1": 0.40, "n_replaced_nominal": n_rep5_t1},
        "scores_t_10": {
            "base": str(t10_path),
            "fraction_from_timestep_1": 0.30,
            "fraction_from_timestep_50": 0.30,
            "n_from_1_nominal": n_rep10_t1,
            "n_from_50_nominal": n_rep10_t50,
            "remainder_timestep": 10,
        },
    }
    (args.out_dir / "mix_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
