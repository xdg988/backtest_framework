#!/bin/bash
set -e

# Run backtest script with default parameters
# Output will be redirected to results/backtest.log

cd /home/ecs-user/code/backtest_framework

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate quant

# Install/update dependencies if needed
# pip install -r requirements.txt

# Ensure results directory exists
mkdir -p results

# Run backtest with YAML configuration
python run_backtest.py > results/backtest.log 2>&1

echo "Backtest completed. Check results/backtest.log and results/ directory for output and report."