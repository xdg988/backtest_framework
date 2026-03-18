"""
ETF MA + Momentum range rotation.

Adapted from `2025strategy/58Debug-输出信息-多标的版ETF策略(ETF复现之三）.txt`:
- Candidate filter: short MA > long MA
- Momentum window return should be in [min_inc, max_inc]
- Buy top-N momentum ETFs from filtered candidates
- Sell if out of rank window or momentum overheats
"""

from __future__ import annotations

import pandas as pd


class ETFMAMomentumRotation:
    """Daily top-N ETF rotation with MA and momentum-range filter."""

    multi_asset = True

    def __init__(
        self,
        etf_pool: list[str],
        etf_num: int = 2,
        rank_num: int = 4,
        longdays: int = 20,
        shortdays: int = 5,
        min_inc: float = 0.05,
        max_inc: float = 0.2,
    ):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFMAMomentumRotation")
        self.etf_pool = etf_pool
        self.etf_num = int(etf_num)
        self.rank_num = int(rank_num)
        self.longdays = int(longdays)
        self.shortdays = int(shortdays)
        self.min_inc = float(min_inc)
        self.max_inc = float(max_inc)

    def _calc_metrics(self, hist: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for code in hist.columns:
            series = hist[code].dropna()
            if len(series) < self.longdays:
                continue
            window = series.iloc[-self.longdays:]
            start = float(window.iloc[0])
            end = float(window.iloc[-1])
            if start <= 0:
                continue
            inc = end / start - 1.0
            malong = float(window.mean())
            mashort = float(window.iloc[-self.shortdays:].mean())
            rows.append((code, inc, malong, mashort))

        if not rows:
            return pd.DataFrame(columns=["inc", "malong", "mashort"])

        df = pd.DataFrame(rows, columns=["code", "inc", "malong", "mashort"]).set_index("code")
        return df.sort_values("inc", ascending=False)

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        target = pd.Series(index=panel.index, dtype="object")
        holding = None

        for idx in range(self.longdays - 1, len(panel)):
            hist = panel.iloc[: idx + 1]
            metrics = self._calc_metrics(hist)
            if metrics.empty:
                target.iloc[idx] = holding
                continue

            rank_etf = list(metrics.index)[: self.rank_num]
            buy_pool = metrics[
                (metrics["mashort"] > metrics["malong"])
                & (metrics["inc"] > self.min_inc)
                & (metrics["inc"] < self.max_inc)
            ]
            buy_list = list(buy_pool.index)[: self.etf_num]

            if holding is None:
                holding = buy_list[0] if buy_list else None
            else:
                should_sell = (holding not in rank_etf) or (
                    holding in metrics.index and float(metrics.loc[holding, "inc"]) > self.max_inc
                )
                if should_sell:
                    holding = None
                if holding is None and buy_list:
                    holding = buy_list[0]

            target.iloc[idx] = holding

        return target
