#!/usr/bin/env python3
import argparse
import importlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

CUR_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CUR_DIR, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def parse_args():
    parser = argparse.ArgumentParser(
        description="VBench evaluate with configurable seed index range",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default="./evaluation_results/",
        help="output path to save the evaluation results",
    )
    parser.add_argument(
        "--full_json_dir",
        type=str,
        default=f"{REPO_ROOT}/vbench/VBench_full_info.json",
        help="path to json file with prompt and dimension information",
    )
    parser.add_argument(
        "--videos_path",
        type=str,
        required=True,
        help="folder that contains sampled videos",
    )
    parser.add_argument(
        "--dimension",
        nargs="+",
        required=True,
        help="list of evaluation dimensions, usage: --dimension <dim_1> <dim_2>",
    )
    parser.add_argument(
        "--seed_start",
        type=int,
        default=0,
        help="inclusive sample index start for vbench_standard (default: 0)",
    )
    parser.add_argument(
        "--seed_end",
        type=int,
        default=4,
        help="inclusive sample index end for vbench_standard (default: 4)",
    )
    parser.add_argument(
        "--load_ckpt_from_local",
        type=bool,
        required=False,
        help="whether load checkpoints from local default paths",
    )
    parser.add_argument(
        "--read_frame",
        type=bool,
        required=False,
        help="whether directly read frames or videos",
    )
    parser.add_argument(
        "--mode",
        choices=["custom_input", "vbench_standard", "vbench_category"],
        default="vbench_standard",
        help="""Choose one of:
1. custom_input: receive prompt from --prompt/--prompt_file or filename
2. vbench_standard: evaluate on standard prompt suite
3. vbench_category: evaluate on specific category
""",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="None",
        help="""Specify input prompt.
Mutually exclusive to --prompt_file.
Use with --mode=custom_input.
""",
    )
    parser.add_argument(
        "--prompt_file",
        type=str,
        required=False,
        help="""Path to JSON file of prompts.
Mutually exclusive to --prompt.
Use with --mode=custom_input.
""",
    )
    parser.add_argument(
        "--category",
        type=str,
        required=False,
        help="For mode=vbench_category, category name (e.g. animal).",
    )
    parser.add_argument(
        "--imaging_quality_preprocessing_mode",
        type=str,
        required=False,
        default="longer",
        help="Preprocessing mode for imaging_quality",
    )
    return parser.parse_args()


def _pick_video_suffix(video_names):
    for name in video_names:
        suffix = Path(name).suffix.lower()
        if suffix in [".mp4", ".gif", ".jpg", ".png"]:
            return Path(name).suffix
    raise ValueError("No supported video/image files found in videos_path.")


def build_full_info_with_seed_range(
    full_json_dir,
    videos_path,
    output_path,
    name,
    dimension_list,
    seed_start,
    seed_end,
    special_str="",
    verbose=False,
):
    from vbench.distributed import print0
    from vbench.utils import load_json, save_json

    full_info_list = load_json(full_json_dir)
    video_names = os.listdir(videos_path)
    postfix = _pick_video_suffix(video_names)

    cur_full_info_list = []
    for prompt_dict in full_info_list:
        if not (set(dimension_list) & set(prompt_dict["dimension"])):
            continue

        prompt = prompt_dict["prompt_en"]
        row = dict(prompt_dict)
        row["video_list"] = []
        for i in range(seed_start, seed_end + 1):
            intended_video_name = f"{prompt}{special_str}-{i}{postfix}"
            if intended_video_name in video_names:
                intended_video_path = os.path.join(videos_path, intended_video_name)
                row["video_list"].append(intended_video_path)
                if verbose:
                    print0(f"Found video: {intended_video_name}")
            else:
                print0(
                    "WARNING!!! This required video is not found! "
                    f"Missing benchmark videos can lead to unfair result: {intended_video_name}"
                )
        cur_full_info_list.append(row)

    os.makedirs(output_path, exist_ok=True)
    cur_full_info_path = os.path.join(output_path, f"{name}_full_info.json")
    save_json(cur_full_info_list, cur_full_info_path)
    print0(f"Evaluation meta data saved to {cur_full_info_path}")
    return cur_full_info_path


def evaluate_with_seed_range(my_vbench, args, name, kwargs):
    from vbench.distributed import get_rank, print0
    from vbench.utils import init_submodules, save_json

    dimension_list = args.dimension
    submodules_dict = init_submodules(
        dimension_list, local=args.load_ckpt_from_local, read_frame=args.read_frame
    )
    cur_full_info_path = build_full_info_with_seed_range(
        full_json_dir=args.full_json_dir,
        videos_path=args.videos_path,
        output_path=args.output_path,
        name=name,
        dimension_list=dimension_list,
        seed_start=args.seed_start,
        seed_end=args.seed_end,
    )

    results_dict = {}
    for dimension in dimension_list:
        try:
            dimension_module = importlib.import_module(f"vbench.{dimension}")
            evaluate_func = getattr(dimension_module, f"compute_{dimension}")
        except Exception as e:
            raise NotImplementedError(f"UnImplemented dimension {dimension}!, {e}")
        submodules_list = submodules_dict[dimension]
        results = evaluate_func(cur_full_info_path, my_vbench.device, submodules_list, **kwargs)
        results_dict[dimension] = results

    output_name = os.path.join(args.output_path, f"{name}_eval_results.json")
    if get_rank() == 0:
        save_json(results_dict, output_name)
        print0(f"Evaluation results saved to {output_name}")


def main():
    args = parse_args()

    import torch
    from vbench import VBench
    from vbench.distributed import dist_init, print0

    if args.seed_start > args.seed_end:
        raise ValueError("--seed_start must be <= --seed_end")

    dist_init()
    print0(f"args: {args}")
    device = torch.device("cuda")
    my_vbench = VBench(device, args.full_json_dir, args.output_path)

    print0("start evaluation")
    current_time = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")

    kwargs = {}
    prompt = []

    if (args.prompt_file is not None) and (args.prompt != "None"):
        raise Exception("--prompt_file and --prompt cannot be used together")
    if (args.prompt_file is not None or args.prompt != "None") and (args.mode != "custom_input"):
        raise Exception("must set --mode=custom_input for using external prompt")

    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            prompt = json.load(f)
        assert type(prompt) == dict, 'Invalid prompt file format. Correct: {"video_path": prompt, ... }'
    elif args.prompt != "None":
        prompt = [args.prompt]

    if args.category:
        kwargs["category"] = args.category
    kwargs["imaging_quality_preprocessing_mode"] = args.imaging_quality_preprocessing_mode

    result_name = f"results_{current_time}"
    if args.mode == "vbench_standard":
        evaluate_with_seed_range(my_vbench, args, result_name, kwargs)
    else:
        my_vbench.evaluate(
            videos_path=args.videos_path,
            name=result_name,
            prompt_list=prompt,
            dimension_list=args.dimension,
            local=args.load_ckpt_from_local,
            read_frame=args.read_frame,
            mode=args.mode,
            **kwargs,
        )
    print0("done")


if __name__ == "__main__":
    main()
