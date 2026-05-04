# bound

在 **VBench 官方每维标量**之外，提供一种「按 prompt 在多样本里取最好/最差」的 **上界 / 下界** 重聚合，并用与排行榜一致的 **归一化与 Quality / Semantic / Total** 公式打分（见 `scripts/constant.py` 与 `scripts/cal_final_score.py`）。

**说明**：该标量**不是**官方 `compute_*` 里对多视频/多帧的池化方式；同一维度的 `[0]` 与逐视频列表 `[1]` 的算术关系因维度而异。本工具仅用于「若每个 prompt 只上报最好/最差一条样本」时的对比分析。

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
```

可选 `--write_submission ./bound_max.json`：写出 `{ "subject_consistency": [标量, []], ... }`，便于再打包 zip 用 `scripts/cal_final_score.py` 核对格式。

## 注意事项

- `--results_dir` 会合并目录下**所有**成对文件；请避免把不相关评测混在同一目录导致维度被错误覆盖。
- 与官方总分不一致是预期行为；对比时请标明使用的是 **bound (max/min)** 聚合。
