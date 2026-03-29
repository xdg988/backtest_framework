"""ETF momentum + anchored EPO (close to source strategy behavior)."""

from __future__ import annotations

import numpy as np
import pandas as pd


class ETFMomentumEPORotation:
    """Generate monthly target weights using momentum ranking + anchored EPO."""

    multi_asset = True
    sell_then_buy_recalc_cash = True

    def __init__(self,
                 etf_pool: list[str],
                 m_days: int = 34,
                 stock_num: int = 3,
                 epo_lookback: int = 1200,
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
        # First stage: rank candidates by momentum quality.
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
    def _first_trading_day_mask(index: pd.Index) -> pd.Series:
        months = pd.Series(index=index, data=index.to_period('M'))
        return months != months.shift(1)

    def _epo_weights(self, returns: pd.DataFrame) -> pd.Series | None:
        # Match source strategy: anchored EPO with endogenous gamma.
        if returns.empty or returns.shape[1] == 0:
            return None
        if returns.shape[1] == 1:
            return pd.Series([1.0], index=returns.columns)

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
        return pd.Series(weights, index=returns.columns)

    def generate_target_weights(self, close_panel: pd.DataFrame) -> pd.DataFrame:
        panel = close_panel.copy()
        panel = panel[[c for c in self.etf_pool if c in panel.columns]]

        weights_df = pd.DataFrame(index=panel.index, columns=panel.columns, dtype=float)
        if panel.empty:
            return weights_df

        month_start = self._first_trading_day_mask(panel.index)

        for idx in range(self.m_days - 1, len(panel)):
            if not bool(month_start.iloc[idx]):
                continue

            lookback = min(self.epo_lookback, idx + 1)
            hist = panel.iloc[idx - lookback + 1: idx + 1]
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
                weights_df.loc[panel.index[idx], selected[0]] = 1.0
                continue

            returns = hist[selected].pct_change(fill_method=None).dropna()
            weights = self._epo_weights(returns)
            if weights is None or weights.empty:
                weights_df.loc[panel.index[idx], selected[0]] = 1.0
            else:
                weights_df.loc[panel.index[idx], weights.index] = weights.values

        return weights_df

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        # Compatibility fallback for environments that still read single targets.
        weights = self.generate_target_weights(close_panel)
        target = pd.Series(index=weights.index, dtype='object')
        for idx in range(len(weights)):
            row = weights.iloc[idx].dropna()
            if row.empty:
                target.iloc[idx] = None
            else:
                target.iloc[idx] = row.sort_values(ascending=False).index[0]

        return target
