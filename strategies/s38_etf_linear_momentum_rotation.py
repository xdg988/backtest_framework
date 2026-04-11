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
        self.m_days = int(m_days)
        self.top_n = int(top_n)
        self.min_score = float(min_score) if min_score is not None else None

    def _momentum_score(self, window: pd.Series) -> float:
        # Weighted linear fit on log-prices to favor recent observations.
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
        # Keep denominator consistent with original source implementation.
        denominator = np.sum(weights * (y - np.mean(y)) ** 2)
        if denominator == 0:
            return np.nan
        r_squared = 1 - (np.sum(weighted_residuals) / denominator)

        # Final ranking score: trend return adjusted by fit quality.
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
        self.cash_dates: set[pd.Timestamp] = set()
        if panel.empty:
            return target

        for idx in range(self.m_days - 1, len(panel)):
            hist = panel.iloc[idx - self.m_days + 1: idx + 1]
            scores = {code: self._momentum_score(hist[code]) for code in hist.columns}
            score_s = pd.Series(scores).dropna().sort_values(ascending=False)
            # Optional absolute quality filter.
            if self.min_score is not None:
                score_s = score_s[score_s >= self.min_score]
            if score_s.empty:
                self.cash_dates.add(panel.index[idx])
                target.iloc[idx] = None
                continue
            selected = score_s.index[:max(1, self.top_n)]
            # Rotation engine in one-target mode only consumes the first code.
            target.iloc[idx] = selected[0]

        return target
