"""
ETF Trend + Low-Correlation Rotation Strategy.

Adapted from JoinQuant-style idea:
- Trend filter first (short MA above long MA)
- Select low-correlation subset
- Rank by momentum score (annualized slope * R-squared)
- Hold top ETF
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ETFTrendCorrRotation:
    """Generate daily target ETF code for rotation using only daily bars."""

    multi_asset = True

    def __init__(self,
                 etf_pool: list[str],
                 m_days: int = 25,
                 corr_lookback: int = 243,
                 corr_pick: int = 4,
                 target_num: int = 1,
                 trend_short_ma: int = 10,
                 trend_long_ma: int = 30,
                 score_min: float = -0.5,
                 score_max: float = 4.5):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFTrendCorrRotation")

        self.etf_pool = etf_pool
        self.m_days = m_days
        self.corr_lookback = corr_lookback
        self.corr_pick = corr_pick
        self.target_num = target_num
        self.trend_short_ma = trend_short_ma
        self.trend_long_ma = trend_long_ma
        self.score_min = score_min
        self.score_max = score_max

    def _momentum_score(self, window: pd.Series) -> float:
        # Momentum quality score from log-price trend and fit quality.
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

    def _trend_filter(self, hist: pd.DataFrame) -> list[str]:
        # Stage 1: keep assets in uptrend (short MA > long MA).
        candidates = []
        for code in hist.columns:
            series = hist[code].dropna()
            if len(series) < self.trend_long_ma:
                continue
            short_ma = series.rolling(self.trend_short_ma).mean().iloc[-1]
            long_ma = series.rolling(self.trend_long_ma).mean().iloc[-1]
            if pd.notna(short_ma) and pd.notna(long_ma) and short_ma > long_ma:
                candidates.append(code)
        return candidates

    def _low_corr_subset(self, hist: pd.DataFrame, candidates: list[str]) -> list[str]:
        if len(candidates) <= self.corr_pick:
            return candidates

        # Stage 2: from trend candidates, keep low-correlation subset.
        returns = np.log(hist[candidates]).diff().dropna(how='all')
        if returns.empty:
            return candidates
        corr = returns.corr().abs()
        corr_mean = corr.mean(axis=1).sort_values()
        return corr_mean.index[:self.corr_pick].tolist()

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        """Generate per-date target ETF code."""
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        min_hist = max(self.corr_lookback, self.trend_long_ma, self.m_days)
        target = pd.Series(index=panel.index, dtype='object')

        for idx in range(min_hist - 1, len(panel)):
            hist = panel.iloc[idx - min_hist + 1: idx + 1]

            candidates = self._trend_filter(hist)
            if not candidates:
                continue

            low_corr = self._low_corr_subset(hist.iloc[-self.corr_lookback:], candidates)
            if not low_corr:
                continue

            momentum_hist = hist.iloc[-self.m_days:]
            scores = {
                code: self._momentum_score(momentum_hist[code])
                for code in low_corr
            }
            score_s = pd.Series(scores).dropna()
            # Stage 3: apply score band and pick the strongest asset.
            score_s = score_s[(score_s > self.score_min) & (score_s < self.score_max)]
            score_s = score_s.sort_values(ascending=False)

            if score_s.empty:
                continue

            selected = score_s.index[:max(1, self.target_num)]
            target.iloc[idx] = selected[0]

        return target
