# eval_custom

`evaluate_custom.py` 是对仓库根目录 `evaluate.py` 的兼容扩展版，用于支持非默认样本索引区间（例如 `5-9`）。

官方 `vbench_standard` 流程默认按 `prompt-0..4` 找视频；本脚本新增 `--seed_start/--seed_end`，可改为按 `prompt-5..9`（或任意闭区间）匹配文件名。

## 适用场景

- 你有一批新结果，文件名是 `...-5.mp4` 到 `...-9.mp4`
- 希望继续使用 VBench 官方维度计算逻辑（`compute_*`），但不想重命名原视频
- 希望输出仍然是标准 `results_*_full_info.json` / `results_*_eval_results.json`

## 脚本位置

- `custom_scripts/eval_custom/evaluate_custom.py`

## 与原版差异

- 新增：
  - `--seed_start`（默认 `0`）
  - `--seed_end`（默认 `4`）
- 仅在 `--mode vbench_standard` 下启用区间匹配逻辑。
- `custom_input` / `vbench_category` 模式沿用原版 `VBench.evaluate(...)` 行为。

## 基本用法

### 评测默认区间（等价原版 0-4）

```bash
python3 custom_scripts/eval_custom/evaluate_custom.py \
  --videos_path /path/to/videos \
  --dimension subject_consistency
```

### 评测新批次（5-9）

```bash
python3 custom_scripts/eval_custom/evaluate_custom.py \
  --videos_path /path/to/videos \
  --dimension subject_consistency \
  --seed_start 5 \
  --seed_end 9 \
  --output_path ./evaluation_results_seed_5_9
```

### 一次跑多个维度

```bash
python3 custom_scripts/eval_custom/evaluate_custom.py \
  --videos_path /path/to/videos \
  --dimension subject_consistency motion_smoothness dynamic_degree \
  --seed_start 5 \
  --seed_end 9
```

## 参数说明（重点）

- `--videos_path`：待评测视频目录。
- `--dimension`：一个或多个维度名（和原版一致）。
- `--seed_start` / `--seed_end`：样本索引闭区间，按文件名 `...-{i}.mp4` 匹配。
- `--output_path`：输出目录（默认 `./evaluation_results/`）。
- `--full_json_dir`：VBench prompt/维度定义（默认 `vbench/VBench_full_info.json`）。

## 文件名约定

在 `vbench_standard` 下，脚本按如下模式查找视频：

- `{prompt}-{i}.mp4`（或目录中的实际后缀）
- 其中 `i` 来自 `seed_start..seed_end`

例如当区间为 `5..9` 时，期望存在：

- `a person swimming in ocean-5.mp4`
- ...
- `a person swimming in ocean-9.mp4`

## 输出

与原版一致：

- `results_<timestamp>_full_info.json`
- `results_<timestamp>_eval_results.json`

可直接配合你现有的打分脚本使用（如 `scripts/cal_final_score_from_eval_dir.py`、`custom_scripts/bound/cal_bound_score.py` 等）。

## 注意事项

- 若区间内某个样本文件缺失，脚本会打印 warning，并按现有样本继续计算。
- `--seed_start` 必须小于等于 `--seed_end`。
- 该脚本只解决“索引区间兼容”，不改变官方维度模型与分数定义。
