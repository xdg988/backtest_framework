"""
Strategies module - collection of trading signal generators.
"""

from .etf_linear_momentum_rotation import ETFLinearMomentumRotation
from .etf_trend_corr_rotation import ETFTrendCorrRotation
from .etf_momentum_epo_rotation import ETFMomentumEPORotation
from .etf_dandy_rotation import ETFDandyRotation
from .etf_safe_dog_rotation import ETFSafeDogRotation
from .etf_core_rotation_stoploss import ETFCoreRotationStoploss
from .etf_volcorr_rotation import ETFVolCorrRotation
from .etf_epo_lowcorr_combo import ETFEpoLowCorrCombo

__all__ = [
    'ETFLinearMomentumRotation',
    'ETFTrendCorrRotation',
    'ETFMomentumEPORotation',
    'ETFDandyRotation',
    'ETFSafeDogRotation',
    'ETFCoreRotationStoploss',
    'ETFVolCorrRotation',
    'ETFEpoLowCorrCombo',
]