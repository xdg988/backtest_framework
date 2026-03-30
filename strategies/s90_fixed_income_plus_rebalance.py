"""Strategy 90: fixed-income-plus ETF allocation with drift-threshold rebalance."""

from __future__ import annotations

import pandas as pd


class ETFFixedIncomePlusRebalance:
    """Daily drift-check rebalancing for a fixed ETF weight basket."""

    multi_asset = True
    sell_first_same_bar = True

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
        target_weights: dict[str, float] | None = None,
        rebalance_threshold: float = 0.15,
        min_history: int = 5,
    ):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFFixedIncomePlusRebalance")
        self.etf_pool = [self._norm(code) for code in etf_pool]
        self.rebalance_threshold = float(rebalance_threshold)
        self.min_history = int(min_history)

        weights = target_weights or {
            "510880.XSHG": 0.08,
            "513100.XSHG": 0.08,
            "518880.XSHG": 0.14,
            "511010.XSHG": 0.70,
        }
        total = float(sum(max(0.0, float(v)) for v in weights.values()))
        if total <= 0:
            raise ValueError("target_weights must have positive sum")
        self.target_weights = {
            self._norm(k): max(0.0, float(v)) / total
            for k, v in weights.items()
        }

    def _effective_target(self, columns: list[str]) -> pd.Series:
        values = {c: float(self.target_weights.get(c, 0.0)) for c in columns}
        s = pd.Series(values, dtype=float)
        total = float(s.sum())
        if total <= 0:
            return s
        return s / total

    def generate_target_weights(self, close_panel: pd.DataFrame) -> pd.DataFrame:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]
        weights_df = pd.DataFrame(index=panel.index, columns=panel.columns, dtype=float)
        if panel.empty:
            return weights_df

        returns = panel.pct_change(fill_method=None)
        target = self._effective_target(list(panel.columns))
        if float(target.sum()) <= 0:
            return weights_df

        current = None
        for idx, date in enumerate(panel.index):
            if idx < self.min_history:
                continue

            if current is None:
                current = target.copy()
                weights_df.loc[date, target.index] = target.values
                continue

            day_ret = returns.iloc[idx].fillna(0.0)
            grown = current * (1.0 + day_ret)
            grown = grown.clip(lower=0.0)
            grown_sum = float(grown.sum())
            if grown_sum <= 0:
                current = target.copy()
                weights_df.loc[date, target.index] = target.values
                continue

            current = grown / grown_sum
            drift = (current - target).abs()
            if drift.max() > self.rebalance_threshold:
                current = target.copy()
                weights_df.loc[date, target.index] = target.values

        return weights_df
