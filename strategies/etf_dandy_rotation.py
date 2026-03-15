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

    @staticmethod
    def _calc_signal(series: pd.Series) -> tuple[float, float] | None:
        values = series.dropna().values
        if len(values) < 23:
            return None

        curr_price = float(values[-1])
        base_window = values[-23:-20]
        if len(base_window) < 3 or np.any(base_window <= 0):
            return None
        base_price = float(np.mean(base_window))
        momentum = float((values[-3:].sum() - base_window.sum()) * 100.0 / base_window.sum())
        return momentum, curr_price / base_price

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        target = pd.Series(index=panel.index, dtype='object')
        holding = None

        start_idx = max(self.history_window - 1, 23)
        for idx in range(start_idx, len(panel)):
            hist = panel.iloc[:idx + 1].tail(self.history_window)

            rank_rows = []
            ratio_map = {}
            for code in hist.columns:
                signal = self._calc_signal(hist[code])
                if signal is None:
                    continue
                momentum, ratio = signal
                rank_rows.append((momentum, code))
                ratio_map[code] = ratio

            if not rank_rows:
                target.iloc[idx] = holding if holding is not None else np.nan
                continue

            rank_rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
            top_code = rank_rows[0][1]
            top_ratio = ratio_map[top_code]

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
