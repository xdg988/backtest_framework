"""Script to execute a backtest using the modular framework."""

import os
import pandas as pd
import backtrader as bt
import argparse

from data_loader.data_loader import fetch_daily
from backtest.strategy import BacktestStrategy
from strategies import SMACrossover, RSIStrategy, MACDStrategy, KDJStrategy, BollingerStrategy, MultiFactorStrategy
from backtest.position_manager import PercentRisk, FixedSize, RiskManager
from backtest.performance import compute_performance
from config.config import Config
from reporting import BacktestVisualizer, PerformanceMetrics, ReportGenerator


def run(ts_code: str,
        start: str,
        end: str,
        cash: float = 100000,
        token: str = None,
        strategy_class=None,
        signal_kwargs: dict = None,
        position_mgr=None,
        risk_mgr=None,
        enable_charts: bool = True) -> tuple:
    """Run a backtest and return a record DataFrame.

    Parameters
    ----------
    ts_code : str
        tushare code to fetch, e.g. '000001.SZ'.
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
    position_mgr : object
        Instance of FixedSize or PercentRisk.
    risk_mgr : object
        Instance of RiskManager for risk controls.
    """
    try:
        df = fetch_daily(ts_code, start, end, token)
    except Exception as e:
        print(f"Error fetching data: {e}")
        print("Cannot proceed with backtest without data.")
        return None, []

    # backtrader expects a column called "open","high","low","close","volume"
    datafeed = bt.feeds.PandasData(dataname=df)

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(cash)
    cerebro.adddata(datafeed)

    siggen = strategy_class(**(signal_kwargs or {}))
    if position_mgr is None:
        position_mgr = FixedSize(size=100)  # default

    cerebro.addstrategy(BacktestStrategy,
                        signal_generator=siggen,
                        position_manager=position_mgr,
                        risk_manager=risk_mgr)

    print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")
    strat_list = cerebro.run()
    strat = strat_list[0]
    print(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f}")

    # convert records to DataFrame
    rec = pd.DataFrame(strat.records).set_index('date')

    # Generate visualizations and report if enabled
    if enable_charts:
        # Create comprehensive report
        report_gen = ReportGenerator()
        report_path = report_gen.generate_report(
            strategy_name=strategy_class.__name__,
            start_date=start,
            end_date=end,
            records=rec,
            trades=strat.trades,
            data=df,
            signals=siggen.generate(df),
            output_dir=config.get('visualization.output_dir', './results'),
            initial_cash=cash
        )

        print(f"Comprehensive report generated: {report_path}")

    return rec, strat.trades


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run backtest using YAML configuration.')
    parser.add_argument('--config', type=str, default=os.path.join('config', 'default.yaml'), help='Path to config yaml file')

    args = parser.parse_args()

    config = Config(args.config)

    ts_code = config.get('backtest.default_ts_code', '000001.SZ')
    start = config.get('backtest.default_start')
    end = config.get('backtest.default_end')
    cash = config.get('backtest.default_cash', 100000)
    token = config.get('data.token')
    position_type = config.get('position.default_type', 'percent')
    position_value = config.get('position.default_value', 0.1)
    enable_charts = config.get('visualization.enable_charts', True)
    strategy_name = config.get('backtest.default_strategy', 'SMACrossover')

    if not token:
        raise ValueError("Tushare token must be provided in config/default.yaml")

    # Map strategy name to class
    strategy_map = {
        'SMACrossover': SMACrossover,
        'RSIStrategy': RSIStrategy,
        'MACDStrategy': MACDStrategy,
        'KDJStrategy': KDJStrategy,
        'BollingerStrategy': BollingerStrategy,
        'MultiFactorStrategy': MultiFactorStrategy,
    }
    if strategy_name not in strategy_map:
        raise ValueError(f"Unsupported strategy in config: {strategy_name}. Available: {list(strategy_map.keys())}")

    strategy_class = strategy_map[strategy_name]

    # Load strategy parameters from config
    strategy_config_key_map = {
        'SMACrossover': 'sma',
        'RSIStrategy': 'rsi',
        'MACDStrategy': 'macd',
        'KDJStrategy': 'kdj',
        'BollingerStrategy': 'bollinger',
        'MultiFactorStrategy': 'multi_factor',
    }
    strategy_key = strategy_config_key_map[strategy_name]
    signal_kwargs = config.get(f'strategies.{strategy_key}', {})

    # Position manager
    if position_type == 'fixed':
        position_mgr = FixedSize(size=int(position_value))
    else:
        position_mgr = PercentRisk(percent=position_value)

    # Risk manager
    risk_mgr = RiskManager(
        stop_loss_percent=config.get('risk.stop_loss_percent'),
        take_profit_percent=config.get('risk.take_profit_percent'),
        max_drawdown_percent=config.get('risk.max_drawdown_percent')
    )

    # Run backtest
    records, trades = run(ts_code, start, end, cash, token, strategy_class, signal_kwargs, position_mgr, risk_mgr, enable_charts)

    if records is None:
        print("Backtest failed due to data fetching error.")
        exit(1)

    print("Backtest completed successfully")
    print(f"Final portfolio value: {records['value'].iloc[-1]:.2f}")
    perf = compute_performance(records['value'])
    print('Performance metrics:')
    for k, v in perf.items():
        print(f"{k}: {v:.4f}")
