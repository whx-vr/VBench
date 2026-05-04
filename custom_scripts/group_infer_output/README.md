# group_infer_output

将「按 prompt id 落盘」的推理结果，整理成与仓库根目录 `evaluate.sh`、`custom_scripts/bound/run_evaluate_bounds.sh` 兼容的 **VBench 标准目录与文件名**（`vbench_standard`：`{prompt_en}-{0..4}.mp4`，且子目录与 `evaluate.sh` 中的 `dimensions` / `folders` 映射一致）。

## 背景约定

- **推理输入**：`resources/prompt_map_vbench_gpt.json`（id → `prompt`、`prompt_en` 等）。
- **推理目录**：`{infer_root}/{id}/0.mp4` … `{id}/4.mp4`（默认五个样本）。
- **对齐规则**：用 map 里的 **`prompt` 字段** 与 `vbench/VBench_full_info.json` 中的 **`prompt_en`** 做**完全一致**匹配，得到该 id 对应的官方句子与 `dimension` 列表（若 full_info 中同句多行，会合并维度并集）。
- **输出布局**：`{out_base}/{model}/{folder}/{prompt_en}-{i}.mp4`；`folder` 与根目录 `evaluate.sh` 中「维度 → 子目录」一致（见 `evaluate_layout.py`）。

## 文件说明

| 文件 | 说明 |
|------|------|
| `evaluate_layout.py` | 与 `evaluate.sh` 对齐的 `dimension → folder` 及反向查询（某 folder 服务哪些维度）。 |
| `map_infer_ids.py` | 生成 id → `prompt_en_vbench`、`dimensions` 等汇总 JSON（含 `unmatched`、`collisions`）。 |
| `materialize_eval_layout.py` | 从 `{infer_root}/{id}/{i}.mp4` 复制或软链到上述 VBench 布局。 |
| `run_prepare.sh` | 依次调用上述两步的示例脚本。 |

## 使用方法

### 1. 生成 id 与维度的映射表

```bash
# 在仓库根目录执行
python3 custom_scripts/group_infer_output/map_infer_ids.py \
  -o custom_scripts/group_infer_output/id_dimensions.json
```

可选参数：

- `--prompt-map`：默认 `resources/prompt_map_vbench_gpt.json`
- `--full-info`：默认 `vbench/VBench_full_info.json`

输出 JSON 含 `entries`、`unmatched`（`prompt` 在 full_info 中找不到同句）、`collisions`（同句在 full_info 多行已合并维度）、`stats`。

### 2. 铺平为 VBench 评测目录

```bash
python3 custom_scripts/group_infer_output/materialize_eval_layout.py \
  --mapping custom_scripts/group_infer_output/id_dimensions.json \
  --infer-root /你的/infer根目录 \
  --out-base ./vbench_videos \
  --model 你的模型名 \
  --method symlink \
  --on-duplicate-prompt keep_lowest_id
```

常用参数：

- `--method`：`symlink`（默认）或 `copy`。
- `--indices`：默认 `0,1,2,3,4`，对应源文件 `{i}.mp4`。
- `--dry-run`：只打印将要创建的路径，不写盘。
- `--on-duplicate-prompt`：不同 id 共用同一 `prompt`、目标文件名会冲突时，`error`（默认）直接失败；`keep_lowest_id` 在同一 folder 下对同一 `prompt_en` 只保留**数值最小**的 id。

### 3. 一键示例

```bash
bash custom_scripts/group_infer_output/run_prepare.sh /path/to/infer_root 模型名 [out_base] [mapping.json路径]
```

默认 `out_base` 为仓库下 `./vbench_videos`，默认 mapping 为 `custom_scripts/group_infer_output/id_dimensions.json`。

完成后可用根目录 `evaluate.sh` 或 `custom_scripts/bound/run_evaluate_bounds.sh` 指向同一 `{out_base}/{model}/...` 做评测。

## 注意事项

- 若 `prompt` 与官方 `prompt_en` 不完全一致，该 id 会进入 `unmatched`，不会生成目标文件。
- 软链在移动或删除 infer 原文件后会影响评测目录；需要自包含快照请用 `--method copy`。
