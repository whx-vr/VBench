# group_infer_output

将「按 prompt id 落盘」的推理结果，整理成与仓库根目录 `evaluate.sh`、`custom_scripts/bound/run_evaluate_bounds.sh` 兼容的 **VBench 标准目录与文件名**（`vbench_standard`：`{prompt_en}-{0..4}.mp4`，且子目录与 `evaluate.sh` 中的 `dimensions` / `folders` 映射一致）。

## 背景约定

- **推理输入**：`resources/vbench_prompt_align_gpt.json`（id → 官方对齐短句 `prompt`、长叙述 `prompt_en`；与 VBench 文件名相关的是 **`prompt`**，须与 `VBench_full_info.json` 的 `prompt_en` 一致）。id 一般为字符串 `"0"`, `"1"`, …，与推理目录名一致。
- **推理目录**：`{infer_root}/{id}/{i}.mp4`；`i` 由 `materialize_eval_layout.py` 的 **`--indices`** 指定（默认 `0..4`，可改为 `0..9` 等）。
- **对齐规则**：用 map 里的 **`prompt` 字段** 与 `vbench/VBench_full_info.json` 中的 **`prompt_en`** 做**完全一致**匹配，得到该 id 对应的官方句子与 `dimension` 列表（若 full_info 中同句多行，会合并维度并集）。
- **输出布局**：`{out_base}/{model}/{folder}/{prompt_en}-{i}.mp4`；`folder` 与根目录 `evaluate.sh` 中「维度 → 子目录」一致（见 `evaluate_layout.py`）。

## 文件说明

| 文件 | 说明 |
|------|------|
| `evaluate_layout.py` | 与 `evaluate.sh` 对齐的 `dimension → folder` 及反向查询（某 folder 服务哪些维度）。 |
| `map_infer_ids.py` | 生成 id → `prompt_en_vbench`、`dimensions` 等汇总 JSON（含 `unmatched`、`collisions`）。 |
| `materialize_eval_layout.py` | 从 `{infer_root}/{id}/{i}.mp4` 复制或软链到上述 VBench 布局。 |
| `run_prepare.sh` | 依次调用上述两步的示例脚本（默认 indices `0..4`）。 |
| `run_prepare_with_indices.sh` | 同上，第 5 个参数传入 `--indices` 列表（如 `0,1,...,9`）。 |

## 使用方法

### 1. 生成 id 与维度的映射表

```bash
# 在仓库根目录执行
python3 custom_scripts/group_infer_output/map_infer_ids.py \
  -o custom_scripts/group_infer_output/id_dimensions.json
```

可选参数：

- `--prompt-map`：默认 `resources/vbench_prompt_align_gpt.json`（若仍用旧表可显式传 `resources/prompt_map_vbench_gpt.json`）
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

**更多样本（如 BoN=10，铺 `0..9`）**：

```bash
bash custom_scripts/group_infer_output/run_prepare_with_indices.sh \
  /path/to/infer_root 模型名 ./vbench_videos "" "0,1,2,3,4,5,6,7,8,9"
```

铺完后请用 `custom_scripts/eval_custom/evaluate_custom.py` 的 **`--seed_start` / `--seed_end`** 与 indices 对齐（官方 `evaluate.py` 仍只认 `0..4`）。

完成后可用根目录 `evaluate.sh` 或 `custom_scripts/bound/run_evaluate_bounds.sh` 指向同一 `{out_base}/{model}/...` 做评测。

## 注意事项

- 若 `prompt` 与官方 `prompt_en` 不完全一致，该 id 会进入 `unmatched`，不会生成目标文件。
- 软链在移动或删除 infer 原文件后会影响评测目录；需要自包含快照请用 `--method copy`。
