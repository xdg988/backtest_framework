"""
Strategies module - collection of trading signal generators.
"""

from .s38_etf_linear_momentum_rotation import ETFLinearMomentumRotation
from .s74_etf_trend_corr_rotation import ETFTrendCorrRotation
from .s17_etf_momentum_epo_rotation import ETFMomentumEPORotation
from .s81_etf_dandy_rotation import ETFDandyRotation
from .s14_etf_safe_dog_rotation import ETFSafeDogRotation
from .s22_etf_core_rotation_stoploss import ETFCoreRotationStoploss
from .s26_etf_volcorr_rotation import ETFVolCorrRotation
from .s58_etf_ma_momentum_rotation import ETFMAMomentumRotation

__all__ = [
    'ETFLinearMomentumRotation',
    'ETFTrendCorrRotation',
    'ETFMomentumEPORotation',
    'ETFDandyRotation',
    'ETFSafeDogRotation',
    'ETFCoreRotationStoploss',
    'ETFVolCorrRotation',
    'ETFMAMomentumRotation',
]