"""
ETF Safe-Dog Rotation Strategy.

Adapted from JoinQuant strategy idea in
`2025strategy/14安全摸狗策略.txt`:
- Weighted linear momentum score (annualized return * weighted R-squared)
- Use safety band on score to avoid extremely weak/overheated regimes
- Hold top-ranked ETF
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ETFSafeDogRotation:
    """Generate daily target ETF code using safe-bounded weighted momentum."""

    multi_asset = True

    def __init__(self,
                 etf_pool: list[str],
                 m_days: int = 25,
                 top_n: int = 1,
                 score_min: float = 0.0,
                 score_max: float = 5.0):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFSafeDogRotation")
        self.etf_pool = etf_pool
        self.m_days = int(m_days)
        self.top_n = int(top_n)
        self.score_min = float(score_min)
        self.score_max = float(score_max)

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
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        target = pd.Series(index=panel.index, dtype='object')

        for idx in range(self.m_days - 1, len(panel)):
            hist = panel.iloc[idx - self.m_days + 1: idx + 1]
            scores = {code: self._momentum_score(hist[code]) for code in hist.columns}
            score_s = pd.Series(scores).dropna().sort_values(ascending=False)
            score_s = score_s[(score_s > self.score_min) & (score_s <= self.score_max)]
            if score_s.empty:
                continue
            selected = score_s.index[:max(1, self.top_n)]
            target.iloc[idx] = selected[0]

        return target
