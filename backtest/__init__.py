"""
Backtest engine module for running trading strategies.
"""

from .strategy import BacktestStrategy
from .position_manager import PercentRisk, FixedSize, RiskManager
from .performance import compute_performance, PerformanceMetrics

__all__ = ['BacktestStrategy', 'PercentRisk', 'FixedSize', 'RiskManager', 'compute_performance', 'PerformanceMetrics']