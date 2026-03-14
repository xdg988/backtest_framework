"""Script to execute a backtest using the modular framework."""

import os
import pandas as pd
import backtrader as bt
import argparse

from data_loader.data_loader import fetch_daily_multiple, fetch_benchmark_series, normalize_ts_code
from backtest.rotation_strategy import RotationBacktestStrategy
from strategies import (
    ETFLinearMomentumRotation,
    ETFTrendCorrRotation,
)
from backtest.performance import compute_performance
from config.config import Config
from reporting import ReportGenerator


def run(start: str,
        end: str,
        cash: float = 100000,
        token: str = None,
        strategy_class=None,
        signal_kwargs: dict = None,
        slippage_perc: float = 0.001,
        benchmark_code: str = '000300.SH',
        enable_charts: bool = True,
        output_dir: str = './results') -> tuple:
    """Run a backtest and return a record DataFrame.

    Parameters
    ----------
    start : str
        start date YYYYMMDD
    end : str
        end date YYYYMMDD
    cash : float
        Starting cash
    token : str
        tushare token (or will read TUSHARE_TOKEN env).
    strategy_class : class
        Strategy class from strategies module, e.g. SMACrossover. Required.
    signal_kwargs : dict
        Arguments for the strategy class.
    slippage_perc : float
        Slippage percentage for each trade, e.g. 0.001 means 0.1%.
    benchmark_code : str
        Benchmark symbol, default HS300 index code '000300.SH'.
    """
    if strategy_class is None or not getattr(strategy_class, 'multi_asset', False):
        raise ValueError('This framework now supports multi-asset rotation strategies only.')

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(cash)
    if slippage_perc and slippage_perc > 0:
        cerebro.broker.set_slippage_perc(slippage_perc)

    signal_kwargs = signal_kwargs or {}
    siggen = strategy_class(**signal_kwargs)
    pool_codes = [normalize_ts_code(code) for code in siggen.etf_pool]
    siggen.etf_pool = pool_codes
    try:
        data_map = fetch_daily_multiple(pool_codes, start, end, token)
    except Exception as e:
        print(f"Error fetching multi-asset data: {e}")
        print("Cannot proceed with backtest without data.")
        return None, []

    for code, df_item in data_map.items():
        datafeed = bt.feeds.PandasData(dataname=df_item)
        cerebro.adddata(datafeed, name=code)

    cerebro.addstrategy(RotationBacktestStrategy, signal_generator=siggen)
    report_data = next(iter(data_map.values()))

    print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")
    strat_list = cerebro.run()
    strat = strat_list[0]
    print(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f}")

    # convert records to DataFrame
    rec = pd.DataFrame(strat.records).set_index('date')

    # Generate visualizations and report if enabled
    if enable_charts:
        report_signals = pd.Series(0, index=report_data.index)

        benchmark_series = fetch_benchmark_series(
            start_date=start,
            end_date=end,
            token=token,
            benchmark_code=benchmark_code
        )
        benchmark_value = None
        if benchmark_series is not None and not benchmark_series.empty:
            aligned = benchmark_series.reindex(rec.index).ffill().dropna()
            if not aligned.empty and aligned.iloc[0] != 0:
                benchmark_value = aligned / aligned.iloc[0] * cash

        # Create comprehensive report
        report_gen = ReportGenerator()
        report_path = report_gen.generate_report(
            strategy_name=strategy_class.__name__,
            start_date=start,
            end_date=end,
            records=rec,
            trades=strat.trades,
            data=report_data,
            signals=report_signals,
            benchmark=benchmark_value,
            output_dir=output_dir,
            initial_cash=cash
        )

        print(f"Comprehensive report generated: {report_path}")

    return rec, strat.trades


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run backtest using YAML configuration.')
    parser.add_argument('--config', type=str, default=os.path.join('config', 'default.yaml'), help='Path to config yaml file')

    args = parser.parse_args()

    config = Config(args.config)

    start = config.get('backtest.default_start')
    end = config.get('backtest.default_end')
    cash = config.get('backtest.default_cash', 100000)
    token = config.get('data.token')
    slippage_perc = config.get('backtest.slippage_perc', 0.001)
    benchmark_code = config.get('backtest.benchmark_code', '000300.SH')
    enable_charts = config.get('visualization.enable_charts', True)
    output_dir = config.get('visualization.output_dir', './results')
    strategy_name = config.get('backtest.default_strategy', 'ETFLinearMomentumRotation')

    if not token:
        raise ValueError("Tushare token must be provided in config/default.yaml")

    # Map strategy name to class
    strategy_map = {
        'ETFLinearMomentumRotation': ETFLinearMomentumRotation,
        'ETFTrendCorrRotation': ETFTrendCorrRotation,
    }
    if strategy_name not in strategy_map:
        raise ValueError(f"Unsupported strategy in config: {strategy_name}. Available: {list(strategy_map.keys())}")

    strategy_class = strategy_map[strategy_name]

    # Load strategy parameters from config
    strategy_config_key_map = {
        'ETFLinearMomentumRotation': 'etf_linear_rotation',
        'ETFTrendCorrRotation': 'etf_trend_corr_rotation',
    }
    strategy_key = strategy_config_key_map[strategy_name]
    signal_kwargs = config.get(f'strategies.{strategy_key}', {})

    # Run backtest
    records, trades = run(start, end, cash, token, strategy_class, signal_kwargs, slippage_perc, benchmark_code, enable_charts, output_dir)

    if records is None:
        print("Backtest failed due to data fetching error.")
        exit(1)

    print("Backtest completed successfully")
    print(f"Final portfolio value: {records['value'].iloc[-1]:.2f}")
    perf = compute_performance(records['value'])
    print('Performance metrics:')
    for k, v in perf.items():
        print(f"{k}: {v:.4f}")
