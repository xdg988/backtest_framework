"""
ETF Linear Momentum Rotation Strategy.

Adapted from JoinQuant-style "核心资产轮动（线性增加权重）" idea:
- Use weighted linear regression on log-close over a lookback window
- Score = annualized return * weighted R-squared
- Hold the top ranked ETF
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ETFLinearMomentumRotation:
    """Generate daily target ETF by weighted momentum ranking.

    This is a multi-asset strategy, intended to work with a basket of ETF daily bars.
    """

    multi_asset = True

    def __init__(self,
                 etf_pool: list[str],
                 m_days: int = 25,
                 top_n: int = 1,
                 min_score: float = None):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFLinearMomentumRotation")
        self.etf_pool = etf_pool
        self.m_days = m_days
        self.top_n = top_n
        self.min_score = min_score

    def _momentum_score(self, window: pd.Series) -> float:
        values = window.dropna().values
        if len(values) < self.m_days:
            return np.nan

        y = np.log(values)
        n = len(y)
        x = np.arange(n)
        weights = np.linspace(1.0, 2.0, n)

        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_returns = np.exp(slope * 250) - 1

        fitted = slope * x + intercept
        residuals = y - fitted
        weighted_residuals = weights * residuals ** 2
        denominator = np.sum(weights * (y - np.average(y, weights=weights)) ** 2)
        if denominator == 0:
            return np.nan
        r_squared = 1 - (np.sum(weighted_residuals) / denominator)

        return annualized_returns * r_squared

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        """Generate per-date target ETF code.

        Parameters
        ----------
        close_panel : pd.DataFrame
            columns are ETF codes, index is datetime, values are close prices.
        """
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        target = pd.Series(index=panel.index, dtype='object')

        for idx in range(self.m_days - 1, len(panel)):
            hist = panel.iloc[idx - self.m_days + 1: idx + 1]
            scores = {code: self._momentum_score(hist[code]) for code in hist.columns}
            score_s = pd.Series(scores).dropna().sort_values(ascending=False)
            if self.min_score is not None:
                score_s = score_s[score_s >= self.min_score]
            if score_s.empty:
                continue
            selected = score_s.index[:max(1, self.top_n)]
            target.iloc[idx] = selected[0]

        return target
