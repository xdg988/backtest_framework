#!/bin/bash

# Run backtest script with default parameters
# Output will be redirected to logs file

cd /home/ecs-user/code/backtest_framework

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate quant

# Install/update dependencies if needed
pip install -r requirements.txt

# Set token environment variable
export TUSHARE_TOKEN="xx"

# Run the backtest with example parameters
python run_backtest.py --strategy SMACrossover --enable_charts

echo "Backtest completed. Check logs file and results/ directory for output and report."