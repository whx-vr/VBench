# Custom scoring (`custom_scripts/custom_scoring`)

This folder holds tooling that **re-aggregates** VBench `*_eval_results.json` (together with `*_full_info.json`) into per-dimension scalars, then applies the same **normalize → quality / semantic (or I2V) → total** pipeline as the official helpers under `scripts/`—with extra controls for **sample index range**, **external tie-break JSON**, **prompt subsampling**, and a fixed **random seed**.

## `cal_custom_score.py`

### What it does

1. Reads evaluation pairs: either `--pair FULL_INFO EVAL_RESULTS` or `--results_dir` (same pairing convention as `custom_scripts/bound/cal_bound_score.py`: `*_full_info.json` + `*_eval_results.json`).
2. For each dimension, walks every `full_info` row, maps each video path to a sample index from the basename (`…-{i}.mp4`), and aggregates scores across prompts according to your flags.
3. Feeds the resulting per-dimension raw scores into `scripts/cal_final_score.py` (T2V) or `scripts/cal_i2v_final_score.py` (I2V) logic and prints quality / semantic (or I2V) / total.

No zip submission is required.

### Main flags

| Flag | Role |
|------|------|
| `--pair` / `--results_dir` | Input JSON sources (one pair or a directory of pairs). |
| `--suite t2v` / `i2v` | Which normalization and quality split to use (default `t2v`). |
| `--index_lo`, `--index_hi` | Inclusive sample index filter; must pass **both** or **neither**. |
| `--tie_json PATH` | Optional JSON used only to **choose which sample index** wins per prompt (argmax of values in JSON within the index range); the **score** recorded is still from **eval** at that index. Ties are broken randomly; use `--seed`. |
| `--within_prompt_agg mean\|max\|min` | When **no** `--tie_json`: how to merge in-range videos inside one prompt (default `mean`). |
| `--prompt_sample_ratio` | In `(0,1]`: each dimension randomly keeps roughly this fraction of **prompts** (`full_info` rows). Subsampling RNG is **per dimension**, derived from `--seed`. |
| `--seed` | Controls tie-break randomness and prompt subsampling. |
| `--write_submission PATH` | Optional `{dim: [scalar, []]}` JSON (same shape as `cal_bound_score.py`). |

### Tie JSON key format

Outer keys must match **`full_info` rows**, not numeric dataset ids. Because VBench can repeat the same short `prompt_en` for different dimension groups, keys use:

```text
{prompt_en}|{dim_a},{dim_b},...
```

with dimensions sorted lexicographically (same rule as `custom_scripts/result_clean/convert_raw_rm_to_prompt_keys.py`).

Typical source for `--tie_json`: `resources/previous_rm_result/clean/ur.json` (or `vr.json` / `vs2.json`) after the `result_clean` pipeline below.

### Examples

```bash
# Single run, all samples, T2V totals
python3 custom_scripts/custom_scoring/cal_custom_score.py \
  --pair evaluation_results/run_full_info.json evaluation_results/run_eval_results.json

# Only samples 0–2; mean within each prompt
python3 custom_scripts/custom_scoring/cal_custom_score.py \
  --pair path/to/full_info.json path/to/eval_results.json \
  --index_lo 0 --index_hi 2

# Pick sample by external RM scores (UR clean JSON), reproducible ties
python3 custom_scripts/custom_scoring/cal_custom_score.py \
  --pair path/to/full_info.json path/to/eval_results.json \
  --index_lo 0 --index_hi 4 \
  --tie_json resources/previous_rm_result/clean/ur.json \
  --seed 42

# Subsample 30% of prompts per dimension (no tie JSON)
python3 custom_scripts/custom_scoring/cal_custom_score.py \
  --results_dir ./evaluation_results \
  --prompt_sample_ratio 0.3 \
  --seed 1
```

### Relation to other scripts

- **`scripts/cal_final_score.py`**: leaderboard-style totals from a **zipped** submission layout. Here we skip zip and build the per-dimension dict from eval JSON + aggregation rules above.
- **`custom_scripts/bound/cal_bound_score.py`**: per-prompt **max or min** over all samples, then mean. Here you get **index filtering**, optional **JSON-driven index choice**, **mean/max/min within prompt**, and **prompt subsampling**.

---

## RM clean data used with `--tie_json` (optional)

Under `custom_scripts/result_clean/`:

1. **`convert_raw_rm_to_prompt_keys.py`** — reads raw id-keyed dumps in `resource_dirty/previous_rm_result/raw/`, builds **clean float** maps (outer key = `prompt_en|sorted,dimensions`, inner `"0"`…`"4"`). Writes the **same** JSON to **`resources/previous_rm_result/prompt_idx/`** and **`resources/previous_rm_result/clean/`** (use `--no_clean` to only update `prompt_idx/`).
2. **`clean_ur.py` / `clean_vr.py` / `clean_vs2.py`** — refresh **one** modality from raw into `clean/` only (same logic as the converter; handy if you did not run the full convert).
3. **`run_all.sh`** — runs `convert_raw_rm_to_prompt_keys.py` only.

`--tie_json` can point at either directory; files are identical after a full convert.

### LRM timestep scores (optional)

If you have LRM outputs under `resource_dirty/lrm_result/single/<id>/result.json` (keys like `0.pt` … `4.pt`, inner keys = timestep strings such as `1`, `5`, `10`, …):

```bash
python3 custom_scripts/lrm_result/materialize_lrm_tie_jsons.py
```

This writes one file per timestep under `resources/lrm_result/` (default names `scores_t_<timestep>.json`), in the **same outer/inner key layout** as `previous_rm_result/prompt_idx/`, so each file can be passed directly to `cal_custom_score.py --tie_json`.

To merge timestep files that only contain sample indices `"0"`…`"4"` with a second reward dump keyed by `<id>/result.json` and `seed_5.pt`…`seed_9.pt` (indices 5–9), producing `"0"`…`"9"` for the **same outer keys**:

```bash
python3 custom_scripts/lrm_result/merge_lrm_extra_seed_jsons.py
```

Default output directory is `resources/lrm_n10_result/`. Pass that file via `--tie_json` together with **`--index_lo 0 --index_hi 9`** whenever your evaluation `full_info` lists ten videos per prompt.
