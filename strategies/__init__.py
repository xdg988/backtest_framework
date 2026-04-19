"""
Strategies module - collection of trading signal generators.
"""

from .s17_etf_momentum_epo_rotation import ETFMomentumEPORotation
from .s81_etf_dandy_rotation import ETFDandyRotation
from .s101_etf_dynamic_momentum_rotation import ETFDynamicMomentumRotation
from .s14_etf_safe_dog_rotation import ETFSafeDogRotation
from .s26_etf_volcorr_rotation import ETFVolCorrRotation
from .s58_etf_ma_momentum_rotation import ETFMAMomentumRotation

__all__ = [
    'ETFMomentumEPORotation',
    'ETFDandyRotation',
    'ETFDynamicMomentumRotation',
    'ETFSafeDogRotation',
    'ETFVolCorrRotation',
    'ETFMAMomentumRotation',
]