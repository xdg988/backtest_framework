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
                 trend_history: int = 3500,
                 trend_limit: float = 3.0,
                 score_min: float = -0.5,
                 score_max: float = 4.5):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFTrendCorrRotation")

        self.etf_pool = etf_pool
        self.m_days = int(m_days)
        self.corr_lookback = int(corr_lookback)
        self.corr_pick = int(corr_pick)
        self.target_num = int(target_num)
        self.trend_short_ma = int(trend_short_ma)
        self.trend_long_ma = int(trend_long_ma)
        self.trend_history = int(trend_history)
        self.trend_limit = float(trend_limit)
        self.score_min = float(score_min)
        self.score_max = float(score_max)
        # Let runner infer enough warmup bars for trend-length filter.
        self.history_window = max(self.trend_history, self.corr_lookback, self.m_days)

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

    @staticmethod
    def _count_days_above(series: pd.Series, short_window: int, long_window: int) -> float:
        clean = series.dropna()
        if len(clean) <= long_window:
            return 0.0
        short_ma = clean.rolling(window=short_window).mean().to_numpy()
        long_ma = clean.rolling(window=long_window).mean().to_numpy()

        count = 0
        total_days = 0
        for i in range(long_window, len(clean)):
            if pd.notna(short_ma[i]) and pd.notna(long_ma[i]) and short_ma[i] > long_ma[i]:
                if i == long_window or not (
                    pd.notna(short_ma[i - 1]) and pd.notna(long_ma[i - 1]) and short_ma[i - 1] > long_ma[i - 1]
                ):
                    count = 0
                count += 1
            else:
                count = 0

            if count > 0:
                total_days += count

        denom = len(clean) - long_window
        if denom <= 0:
            return 0.0
        return total_days / denom

    def _trend_filter(self, hist: pd.DataFrame) -> list[str]:
        # Stage 1: source-like trend-length filter (equivalent to get_trend_length).
        candidates = []
        for code in hist.columns:
            score = self._count_days_above(hist[code], self.trend_short_ma, self.trend_long_ma)
            if score > self.trend_limit:
                candidates.append(code)
        return candidates

    def _low_corr_subset(self, hist: pd.DataFrame, candidates: list[str]) -> list[str]:
        # Stage 2: from trend candidates, keep low-correlation subset.
        prices = hist[candidates].dropna(axis=1, how='any')
        if prices.empty:
            return []
        if prices.shape[1] <= self.corr_pick:
            return prices.columns.tolist()

        returns = np.log(prices).diff().iloc[1:]
        if returns.empty:
            return prices.columns.tolist()
        corr = returns.corr().abs()
        corr_mean = corr.mean(axis=1).sort_values()
        return corr_mean.index[:self.corr_pick].tolist()

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        """Generate per-date target ETF code."""
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        min_hist = max(self.corr_lookback, self.trend_long_ma, self.m_days)
        target = pd.Series(index=panel.index, dtype='object')
        self.cash_dates: set[pd.Timestamp] = set()

        for idx in range(min_hist - 1, len(panel)):
            hist = panel.iloc[idx - min_hist + 1: idx + 1]
            trend_hist = panel.iloc[max(0, idx - self.trend_history + 1): idx + 1]

            candidates = self._trend_filter(trend_hist)
            if not candidates:
                self.cash_dates.add(panel.index[idx])
                continue

            low_corr = self._low_corr_subset(hist.iloc[-self.corr_lookback:], candidates)
            if not low_corr:
                self.cash_dates.add(panel.index[idx])
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
                self.cash_dates.add(panel.index[idx])
                continue

            selected = score_s.index[:max(1, self.target_num)]
            target.iloc[idx] = selected[0]

        return target
