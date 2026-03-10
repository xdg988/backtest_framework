"""Script to execute a backtest using the modular framework."""

import os
import pandas as pd
import backtrader as bt
import argparse

from data_loader import fetch_daily
from .strategy import BacktestStrategy
from strategies import SMACrossover, RSIStrategy, MACDStrategy, KDJStrategy, BollingerStrategy, MultiFactorStrategy
from position_manager import PercentRisk, FixedSize, RiskManager
from performance import compute_performance
from config import config
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
