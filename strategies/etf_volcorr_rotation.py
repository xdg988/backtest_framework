"""
ETF Volatility-Filtered Minimum-Correlation Rotation.

Adapted from `2025strategy/26波动率过滤后相关性最小etf轮动.txt`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ETFVolCorrRotation:
    """Daily top-1 rotation after vol filter and low-correlation selection."""

    multi_asset = True

    def __init__(self,
                 etf_pool: list[str],
                 m_days: int = 25,
                 corr_lookback: int = 729,
                 corr_pick: int = 4,
                 vol_min: float = 0.05,
                 vol_max: float = 0.33,
                 score_min: float = -0.5,
                 score_max: float = 4.5,
                 annual_days: int = 243):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFVolCorrRotation")
        self.etf_pool = etf_pool
        self.m_days = int(m_days)
        self.corr_lookback = int(corr_lookback)
        self.corr_pick = int(corr_pick)
        self.vol_min = float(vol_min)
        self.vol_max = float(vol_max)
        self.score_min = float(score_min)
        self.score_max = float(score_max)
        self.annual_days = int(annual_days)

    def _momentum_score(self, window: pd.Series) -> float:
        values = window.dropna().values
        if len(values) < self.m_days:
            return np.nan
        y = np.log(values)
        x = np.arange(len(y))
        slope, intercept = np.polyfit(x, y, 1)
        annualized_returns = np.exp(slope * 250) - 1
        denominator = (len(y) - 1) * np.var(y, ddof=1)
        if denominator == 0:
            return np.nan
        r_squared = 1 - (np.sum((y - (slope * x + intercept)) ** 2) / denominator)
        return annualized_returns * r_squared

    def _min_corr_subset(self, hist: pd.DataFrame) -> list[str]:
        p = hist.dropna(axis=1, how='any')
        if p.empty:
            return []

        r = np.log(p).diff().dropna(how='all')
        if r.empty:
            return []
        v = r.std() * np.sqrt(self.annual_days)
        v = v[(v > self.vol_min) & (v < self.vol_max)]
        if v.empty:
            return []

        r = r[v.index]
        corr = r.corr()
        corr_mean = corr.abs().mean(axis=1).sort_values()
        return corr_mean.index[:self.corr_pick].tolist()

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        target = pd.Series(index=panel.index, dtype='object')
        min_hist = max(self.corr_lookback, self.m_days)

        for idx in range(min_hist - 1, len(panel)):
            hist = panel.iloc[idx - self.corr_lookback + 1: idx + 1]
            subset = self._min_corr_subset(hist)
            if not subset:
                continue

            mom_hist = panel.loc[hist.index, subset].iloc[-self.m_days:]
            scores = {code: self._momentum_score(mom_hist[code]) for code in subset}
            score_s = pd.Series(scores).dropna()
            score_s = score_s[(score_s > self.score_min) & (score_s < self.score_max)]
            score_s = score_s.sort_values(ascending=False)
            if score_s.empty:
                continue
            target.iloc[idx] = str(score_s.index[0])

        return target
