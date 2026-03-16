#!/bin/bash
set -e

# Run backtest script with default parameters
# Output will be redirected to results/backtest.log

cd /home/ecs-user/code/backtest_framework

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate quant

# Source local env token file if present (keeps token out of default.yaml)
if [ -f "$(pwd)/env/set_tushare_token.sh" ]; then
	# shellcheck disable=SC1090
	. "$(pwd)/env/set_tushare_token.sh"
fi

# Install/update dependencies if needed
# pip install -r requirements.txt

# Ensure results directory exists
mkdir -p results

# Run backtest with YAML configuration (supports extra args, e.g. --config ...)
python run_backtest.py "$@" > results/backtest.log 2>&1

echo "Backtest completed. Check results/backtest.log and results/ directory for output and report."