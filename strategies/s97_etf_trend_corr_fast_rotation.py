"""Strategy 97 alias: fast trend-correlation ETF rotation."""

from __future__ import annotations

from .s74_etf_trend_corr_rotation import ETFTrendCorrRotation


class ETFTrendCorrFastRotation(ETFTrendCorrRotation):
    """Alias class for strategy 97; currently reuses ETFTrendCorrRotation logic."""
