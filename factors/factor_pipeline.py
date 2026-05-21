"""Unified factor pipeline helpers for ETF multi-factor strategies."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from data_loader.data_loader import normalize_ts_code
from data_loader.multi_factor_data_loader import (
    build_daily_constituent_weight_snapshot,
    build_daily_financial_snapshot,
    fetch_balancesheet_statements,
    fetch_income_statements,
    fetch_index_weight,
)

from .factor_merge import merge_factor_tables
from .financial_factors import build_constituent_financial_factor_data
from .market_factors import build_etf_factor_data


def _to_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def prepare_financial_factor_data(
    financial_factors: Mapping[str, object] | None,
    token: str | None,
    start_date: str | None,
    end_date: str | None,
    trading_index: pd.DatetimeIndex,
    etf_pool: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Build constituent-aggregated ETF financial factor table from strategy config."""
    cfg = dict(financial_factors or {})
    if not _to_bool(cfg.get("enabled", False), default=False):
        return pd.DataFrame()

    idx = pd.DatetimeIndex(trading_index)
    if idx.empty:
        return pd.DataFrame()

    start = start_date or idx.min().strftime("%Y%m%d")
    end = end_date or idx.max().strftime("%Y%m%d")

    etf_to_index_map = dict(cfg.get("etf_to_index_map") or {})
    if etf_pool:
        normalized_pool = {normalize_ts_code(code) for code in etf_pool}
        etf_to_index_map = {k: v for k, v in etf_to_index_map.items() if normalize_ts_code(k) in normalized_pool}
    if not etf_to_index_map:
        return pd.DataFrame()

    normalized_map = {normalize_ts_code(etf): normalize_ts_code(index) for etf, index in etf_to_index_map.items()}
    index_codes = sorted(set(normalized_map.values()))
    if not index_codes:
        return pd.DataFrame()

    index_weight_frames: list[pd.DataFrame] = []
    for index_code in index_codes:
        try:
            frame = fetch_index_weight(index_code=index_code, start_date=start, end_date=end, token=token)
        except Exception as e:
            print(f"fetch_index_weight failed for {index_code}: {e}")
            frame = pd.DataFrame()
        if frame is not None and not frame.empty:
            index_weight_frames.append(frame)

    if not index_weight_frames:
        return pd.DataFrame()

    index_weight_df = pd.concat(index_weight_frames, ignore_index=True)
    index_weight_daily = build_daily_constituent_weight_snapshot(
        index_weight_df=index_weight_df,
        start_date=start,
        end_date=end,
        trading_index=idx,
    )
    if index_weight_daily.empty:
        return pd.DataFrame()

    constituent_codes = sorted(set(index_weight_daily["con_code"].dropna().astype(str)))
    if not constituent_codes:
        return pd.DataFrame()

    date_priority = cfg.get("date_priority") or ["ann_date", "f_ann_date", "end_date"]
    use_income_only = _to_bool(cfg.get("use_income_only", False), default=False)
    selected_fields = dict(cfg.get("fields") or {})

    income_fields = ",".join(
        [
            "ts_code", "ann_date", "f_ann_date", "end_date",
            "n_income_attr_p", "n_income", "dtprofit", "q_dtprofit",
        ]
    )
    income_df = fetch_income_statements(
        ts_codes=constituent_codes,
        start_date=start,
        end_date=end,
        token=token,
        fields=income_fields,
    )
    income_snapshot_daily = build_daily_financial_snapshot(
        financial_df=income_df,
        start_date=start,
        end_date=end,
        trading_index=idx,
        id_column="ts_code",
        date_priority=date_priority,
        value_columns=["n_income_attr_p", "n_income", "dtprofit", "q_dtprofit"],
    )

    balancesheet_snapshot_daily = pd.DataFrame()
    if not use_income_only:
        balance_fields = ",".join(
            [
                "ts_code", "ann_date", "f_ann_date", "end_date",
                "total_hldr_eqy_exc_min_int", "total_hldr_eqy_inc_min_int", "total_hldr_eqy",
                "total_cur_assets", "total_assets",
            ]
        )
        balance_df = fetch_balancesheet_statements(
            ts_codes=constituent_codes,
            start_date=start,
            end_date=end,
            token=token,
            fields=balance_fields,
        )
        balancesheet_snapshot_daily = build_daily_financial_snapshot(
            financial_df=balance_df,
            start_date=start,
            end_date=end,
            trading_index=idx,
            id_column="ts_code",
            date_priority=date_priority,
            value_columns=[
                "total_hldr_eqy_exc_min_int",
                "total_hldr_eqy_inc_min_int",
                "total_hldr_eqy",
                "total_cur_assets",
                "total_assets",
            ],
        )

    financial_factor_data = build_constituent_financial_factor_data(
        index_weight_daily=index_weight_daily,
        income_snapshot_daily=income_snapshot_daily,
        balancesheet_snapshot_daily=balancesheet_snapshot_daily,
        etf_to_index_map=normalized_map,
        coverage_threshold=float(cfg.get("coverage_threshold", 0.6)),
    )

    # 支持按配置仅启用部分财务因子字段。
    enabled_factor_cols = [k for k, v in selected_fields.items() if _to_bool(v, default=False)]
    if enabled_factor_cols and not financial_factor_data.empty:
        base_cols = ["trade_date", "ts_code"]
        keep_cols = base_cols + [c for c in enabled_factor_cols if c in financial_factor_data.columns]
        financial_factor_data = financial_factor_data[keep_cols].copy()

    return financial_factor_data


def build_unified_etf_factor_data(
    close_panel: pd.DataFrame,
    volume_panel: pd.DataFrame | None = None,
    float_share_panel: pd.DataFrame | None = None,
    momentum_windows: Iterable[int] | None = None,
    volatility_windows: Iterable[int] | None = None,
    momentum_regression_windows: Iterable[int] | None = None,
    turnover_window: int = 20,
    financial_factor_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build unified ETF factor table via one call.

    This function keeps strategy-side usage concise by combining:
    1) market factor construction
    2) optional extra factor merge (e.g. financial factors)
    """
    market_factor_data = build_etf_factor_data(
        close_panel=close_panel,
        volume_panel=volume_panel,
        float_share_panel=float_share_panel,
        momentum_windows=momentum_windows,
        volatility_windows=volatility_windows,
        momentum_regression_windows=momentum_regression_windows,
        turnover_window=turnover_window,
    )
    return merge_factor_tables(
        market_factor_data=market_factor_data,
        extra_factor_data=financial_factor_data,
    )


__all__ = ["build_unified_etf_factor_data", "prepare_financial_factor_data"]
