"""
Strategies module - collection of trading signal generators.
"""

from .etf_linear_momentum_rotation import ETFLinearMomentumRotation
from .etf_trend_corr_rotation import ETFTrendCorrRotation

__all__ = [
    'ETFLinearMomentumRotation',
    'ETFTrendCorrRotation',
]