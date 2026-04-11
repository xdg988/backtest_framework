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
    fill_vacancy_only = True

    def __init__(
        self,
        etf_pool: list[str],
        etf_num: int = 2,
        change_day: int = 1,
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
        self.change_day = max(1, int(change_day))
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

    def _select_holdings(self, panel: pd.DataFrame) -> list[list[str]]:
        """Select holdings per day for true top-N simultaneous holding.

        Rebalance only every ``change_day`` bars and never re-buy symbols sold
        on the same rebalance day.
        """
        daily_holdings: list[list[str]] = [[] for _ in range(len(panel))]
        holdings: list[str] = []
        rebalance_clock = 0

        # Match JQ attribute_history behavior in run_daily trade: use prior-day
        # bars only for today's signal, i.e. exclude current bar from window.
        for idx in range(self.longdays, len(panel)):
            if rebalance_clock % self.change_day != 0:
                daily_holdings[idx] = holdings.copy()
                rebalance_clock += 1
                continue

            hist = panel.iloc[:idx]
            metrics = self._calc_metrics(hist)
            if metrics.empty:
                daily_holdings[idx] = holdings.copy()
                rebalance_clock += 1
                continue

            rank_etf = list(metrics.index)[: self.rank_num]
            buy_pool = metrics[
                (metrics["mashort"] > metrics["malong"])
                & (metrics["inc"] > self.min_inc)
                & (metrics["inc"] < self.max_inc)
            ]
            buy_list = list(buy_pool.index)[: self.etf_num]

            if not holdings:
                holdings = buy_list[: self.etf_num]
                daily_holdings[idx] = holdings.copy()
                rebalance_clock += 1
                continue

            sell_set: set[str] = set()
            for code in holdings:
                if code not in metrics.index:
                    sell_set.add(code)
                    continue
                inc = float(metrics.loc[code, "inc"])
                if (code not in rank_etf) or (inc > self.max_inc):
                    sell_set.add(code)

            kept: list[str] = [code for code in holdings if code not in sell_set]

            for code in buy_list:
                if code in kept:
                    continue
                if code in sell_set:
                    continue
                if len(kept) >= self.etf_num:
                    break
                kept.append(code)

            holdings = kept
            daily_holdings[idx] = holdings.copy()
            rebalance_clock += 1

        return daily_holdings

    def generate_target_weights(self, close_panel: pd.DataFrame) -> pd.DataFrame:
        """Generate equal-weight top-N targets for multi-asset simultaneous holding."""
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        weights = pd.DataFrame(index=panel.index, columns=panel.columns, dtype=float)
        self.cash_dates: set[pd.Timestamp] = set()
        self.target_lists_by_date: dict[pd.Timestamp, list[str]] = {}
        if panel.empty:
            return weights

        daily_holdings = self._select_holdings(panel)
        for idx, holdings in enumerate(daily_holdings):
            self.target_lists_by_date[panel.index[idx]] = holdings.copy()
            if not holdings:
                if idx >= self.longdays - 1:
                    self.cash_dates.add(panel.index[idx])
                continue
            w = 1.0 / len(holdings)
            for code in holdings:
                if code in weights.columns:
                    weights.iloc[idx, weights.columns.get_loc(code)] = w

        return weights

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        """Backward-compatible single target: pick the highest-weight symbol each day."""
        weights = self.generate_target_weights(close_panel)

        target = pd.Series(index=weights.index, dtype="object")
        for idx in range(len(weights)):
            row = weights.iloc[idx].dropna()
            if row.empty:
                target.iloc[idx] = None
            else:
                target.iloc[idx] = row.sort_values(ascending=False).index[0]

        return target
