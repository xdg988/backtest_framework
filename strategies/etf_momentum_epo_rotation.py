"""
ETF Momentum Rotation with EPO-style weight selection.

Adapted from JoinQuant strategy idea in
`17多品种ETF动量轮动+EPO优化.txt`:
- Rank ETFs by momentum score (annualized return * R-squared)
- Keep top-N positive-score ETFs
- Use anchored EPO-like optimization to pick the highest-weight target ETF
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ETFMomentumEPORotation:
    """Generate daily target ETF code using momentum + EPO-like selection."""

    multi_asset = True

    def __init__(self,
                 etf_pool: list[str],
                 m_days: int = 34,
                 stock_num: int = 3,
                 epo_lookback: int = 240,
                 lambda_: float = 10.0,
                 w: float = 0.2,
                 min_score: float = 0.0):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFMomentumEPORotation")
        self.etf_pool = etf_pool
        self.m_days = int(m_days)
        self.stock_num = int(stock_num)
        self.epo_lookback = int(epo_lookback)
        self.lambda_ = float(lambda_)
        self.w = float(w)
        self.min_score = float(min_score)

    def _momentum_score(self, window: pd.Series) -> float:
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

    def _epo_pick(self, returns: pd.DataFrame) -> str | None:
        if returns.empty or returns.shape[1] == 0:
            return None
        if returns.shape[1] == 1:
            return returns.columns[0]

        cov = returns.cov().values
        if np.any(~np.isfinite(cov)):
            return None

        signal = returns.mean().values
        if np.any(~np.isfinite(signal)):
            return None

        diag = np.diag(cov)
        if np.any(diag <= 0):
            return None

        inv_diag = 1.0 / diag
        anchor = inv_diag / inv_diag.sum()

        std = np.sqrt(diag)
        corr = returns.corr().values
        identity = np.eye(corr.shape[0])
        shrunk_corr = (1 - self.w) * corr + self.w * identity
        cov_tilde = np.diag(std) @ shrunk_corr @ np.diag(std)

        try:
            inv_cov_tilde = np.linalg.solve(cov_tilde, np.eye(cov_tilde.shape[0]))
        except np.linalg.LinAlgError:
            inv_cov_tilde = np.linalg.pinv(cov_tilde)

        gamma_num = np.sqrt(float(anchor.T @ cov_tilde @ anchor))
        gamma_den = np.sqrt(float(signal.T @ inv_cov_tilde @ cov_tilde @ inv_cov_tilde @ signal))
        if gamma_den == 0:
            return None
        gamma = gamma_num / gamma_den

        epo_vec = inv_cov_tilde @ (((1 - self.w) * gamma * signal) + (self.w * (np.diag(diag) @ anchor)))
        epo_vec = np.where(epo_vec < 0, 0, epo_vec)
        if epo_vec.sum() <= 0:
            return None
        weights = epo_vec / epo_vec.sum()
        return returns.columns[int(np.argmax(weights))]

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        target = pd.Series(index=panel.index, dtype='object')
        min_hist = max(self.m_days, self.epo_lookback)

        for idx in range(min_hist - 1, len(panel)):
            hist = panel.iloc[idx - min_hist + 1: idx + 1]
            momentum_hist = hist.iloc[-self.m_days:]

            scores = {
                code: self._momentum_score(momentum_hist[code])
                for code in momentum_hist.columns
            }
            score_s = pd.Series(scores).dropna()
            score_s = score_s[score_s > self.min_score].sort_values(ascending=False)
            if score_s.empty:
                continue

            selected = score_s.index[:max(1, self.stock_num)].tolist()
            if len(selected) == 1:
                target.iloc[idx] = selected[0]
                continue

            returns = hist[selected].pct_change(fill_method=None).dropna()
            picked = self._epo_pick(returns)
            target.iloc[idx] = picked if picked is not None else selected[0]

        return target
