"""Script to execute a backtest using the modular framework."""

import os
import pandas as pd
import backtrader as bt
import argparse

from data_loader.data_loader import fetch_daily_multiple, fetch_benchmark_series, normalize_ts_code
from backtest.rotation_strategy import RotationBacktestStrategy
from backtest.weight_rotation_strategy import WeightRotationBacktestStrategy
from backtest.sell_first_broker import SellFirstBackBroker
from strategies import (
    ETFLinearMomentumRotation,
    ETFMomentumEPORotation,
    ETFDandyRotation,
    ETFDynamicMomentumRotation,
    ETFSafeDogRotation,
    ETFCoreRotationStoploss,
    ETFVolCorrRotation,
    ETFMAMomentumRotation,
)
from backtest.performance import compute_performance
from config.config import Config
from reporting import ReportGenerator

# 解决问题--策略有回看窗口时，回测起点前数据不够导致信号失真/起点延后
def _infer_warmup_bars(signal_generator) -> int:
    """Infer required pre-start history from common strategy parameters."""
    candidates = []
    for attr in ('warmup_bars', 'history_window', 'epo_lookback', 'corr_lookback', 'lookback', 'm_days', 'max_days', 'min_days', 'min_history'):
        value = getattr(signal_generator, attr, None)
        if value is None:
            continue
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            continue
        if ivalue > 0:
            candidates.append(ivalue)
    return max(candidates) if candidates else 0


def run(start: str,
        end: str,
        cash: float = 100000,
        token: str = None,
        strategy_class=None,
        signal_kwargs: dict = None,
    commission: float = 0.0005,
        slippage_perc: float = 0.001,
    target_percent: float = 0.98,
    cost_buffer: float = 0.003,
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
        Strategy class from strategies module, e.g. ETFLinearMomentumRotation. Required.
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
    cerebro.setbroker(SellFirstBackBroker())
    # Default execution mode: same-bar sell-first, so skip submit-time cash blocking.
    cerebro.broker.set_checksubmit(False)

    cerebro.broker.setcash(cash)
    if commission is not None and commission >= 0:
        cerebro.broker.setcommission(commission=commission)
    if slippage_perc and slippage_perc > 0:
        cerebro.broker.set_slippage_perc(slippage_perc)

    signal_kwargs = signal_kwargs or {}
    siggen = strategy_class(**signal_kwargs)
    pool_codes = [normalize_ts_code(code) for code in siggen.etf_pool]
    siggen.etf_pool = pool_codes
    warmup_bars = _infer_warmup_bars(siggen)
    fetch_start = start
    if warmup_bars > 0:
        fetch_start = (pd.Timestamp(start) - pd.offsets.BDay(warmup_bars + 5)).strftime('%Y%m%d')
    try:
        data_map = fetch_daily_multiple(pool_codes, fetch_start, end, token)
    except Exception as e:
        print(f"Error fetching multi-asset data: {e}")
        print("Cannot proceed with backtest without data.")
        return None, []

    for code, df_item in data_map.items():
        datafeed = bt.feeds.PandasData(dataname=df_item)
        cerebro.adddata(datafeed, name=code)

    if hasattr(siggen, 'set_market_data'):
        siggen.set_market_data(data_map)

    execution_strategy_class = (
        WeightRotationBacktestStrategy
        if hasattr(siggen, 'generate_target_weights')
        else RotationBacktestStrategy
    )

    cerebro.addstrategy(
        execution_strategy_class,
        signal_generator=siggen,
        target_percent=target_percent,
        cost_buffer=cost_buffer,
        start_date=pd.Timestamp(start),
    )
    report_data = next(iter(data_map.values())).loc[pd.Timestamp(start):]

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
    if token in (None, '', 'xx', 'YOUR_TUSHARE_TOKEN'):
        token = os.environ.get('TUSHARE_TOKEN')
    slippage_perc = config.get('backtest.slippage_perc', 0.001)
    commission = config.get('backtest.commission', 0.0005)
    target_percent = config.get('backtest.target_percent', 0.98)
    cost_buffer = config.get('backtest.cost_buffer', 0.003)
    benchmark_code = config.get('backtest.benchmark_code', '000300.SH')
    enable_charts = config.get('visualization.enable_charts', True)
    output_dir = config.get('visualization.output_dir', './results')
    strategy_name = config.get('backtest.default_strategy', 'ETFLinearMomentumRotation')

    if not token:
        raise ValueError("Tushare token is required. Set data.token in config or export TUSHARE_TOKEN.")

    # Map strategy name to class
    strategy_map = {
        'ETFLinearMomentumRotation': ETFLinearMomentumRotation,
        'ETFMomentumEPORotation': ETFMomentumEPORotation,
        'ETFDandyRotation': ETFDandyRotation,
        'ETFDynamicMomentumRotation': ETFDynamicMomentumRotation,
        'ETFSafeDogRotation': ETFSafeDogRotation,
        'ETFCoreRotationStoploss': ETFCoreRotationStoploss,
        'ETFVolCorrRotation': ETFVolCorrRotation,
        'ETFMAMomentumRotation': ETFMAMomentumRotation,
    }
    if strategy_name not in strategy_map:
        raise ValueError(f"Unsupported strategy in config: {strategy_name}. Available: {list(strategy_map.keys())}")

    strategy_class = strategy_map[strategy_name]

    # Load strategy parameters from config
    strategy_config_key_map = {
        'ETFLinearMomentumRotation': 'etf_linear_rotation',
        'ETFMomentumEPORotation': 'etf_momentum_epo_rotation',
        'ETFDandyRotation': 'etf_dandy_rotation',
        'ETFDynamicMomentumRotation': 'etf_dynamic_momentum_rotation',
        'ETFSafeDogRotation': 'etf_safe_dog_rotation',
        'ETFCoreRotationStoploss': 'etf_core_rotation_stoploss',
        'ETFVolCorrRotation': 'etf_volcorr_rotation',
        'ETFMAMomentumRotation': 'etf_ma_momentum_rotation',
    }
    strategy_key = strategy_config_key_map[strategy_name]
    strategy_cfg = dict(config.get(f'strategies.{strategy_key}', {}) or {})
    strategy_slippage = strategy_cfg.pop('slippage_perc', slippage_perc)
    strategy_commission = strategy_cfg.pop('commission', commission)
    strategy_target_percent = strategy_cfg.pop('target_percent', target_percent)
    strategy_cost_buffer = strategy_cfg.pop('cost_buffer', cost_buffer)
    signal_kwargs = strategy_cfg

    # Run backtest
    records, trades = run(
        start=start,
        end=end,
        cash=cash,
        token=token,
        strategy_class=strategy_class,
        signal_kwargs=signal_kwargs,
        commission=strategy_commission,
        slippage_perc=strategy_slippage,
        target_percent=strategy_target_percent,
        cost_buffer=strategy_cost_buffer,
        benchmark_code=benchmark_code,
        enable_charts=enable_charts,
        output_dir=output_dir,
    )

    if records is None:
        print("Backtest failed due to data fetching error.")
        exit(1)

    print("Backtest completed successfully")
    print(f"Final portfolio value: {records['value'].iloc[-1]:.2f}")
    perf = compute_performance(records['value'])
    print('Performance metrics:')
    for k, v in perf.items():
        print(f"{k}: {v:.4f}")
