"""
ETF Core Asset Rotation with Stop-loss.

Adapted from `2025strategy/22带上止损的核心资产轮动才更安心，低回撤，高收益率.txt`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ETFCoreRotationStoploss:
    """Daily top-1 momentum rotation with hold/re-entry filters."""

    multi_asset = True

    def __init__(self,
                 etf_pool: list[str],
                 m_days: int = 25,
                 history_window: int = 100,
                 hold_drop_threshold: float = 0.96):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFCoreRotationStoploss")
        self.etf_pool = etf_pool
        self.m_days = int(m_days)
        self.history_window = int(history_window)
        self.hold_drop_threshold = float(hold_drop_threshold)

    def _momentum_score(self, window: pd.Series) -> float:
        # Momentum ranking metric used to pick current best asset.
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

    def _evaluate_worth(self, series: pd.Series, is_hold: bool) -> int:
        # Return 1 means "allowed to hold/open", 0 means "avoid/exit".
        values = series.dropna().values
        if len(values) < 10:
            return 0
        cur_p = float(values[-1])
        max10_p = float(np.max(values[-10:]))
        max_p = float(np.max(values))
        cur2yes = cur_p / float(values[-2]) if float(values[-2]) != 0 else 0.0
        _ = cur_p / max_p if max_p != 0 else np.nan
        _ = cur_p / max10_p if max10_p != 0 else np.nan
        mean4 = float(np.mean(values[-4:]))

        if is_hold:
            # Existing position: use a simple one-day drop stop.
            return 0 if cur2yes <= self.hold_drop_threshold else 1
        # New entry: require current price not weaker than recent short mean.
        return 1 if cur_p >= mean4 else 0

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        target = pd.Series(index=panel.index, dtype='object')
        holding = None
        prev_holding = None

        min_idx = max(self.m_days - 1, self.history_window - 1, 10)
        for idx in range(min_idx, len(panel)):
            hist = panel.iloc[:idx + 1]

            scores = {}
            for code in panel.columns:
                window = hist[code].iloc[-self.m_days:]
                scores[code] = self._momentum_score(window)
            score_s = pd.Series(scores).dropna().sort_values(ascending=False)
            if score_s.empty:
                target.iloc[idx] = holding
                continue

            selected = str(score_s.index[0])
            selected_hist = hist[selected].iloc[-self.history_window:]
            sel_worth = self._evaluate_worth(selected_hist, is_hold=False)

            hold_worth = 0
            if holding is not None and holding in hist.columns:
                hold_hist = hist[holding].iloc[-self.history_window:]
                hold_worth = self._evaluate_worth(hold_hist, is_hold=True)

            if holding is not None:
                prev_holding = holding
                # Leave position if leader changed or hold quality degraded.
                if selected != holding or hold_worth == 0:
                    holding = None

            # Re-enter only when leader is acceptable under entry filter.
            if selected != prev_holding:
                holding = selected
            elif holding is None and selected == prev_holding and sel_worth == 1:
                holding = selected

            target.iloc[idx] = holding

        return target
