"""
Backtest engine module for running trading strategies.
"""

from .rotation_strategy import RotationBacktestStrategy
from .position_manager import PercentRisk, FixedSize, RiskManager
from .performance import compute_performance, PerformanceMetrics

__all__ = ['RotationBacktestStrategy', 'PercentRisk', 'FixedSize', 'RiskManager', 'compute_performance', 'PerformanceMetrics']