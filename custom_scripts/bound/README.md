# bound

在 **VBench 官方每维标量**之外，提供一种「按 prompt 在多样本里取最好/最差」的 **上界 / 下界** 重聚合，并用与排行榜一致的 **归一化与 Quality / Semantic / Total** 公式打分（见 `scripts/constant.py` 与 `scripts/cal_final_score.py`）。

**说明**：`--bound max|min` 下的重聚合**一般不等于**官方 `compute_*` 写在 `eval_results` 里的 `[0]`（例如 `dynamic_degree` 官方是全体样本上 bool 的均值，而「每 prompt 再 max 再对 prompt 平均」会得到另一套数）。因此与 `scripts/cal_final_score_from_eval_dir.py`（只读各 json 的 `[0]`）对比时，总分差异是**定义不同**导致的，不一定是实现 bug。

**与官方对齐的用法**：`cal_bound_score.py` 支持 **`--eval-scalars-only`**，行为与 `scripts/cal_final_score_from_eval_dir.py` 一致（合并目录下所有 `*_eval_results.json` 的 `[0]`，不读 `full_info`、不做 per-prompt max/min）。

**回退逻辑**：在 `--bound` 模式下，若某维没有可用的逐视频分或无法与 `full_info` 对齐，会自动使用该维 json 里的 **官方 `[0]`** 作为该维标量，避免整条维度被当成 0 拉崩总分（仅缓解路径/缺字段等问题；**不**改变「有 bound 时仍以 bound 为主」的语义）。

## 文件说明

| 文件 | 说明 |
|------|------|
| `bound_scoring.py` | 读 `*_full_info.json` + `*_eval_results.json`，按 prompt 对逐视频分做 max/min，再对 prompt 平均得到每维 bound 标量。 |
| `cal_bound_score.py` | CLI：单对 JSON 或整个 `evaluation_results` 目录下多对结果合并后，输出 Quality / Semantic / Total；可选写出与 `cal_final_score.py` 兼容的 submission 形 JSON。 |
| `run_evaluate_bounds.sh` | 与根目录 `evaluate.sh` 相同的 `dimensions`/`folders` 映射，调用 `evaluate.py` 跑一维后，对**当次**生成的 `*_full_info.json` / `*_eval_results.json` 打印 max / min bound。 |
| `run_bounds_on_dir.sh` | 对目录内所有成对的 `*_eval_results.json` + `*_full_info.json` 合并后各算一遍 max 与 min bound。 |

## 依赖关系

- 需先按仓库方式跑完 `evaluate.py`（或 `run_evaluate_bounds.sh`），得到带时间戳的 `results_*_full_info.json` 与 `results_*_eval_results.json`。
- `eval_results` 中每维一般为 `[官方标量, [ { "video_path", "video_results" }, ... ]]`；bound 逻辑使用第二段逐视频分与 full_info 里的 `video_list` 归组到同一 `prompt_en`。

## 使用方法

### 对整个 `evaluation_results` 目录算 bound

在完成各维度评测（目录内有多对同名 stem 的 full_info / eval_results）后：

```bash
bash custom_scripts/bound/run_bounds_on_dir.sh ./evaluation_results
```

会依次打印 **max**（每 prompt 取多样本中最高）与 **min**（每 prompt 取最低）下的 Quality / Semantic / Total。

### 单次评测后立即看 bound

与 `evaluate.sh` 一致：先给 **视频根**、**模型名**、**维度名**（脚本内部会解析到正确的子文件夹，见脚本内注释）。

```bash
bash custom_scripts/bound/run_evaluate_bounds.sh ./vbench_videos 模型名 aesthetic_quality
```

可选第 4 个参数：`evaluation_results` 输出目录（默认 `./evaluation_results`）。

### 仅对指定一对 JSON 算分

```bash
python3 custom_scripts/bound/cal_bound_score.py \
  --pair ./evaluation_results/results_时间_full_info.json \
         ./evaluation_results/results_时间_eval_results.json \
  --bound max

python3 custom_scripts/bound/cal_bound_score.py \
  --results_dir ./evaluation_results \
  --bound min

# 仅使用样本 index 0~2 参与 bound 聚合
python3 custom_scripts/bound/cal_bound_score.py \
  --results_dir ./evaluation_results \
  --bound max \
  --index_lo 0 --index_hi 2

# 与 cal_final_score_from_eval_dir 完全一致（只合并各维官方 [0]）
python3 custom_scripts/bound/cal_bound_score.py \
  --results_dir ./evaluation_results \
  --eval-scalars-only
```

可选 `--write_submission ./bound_max.json`：写出 `{ "subject_consistency": [标量, []], ... }`，便于再打包 zip 用 `scripts/cal_final_score.py` 核对格式。

## 注意事项

- `--results_dir` 会合并目录下**所有**成对文件；请避免把不相关评测混在同一目录导致维度被错误覆盖。
- 与官方总分不一致时：若要对齐 leaderboard 口径，请用 **`--eval-scalars-only`** 或直接用 `scripts/cal_final_score_from_eval_dir.py`。
- 使用 **`--bound`** 时请在报告里标明为 **bound 重聚合**；与官方 `[0]` 对比差异大时，先确认是否属于上面说的定义差异。
- `--index_lo/--index_hi` 仅在 `--bound` 下生效：按文件名结尾 `...-i.mp4` 过滤参与聚合的样本索引区间（闭区间）。
- **`imaging_quality`**：`eval_results` 里逐视频的 `video_results` 与 `vbench/imaging_quality.py` 一致，为 **MUSIQ 原始 0–100 分**；官方标量 `[0]` 在代码里会 `/100`。`bound_scoring` 已对逐视频分做 **`/100`** 再参与 max/min，避免与 `cal_final_score_from_eval_dir` 混用同一归一化区间时出现数量级错误。
