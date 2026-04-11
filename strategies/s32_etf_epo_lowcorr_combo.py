"""
EPO-Optimized Low-Correlation ETF Combination.

Adapted from `2025strategy/32EPO优化低相关etf组合.txt`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ETFEpoLowCorrCombo:
    """Monthly EPO weights over ETF pool."""

    multi_asset = True

    def __init__(self,
                 etf_pool: list[str],
                 lookback: int = 250,
                 lambda_: float = 10.0,
                 shrink_w: float = 0.6,
                 min_history: int = 30):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFEpoLowCorrCombo")
        self.etf_pool = etf_pool
        self.lookback = int(lookback)
        self.lambda_ = float(lambda_)
        self.shrink_w = float(shrink_w)
        self.min_history = int(min_history)

    @staticmethod
    def _first_trading_day_mask(index: pd.Index) -> np.ndarray:
        # Rebalance only on first trading day of each month.
        months = pd.Series(index=index, data=index.to_period('M'))
        return (months != months.shift(1)).values

    def _epo_weights(self, returns: pd.DataFrame) -> pd.Series | None:
        # Produce long-only normalized EPO weights on selected universe.
        n = returns.shape[1]
        if n == 0:
            return None

        vcov = returns.cov().values
        corr = returns.corr().values
        if np.any(~np.isfinite(vcov)) or np.any(~np.isfinite(corr)):
            return None

        diag = np.diag(vcov)
        if np.any(diag <= 0):
            return None

        signal = (1.0 / diag)
        signal = signal / signal.sum()

        identity = np.eye(n)
        std = np.diag(np.sqrt(diag))
        shrunk_cor = (1.0 - self.shrink_w) * corr + self.shrink_w * identity
        cov_tilde = std @ shrunk_cor @ std

        try:
            inv_cov_tilde = np.linalg.solve(cov_tilde, identity)
        except np.linalg.LinAlgError:
            inv_cov_tilde = np.linalg.pinv(cov_tilde)

        epo_vec = (1.0 / self.lambda_) * (inv_cov_tilde @ signal)
        epo_vec = np.where(epo_vec < 0, 0.0, epo_vec)
        if epo_vec.sum() <= 0:
            return None
        epo_vec = epo_vec / epo_vec.sum()

        return pd.Series(epo_vec, index=returns.columns)

    def generate_target_weights(self, close_panel: pd.DataFrame) -> pd.DataFrame:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        weights_df = pd.DataFrame(index=panel.index, columns=panel.columns, dtype=float)
        if panel.empty:
            return weights_df

        first_day_mask = self._first_trading_day_mask(panel.index)

        for idx in range(len(panel)):
            if not first_day_mask[idx]:
                continue
            if idx < self.min_history:
                continue

            hist = panel.iloc[max(0, idx - self.lookback + 1):idx + 1]
            current_row = panel.iloc[idx]
            listed_cols = [
                c for c in hist.columns
                if pd.notna(current_row.get(c))
            ]
            if not listed_cols:
                continue
            hist = hist[listed_cols]

            valid_cols = [
                c for c in hist.columns
                if hist[c].dropna().shape[0] >= 2
            ]
            if not valid_cols:
                continue

            prices = hist[valid_cols]
            returns = prices.pct_change(fill_method=None).dropna(how='any')
            if returns.empty:
                continue

            weights = self._epo_weights(returns)
            if weights is None or weights.empty:
                continue

            # Write only rebalance-date weights; non-rebalance days remain NaN.
            weights_df.loc[panel.index[idx], weights.index] = weights.values

        return weights_df
