TIMESTAMP=$(date -ud "8 hours" +%Y%m%d_%H%M%S)
LOG_NAME="test_${TIMESTAMP}_rank0_1.log"

# Redirect all stdout and stderr to both console and log file for the entire script
exec 1> >(tee -a "${LOG_NAME}")
exec 2>&1


for i in {0..100}; do
    python3 custom_scripts/custom_scoring/cal_custom_score.py \
    --results_dir /home/user/data/loski/project/LRM/sample/vb_format/wan13_10_eval_results \
    --tie_json resources/lrm_n10_result/scores_t_10.json \
    --index_lo 0 --index_hi 9 \
    --within_prompt_agg max \
    --seed $i \
    --prompt_sample_ratio 0.5 \
done