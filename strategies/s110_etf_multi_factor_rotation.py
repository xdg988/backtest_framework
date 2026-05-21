"""ETF multi-factor rotation strategy (weight-based)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from factors import (
    build_unified_etf_factor_data,
    prepare_financial_factor_data,
    score_etf_cross_section,
    select_top_etfs,
)


class ETFMultiFactorRotation:
    """Generate target weights for ETF rotation using cross-sectional multi-factor scores."""

    multi_asset = True
    signal_price_field = "close"

    @staticmethod
    def _norm(code: str) -> str:
        if not isinstance(code, str):
            return code
        c = code.strip().upper()
        if c.endswith(".XSHG"):
            return c.replace(".XSHG", ".SH")
        if c.endswith(".XSHE"):
            return c.replace(".XSHE", ".SZ")
        return c

    def __init__(
        self,
        etf_pool: list[str],
        top_n: int = 3,
        rebalance: str = "monthly",
        min_score: float | None = None,
        weight_method: str = "equal",
        momentum_windows: Sequence[int] = (60,),
        volatility_windows: Sequence[int] = (60,),
        momentum_regression_windows: Sequence[int] = (25,),
        turnover_window: int = 20,
        factor_weights: Mapping[str, float] | None = None,
        factor_directions: Mapping[str, int] | None = None,
        factor_whitelist: Sequence[str] | None = None,
        financial_factors: Mapping[str, object] | None = None,
        fill_value: float = 0.0,
        drop_missing_factors: bool = False,
    ):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFMultiFactorRotation")
        self.etf_pool = [self._norm(code) for code in etf_pool]

        self.top_n = max(1, int(top_n))
        self.rebalance = str(rebalance or "monthly").lower()
        self.min_score = None if min_score is None else float(min_score)
        self.weight_method = str(weight_method or "equal").lower()

        self.momentum_windows = tuple(int(x) for x in momentum_windows)
        self.volatility_windows = tuple(int(x) for x in volatility_windows)
        self.momentum_regression_windows = tuple(int(x) for x in momentum_regression_windows)
        self.turnover_window = int(turnover_window)

        self.factor_weights = dict(factor_weights) if factor_weights else None
        self.factor_directions = dict(factor_directions) if factor_directions else None
        self.factor_whitelist = tuple(factor_whitelist) if factor_whitelist else None
        self.financial_factors = dict(financial_factors) if financial_factors else {}
        self.fill_value = float(fill_value)
        self.drop_missing_factors = bool(drop_missing_factors)

        self.market_data: dict[str, pd.DataFrame] = {}
        self.financial_factor_data = pd.DataFrame()
        self._financial_factor_prepared = False
        self._runtime_token: str | None = None
        self._runtime_start: str | None = None
        self._runtime_end: str | None = None

        max_window = max(
            max(self.momentum_windows) if self.momentum_windows else 1,
            max(self.volatility_windows) if self.volatility_windows else 1,
            max(self.momentum_regression_windows) if self.momentum_regression_windows else 1,
        )
        self.warmup_bars = max(30, max_window + 5)

        # 调试/可解释性：保留最近一次评分中间表。
        self.last_factor_data = pd.DataFrame()
        self.last_scored = pd.DataFrame()
        self.last_positions = pd.DataFrame()

    def set_market_data(self, data_map: dict[str, pd.DataFrame]):
        """Inject market OHLCV data, used to build optional volume/amount factor panels."""
        normalized = {}
        for code, df in (data_map or {}).items():
            norm_code = self._norm(code)
            item = df.copy()
            if not isinstance(item.index, pd.DatetimeIndex):
                item.index = pd.to_datetime(item.index, errors="coerce")
            item = item[~item.index.isna()].sort_index()
            normalized[norm_code] = item
        self.market_data = normalized

    def set_financial_factor_data(self, financial_factor_data: pd.DataFrame):
        """Inject pre-aggregated ETF financial factor data (trade_date, ts_code, factor columns)."""
        if financial_factor_data is None:
            self.financial_factor_data = pd.DataFrame()
            return
        item = financial_factor_data.copy()
        if "trade_date" in item.columns:
            item["trade_date"] = pd.to_datetime(item["trade_date"], errors="coerce")
        self.financial_factor_data = item
        self._financial_factor_prepared = True

    def set_runtime_context(self, token: str | None, start: str | None, end: str | None):
        """Inject runtime context for optional data pipelines.

        This keeps run_backtest generic: strategy decides whether to use the context.
        """
        self._runtime_token = token
        self._runtime_start = start
        self._runtime_end = end

    def _ensure_financial_factor_data(self, trading_index: pd.DatetimeIndex):
        """Prepare financial factors on first use and cache in-memory."""
        if self._financial_factor_prepared:
            return

        self._financial_factor_prepared = True
        try:
            built = prepare_financial_factor_data(
                financial_factors=self.financial_factors,
                token=self._runtime_token,
                start_date=self._runtime_start,
                end_date=self._runtime_end,
                trading_index=trading_index,
                etf_pool=self.etf_pool,
            )
            self.set_financial_factor_data(built)
        except Exception as e:
            print(f"financial factor pipeline failed, fallback to market-only: {e}")
            self.financial_factor_data = pd.DataFrame()

    @staticmethod
    def _rebalance_mask(index: pd.DatetimeIndex, rebalance: str) -> pd.Series:
        if len(index) == 0:
            return pd.Series(dtype=bool)

        mode = (rebalance or "monthly").lower()
        if mode in {"daily", "d"}:
            return pd.Series(True, index=index)
        if mode in {"weekly", "w"}:
            periods = pd.Series(index=index, data=index.to_period("W-FRI"))
            return periods != periods.shift(1)
        if mode in {"monthly", "m"}:
            periods = pd.Series(index=index, data=index.to_period("M"))
            return periods != periods.shift(1)

        raise ValueError("rebalance must be one of: daily/weekly/monthly")

    def _build_aux_panels(self, close_panel: pd.DataFrame) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
        """Build aligned volume/float_share panels from injected market data."""
        if not self.market_data:
            return None, None

        vol_dict: dict[str, pd.Series] = {}
        float_share_dict: dict[str, pd.Series] = {}
        for code in close_panel.columns:
            item = self.market_data.get(code)
            if item is None or item.empty:
                continue

            if "vol" in item.columns:
                vol_dict[code] = item["vol"].reindex(close_panel.index)
            if "float_share" in item.columns:
                float_share_dict[code] = item["float_share"].reindex(close_panel.index)

        volume_panel = pd.DataFrame(vol_dict).reindex(index=close_panel.index) if vol_dict else None
        float_share_panel = pd.DataFrame(float_share_dict).reindex(index=close_panel.index) if float_share_dict else None
        return volume_panel, float_share_panel

    def generate_target_weights(self, close_panel: pd.DataFrame) -> pd.DataFrame:
        """Generate target weights on rebalance dates.

        Output format matches WeightRotationBacktestStrategy expectation:
        - index: trade_date
        - columns: ETF codes
        - values: target weights on rebalance days, NaN otherwise
        """
        panel = close_panel.copy()
        panel = panel[[code for code in self.etf_pool if code in panel.columns]].sort_index()

        weights_df = pd.DataFrame(index=panel.index, columns=panel.columns, dtype=float)
        if panel.empty:
            return weights_df

        self._ensure_financial_factor_data(panel.index)

        volume_panel, float_share_panel = self._build_aux_panels(panel)

        factor_data = build_unified_etf_factor_data(
            close_panel=panel,
            volume_panel=volume_panel,
            float_share_panel=float_share_panel,
            momentum_windows=self.momentum_windows,
            volatility_windows=self.volatility_windows,
            momentum_regression_windows=self.momentum_regression_windows,
            turnover_window=self.turnover_window,
            financial_factor_data=self.financial_factor_data,
        )
        if factor_data.empty:
            self.last_factor_data = factor_data
            self.last_scored = pd.DataFrame()
            self.last_positions = pd.DataFrame()
            return weights_df

        scored = score_etf_cross_section(
            factor_data=factor_data,
            factor_weights=self.factor_weights,
            factor_directions=self.factor_directions,
            whitelist=self.factor_whitelist,
            fill_value=self.fill_value,
            drop_missing_factors=self.drop_missing_factors,
        )
        positions = select_top_etfs(
            scored_data=scored,
            top_n=self.top_n,
            min_score=self.min_score,
            weight_method=self.weight_method,
        )

        self.last_factor_data = factor_data
        self.last_scored = scored
        self.last_positions = positions

        if positions.empty:
            return weights_df

        rebalance_mask = self._rebalance_mask(panel.index, self.rebalance)
        rebalance_dates = set(panel.index[rebalance_mask.values])

        rebalance_positions = positions[positions["trade_date"].isin(rebalance_dates)]
        if rebalance_positions.empty:
            return weights_df

        pivot = rebalance_positions.pivot(index="trade_date", columns="ts_code", values="weight")
        pivot = pivot.reindex(index=panel.index, columns=panel.columns)

        # 仅在调仓日写入目标权重，非调仓日保留 NaN（执行层会视为不触发调仓）。
        for dt in pivot.index:
            row = pivot.loc[dt]
            valid = row.dropna()
            if valid.empty:
                continue
            total = float(valid.sum())
            if total <= 0:
                continue
            weights_df.loc[dt, valid.index] = (valid / total).values

        return weights_df


__all__ = ["ETFMultiFactorRotation"]
