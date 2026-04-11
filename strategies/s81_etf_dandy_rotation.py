"""
ETF momentum rotation strategy adapted from
`81搞市场最靓的仔！指数ETF动量轮动策略-2.txt`.

Logic:
- Rank ETF pool by smoothed momentum relative to ~21-day anchor period
- If no position and top ETF passes buy threshold, open position
- If holding top ETF and it breaks sell threshold, exit
- If another ETF becomes top and passes buy threshold, switch
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import zlib


class ETFDandyRotation:
    """Generate daily target ETF code using thresholded momentum switching."""

    multi_asset = True

    def __init__(self,
                 etf_pool: list[str],
                 history_window: int = 30,
                 n_days: int = 21,
                 buy_threshold: float = 1.001,
                 sell_threshold: float = 0.999):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFDandyRotation")
        self.etf_pool = etf_pool
        self.history_window = int(history_window)
        self.n_days = int(n_days)
        self.buy_threshold = float(buy_threshold)
        self.sell_threshold = float(sell_threshold)
        

    def _calc_signal(self, history_series: pd.Series, curr_price: float) -> tuple[float, float] | None:
        # Approximate source intent with daily bars:
        # - history excludes today (like attribute_history)
        # - today's close approximates 14:50 current price
        values = history_series.values
        need_len = max(self.history_window, self.n_days + 2, 23)
        if len(values) < need_len or self.n_days <= 0:
            return None

        if not np.isfinite(curr_price) or curr_price <= 0:
            return None

        base_window = values[-23:-20]
        if len(base_window) < 3 or np.any(base_window <= 0):
            return None
        base_price = float(values[-self.n_days])
        if base_price <= 0:
            return None
        if not np.isfinite(values[-1]) or not np.isfinite(values[-2]) or values[-1] <= 0 or values[-2] <= 0:
            return None

        # R = (close[-2] + close[-1] + curr_price - sum(close[-23:-20])) * 100 / sum(close[-23:-20])
        momentum = float((values[-2] + values[-1] + curr_price - base_window.sum()) * 100.0 / base_window.sum())
        return momentum, curr_price / base_price

    @staticmethod
    def _tie_break_jitter(ts: pd.Timestamp, code: str) -> float:
        key = f"{ts.strftime('%Y%m%d')}|{code}"
        return (zlib.crc32(key.encode('utf-8')) % 1000) / 1_000_000_000.0

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        target = pd.Series(index=panel.index, dtype='object')
        holding = None

        start_idx = max(self.history_window, self.n_days)
        # Use same-day signal: today's close approximates 14:50 current price.
        for idx in range(start_idx, len(panel)):
            signal_ts = panel.index[idx]
            hist = panel.iloc[:idx].tail(self.history_window)
            today_row = panel.iloc[idx]

            rank_rows = []
            ratio_map = {}
            for code in hist.columns:
                curr_price = float(today_row[code]) if pd.notna(today_row[code]) else np.nan
                signal = self._calc_signal(hist[code], curr_price)
                if signal is None:
                    continue
                momentum, ratio = signal
                rank_rows.append((momentum + self._tie_break_jitter(signal_ts, code), code))
                ratio_map[code] = ratio

            if not rank_rows:
                target.iloc[idx] = holding if holding is not None else np.nan
                continue

            rank_rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
            top_code = rank_rows[0][1]
            top_ratio = ratio_map[top_code]

            # State machine: open / hold / switch based on threshold confirmations.
            if holding is None:
                if top_ratio > self.buy_threshold:
                    holding = top_code
            elif holding == top_code:
                hold_ratio = ratio_map.get(holding)
                if hold_ratio is not None and hold_ratio < self.sell_threshold:
                    holding = None
            else:
                if top_ratio > self.buy_threshold:
                    holding = top_code

            target.iloc[idx] = holding if holding is not None else np.nan

        return target
