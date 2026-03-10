"""
Strategies module - collection of trading signal generators.
"""

from .sma_crossover import SMACrossover
from .rsi_strategy import RSIStrategy
from .macd_strategy import MACDStrategy
from .kdj_strategy import KDJStrategy
from .bollinger_strategy import BollingerStrategy
from .multi_factor_strategy import MultiFactorStrategy

__all__ = [
    'SMACrossover',
    'RSIStrategy',
    'MACDStrategy',
    'KDJStrategy',
    'BollingerStrategy',
    'MultiFactorStrategy',
]