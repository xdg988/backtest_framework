"""Strategy 101: dynamic-lookback momentum ETF rotation."""

from __future__ import annotations

import math
import importlib
import numpy as np
import pandas as pd


class ETFDynamicMomentumRotation:
    """Rank ETF pool by weighted trend score with dynamic lookback and rotate to top 1."""

    multi_asset = True
    signal_price_field = 'close'

    @staticmethod
    def _norm(code: str) -> str:
        if not isinstance(code, str):
            return code
        c = code.strip().upper()
        if c.endswith('.XSHG'):
            return c.replace('.XSHG', '.SH')
        if c.endswith('.XSHE'):
            return c.replace('.XSHE', '.SZ')
        return c

    def __init__(
        self,
        etf_pool: list[str],
        m_days: int = 25,
        auto_day: bool = True,
        min_days: int = 20,
        max_days: int = 60,
        top_n: int = 1,
        score_upper: float = 6.0,
        score_price_field: str = 'open',
        enable_premium_penalty: bool = True,
        premium_threshold: float = 5.0,
        premium_penalty: float = 1.0,
    ):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFDynamicMomentumRotation")
        self.etf_pool = [self._norm(code) for code in etf_pool]
        self.m_days = int(m_days)
        self.auto_day = bool(auto_day)
        self.min_days = int(min_days)
        self.max_days = int(max_days)
        self.top_n = max(1, int(top_n))
        self.score_upper = float(score_upper)
        self.score_price_field = str(score_price_field or 'open')
        self.enable_premium_penalty = bool(enable_premium_penalty)
        self.premium_threshold = float(premium_threshold)
        self.premium_penalty = float(premium_penalty)
        self.warmup_bars = max(self.max_days + 20, self.m_days + 20)
        self.market_data = {}
        self.nav_history = {}

    def set_market_data(self, data_map: dict[str, pd.DataFrame]):
        normalized = {}
        for code, df in (data_map or {}).items():
            norm_code = self._norm(code)
            normalized[norm_code] = df.copy()
        self.market_data = normalized

    def set_nav_history(self, nav_history: dict[str, pd.Series]):
        normalized = {}
        for code, series in (nav_history or {}).items():
            norm_code = self._norm(code)
            s = series.copy()
            if not isinstance(s.index, pd.DatetimeIndex):
                s.index = pd.to_datetime(s.index, errors='coerce')
            s = s[~s.index.isna()].sort_index()
            normalized[norm_code] = s
        self.nav_history = normalized

    def _premium_rate(self, code: str, prev_close: float, ref_ts: pd.Timestamp) -> float | None:
        s = self.nav_history.get(code)
        if not np.isfinite(prev_close) or prev_close <= 0:
            return 0.0
        # Source-style behavior:
        # 1) use reference-date NAV only
        # 2) if NAV is missing/invalid, treat premium as 0 (no penalty)
        if s is None or s.empty:
            return 0.0
        ref_day = pd.Timestamp(ref_ts).normalize()
        same_day = s.loc[s.index.normalize() == ref_day]
        if same_day.empty:
            return 0.0
        nav = float(same_day.iloc[-1])
        if not np.isfinite(nav) or nav <= 0:
            return 0.0
        return (prev_close - nav) / nav * 100.0

    @staticmethod
    def _weighted_regression_score(prices: np.ndarray) -> float:
        if len(prices) < 5 or np.any(~np.isfinite(prices)) or np.any(prices <= 0):
            return 0.0

        y = np.log(prices)
        x = np.arange(len(y), dtype=float)
        weights = np.linspace(1.0, 2.0, len(y))

        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_returns = math.exp(float(slope) * 250.0) - 1.0

        fitted = slope * x + intercept
        ss_res = float(np.sum(weights * (y - fitted) ** 2))
        ss_tot = float(np.sum(weights * (y - np.mean(y)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        score = annualized_returns * r2
        if not np.isfinite(score):
            return 0.0
        return float(score)

    @staticmethod
    def _risk_filter(prices: np.ndarray) -> bool:
        if len(prices) < 5:
            return False
        p = prices
        con1 = min(p[-1] / p[-2], p[-2] / p[-3], p[-3] / p[-4]) < 0.95
        con2 = (p[-1] < p[-2]) and (p[-2] < p[-3]) and (p[-3] < p[-4]) and (p[-1] / p[-4] < 0.95)
        con3 = (p[-2] < p[-3]) and (p[-3] < p[-4]) and (p[-4] < p[-5]) and (p[-2] / p[-5] < 0.95)
        return bool(con1 or con2 or con3)

    @staticmethod
    def _atr_last(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> float | None:
        if period <= 0:
            return None
        h = high.astype(float).to_numpy()
        l = low.astype(float).to_numpy()
        c = close.astype(float).to_numpy()
        if len(c) < period + 1:
            return None
        talib_mod = importlib.import_module('talib')
        atr = talib_mod.ATR(h, l, c, timeperiod=period)
        if atr is None or len(atr) == 0:
            return None
        val = atr[-1]
        if pd.isna(val) or not np.isfinite(val):
            return None
        return float(val)

    def _dynamic_lookback(self, hist_df: pd.DataFrame) -> int:
        if not self.auto_day:
            return max(5, self.m_days)

        if any(col not in hist_df.columns for col in ('high', 'low', 'close')):
            return max(5, self.m_days)

        long_atr = self._atr_last(hist_df['high'], hist_df['low'], hist_df['close'], self.max_days)
        short_atr = self._atr_last(hist_df['high'], hist_df['low'], hist_df['close'], self.min_days)
        if long_atr is None or short_atr is None or long_atr <= 0:
            return max(5, self.m_days)

        ratio = min(0.9, short_atr / long_atr) if np.isfinite(short_atr) and short_atr >= 0 else 0.9
        lookback = int(self.min_days + (self.max_days - self.min_days) * (1.0 - ratio))
        return int(max(self.min_days, min(self.max_days, lookback)))

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]
        target = pd.Series(index=panel.index, dtype='object')
        if panel.empty:
            return target

        # Do not block globally by a fixed start index.
        # Let per-symbol data sufficiency checks decide tradability on each day,
        # which is closer to source behavior with preloaded platform history.
        start_idx = 1
        holding = None

        for idx in range(start_idx, len(panel)):
            hist = panel.iloc[:idx]
            today = panel.iloc[idx]
            ts = panel.index[idx]
            score_rows = []

            for code in panel.columns:
                curr_price = today.get(code)
                scoring_price = curr_price
                if code in self.market_data:
                    symbol_df = self.market_data[code]
                    if self.score_price_field in symbol_df.columns:
                        same_bar = symbol_df.loc[symbol_df.index == ts, self.score_price_field]
                        if not same_bar.empty and np.isfinite(same_bar.iloc[-1]):
                            scoring_price = float(same_bar.iloc[-1])
                if pd.isna(curr_price) or float(curr_price) <= 0:
                    continue
                if pd.isna(scoring_price) or float(scoring_price) <= 0:
                    continue

                hist_price = hist[code].dropna()
                if len(hist_price) < self.min_days + 5:
                    continue

                # Match source strict data sufficiency checks using OHLC history.
                hist_df = None
                if code in self.market_data:
                    symbol_df = self.market_data[code]
                    hist_df = symbol_df.loc[symbol_df.index < ts].tail(self.max_days + 10)
                if hist_df is None or len(hist_df) < (self.max_days + 10):
                    continue
                if any(col not in hist_df.columns for col in ('high', 'low', 'close')):
                    continue
                if (
                    hist_df['low'].isna().sum() > self.max_days
                    or hist_df['close'].isna().sum() > self.max_days
                    or hist_df['high'].isna().sum() > self.max_days
                ):
                    continue

                lookback = self._dynamic_lookback(hist_df)
                prices = np.append(hist_price.values, float(scoring_price))
                if len(prices) < max(lookback, 6):
                    continue
                prices = prices[-lookback:]

                score = self._weighted_regression_score(prices)
                if self._risk_filter(prices):
                    score = 0.0

                if self.enable_premium_penalty:
                    prev_ts = hist_price.index[-1]
                    prev_close = float(hist_price.iloc[-1])
                    if code in self.market_data:
                        symbol_df = self.market_data[code]
                        close_col = 'close_raw' if 'close_raw' in symbol_df.columns else 'close'
                        close_ref = symbol_df.loc[symbol_df.index <= prev_ts, close_col]
                        if not close_ref.empty and np.isfinite(close_ref.iloc[-1]):
                            prev_close = float(close_ref.iloc[-1])
                    premium_rate = self._premium_rate(code, prev_close, prev_ts)
                    if premium_rate is not None and premium_rate >= self.premium_threshold:
                        score -= self.premium_penalty

                if 0.0 < score < self.score_upper:
                    score_rows.append((score, code))

            if not score_rows:
                holding = None
                target.iloc[idx] = np.nan
                continue

            score_rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
            top_codes = [code for _, code in score_rows[:self.top_n]]
            selected = top_codes[0] if top_codes else None

            holding = selected
            target.iloc[idx] = holding if holding is not None else np.nan

        return target
