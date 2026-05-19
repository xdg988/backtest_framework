"""Constituent-based financial factor aggregation for ETF strategies."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd


def build_constituent_financial_factor_data(
    index_weight_daily: pd.DataFrame,
    income_snapshot_daily: pd.DataFrame,
    balancesheet_snapshot_daily: pd.DataFrame,
    etf_to_index_map: Mapping[str, str],
    coverage_threshold: float = 0.6,
) -> pd.DataFrame:
    """Aggregate stock-level financial snapshots into ETF-level financial factors.

    Output columns
    --------------
    - roe_qoq_growth
    - dtprofit_qoq_growth_rate
    - cur_asset_ratio_qoq_growth
    """
    factor_cols = [
        "roe_qoq_growth",
        "dtprofit_qoq_growth_rate",
        "cur_asset_ratio_qoq_growth",
    ]
    empty = pd.DataFrame(columns=["trade_date", "ts_code", *factor_cols])

    # 没有 ETF->指数映射时无法做成分聚合，直接返回空表。
    if not etf_to_index_map:
        return empty
    if index_weight_daily is None or index_weight_daily.empty:
        return empty

    weights = index_weight_daily.copy()
    for col in ("trade_date", "index_code", "con_code", "weight"):
        if col not in weights.columns:
            raise ValueError(f"index_weight_daily missing required column: {col}")
    weights["trade_date"] = pd.to_datetime(weights["trade_date"], errors="coerce")
    weights = weights.dropna(subset=["trade_date", "index_code", "con_code", "weight"]).copy()

    income = income_snapshot_daily.copy() if income_snapshot_daily is not None else pd.DataFrame()
    balance = balancesheet_snapshot_daily.copy() if balancesheet_snapshot_daily is not None else pd.DataFrame()
    for frame in (income, balance):
        if not frame.empty:
            if "trade_date" not in frame.columns or "ts_code" not in frame.columns:
                raise ValueError("financial snapshot data must contain trade_date and ts_code")
            frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
            frame["ts_code"] = frame["ts_code"].astype(str)

    stock_fin = pd.DataFrame(columns=["trade_date", "ts_code"])
    if not income.empty:
        stock_fin = income[["trade_date", "ts_code"]].drop_duplicates().copy()
    if not balance.empty:
        bs_idx = balance[["trade_date", "ts_code"]].drop_duplicates()
        if stock_fin.empty:
            stock_fin = bs_idx.copy()
        else:
            stock_fin = stock_fin.merge(bs_idx, on=["trade_date", "ts_code"], how="outer")

    if stock_fin.empty:
        return empty

    # 1) ROE 环比增长：先算 ROE，再按个股做环比增长率。
    if not income.empty and not balance.empty:
        income_parent_profit_col = _pick_first_column(income, ["n_income_attr_p", "n_income"])
        parent_equity_col = _pick_first_column(balance, ["total_hldr_eqy_exc_min_int", "total_hldr_eqy_inc_min_int", "total_hldr_eqy"])
        if income_parent_profit_col and parent_equity_col:
            roe_base = income[["trade_date", "ts_code", income_parent_profit_col]].merge(
                balance[["trade_date", "ts_code", parent_equity_col]],
                on=["trade_date", "ts_code"],
                how="inner",
            )
            roe_base[income_parent_profit_col] = pd.to_numeric(roe_base[income_parent_profit_col], errors="coerce")
            roe_base[parent_equity_col] = pd.to_numeric(roe_base[parent_equity_col], errors="coerce")
            roe_base["roe"] = roe_base[income_parent_profit_col] / roe_base[parent_equity_col]
            roe_base["roe_qoq_growth"] = _build_qoq_growth_by_symbol(roe_base, value_col="roe")
            stock_fin = stock_fin.merge(
                roe_base[["trade_date", "ts_code", "roe_qoq_growth"]],
                on=["trade_date", "ts_code"],
                how="left",
            )

    # 2) 归母扣非净利润环比增长率（优先 dtprofit/q_dtprofit）。
    if not income.empty:
        dtprofit_col = _pick_first_column(income, ["dtprofit", "q_dtprofit"])
        if dtprofit_col is None:
            dtprofit_col = _pick_first_column(income, ["n_income_attr_p", "n_income"])
        if dtprofit_col:
            dt = income[["trade_date", "ts_code", dtprofit_col]].copy()
            dt[dtprofit_col] = pd.to_numeric(dt[dtprofit_col], errors="coerce")
            dt["dtprofit_qoq_growth_rate"] = _build_qoq_growth_by_symbol(dt, value_col=dtprofit_col)
            stock_fin = stock_fin.merge(
                dt[["trade_date", "ts_code", "dtprofit_qoq_growth_rate"]],
                on=["trade_date", "ts_code"],
                how="left",
            )

    # 3) 流动资产比例环比增长：先算 total_cur_assets/total_assets，再做环比增长率。
    if not balance.empty:
        cur_assets_col = _pick_first_column(balance, ["total_cur_assets"])
        total_assets_col = _pick_first_column(balance, ["total_assets"])
        if cur_assets_col and total_assets_col:
            cur = balance[["trade_date", "ts_code", cur_assets_col, total_assets_col]].copy()
            cur[cur_assets_col] = pd.to_numeric(cur[cur_assets_col], errors="coerce")
            cur[total_assets_col] = pd.to_numeric(cur[total_assets_col], errors="coerce")
            cur["cur_asset_ratio"] = cur[cur_assets_col] / cur[total_assets_col]
            cur["cur_asset_ratio_qoq_growth"] = _build_qoq_growth_by_symbol(cur, value_col="cur_asset_ratio")
            stock_fin = stock_fin.merge(
                cur[["trade_date", "ts_code", "cur_asset_ratio_qoq_growth"]],
                on=["trade_date", "ts_code"],
                how="left",
            )

    etf_map = {str(etf): str(index) for etf, index in dict(etf_to_index_map).items()}
    merged = weights.merge(
        stock_fin,
        left_on=["trade_date", "con_code"],
        right_on=["trade_date", "ts_code"],
        how="left",
    )

    threshold = max(0.0, min(1.0, float(coverage_threshold)))
    outputs: list[pd.DataFrame] = []

    # 对每个 ETF：按 index_weight 的权重对成分股因子做加权聚合。
    for etf_code, index_code in etf_map.items():
        subset = merged[merged["index_code"] == index_code].copy()
        if subset.empty:
            continue

        rows = []
        for trade_date, group in subset.groupby("trade_date"):
            row = {"trade_date": trade_date, "ts_code": etf_code}
            for factor in factor_cols:
                if factor not in group.columns:
                    row[factor] = np.nan
                    continue
                # 只在有效覆盖权重达到阈值时输出该因子，避免低覆盖导致噪声。
                valid = group.dropna(subset=[factor, "weight"])
                coverage = float(valid["weight"].sum()) if not valid.empty else 0.0
                if coverage < threshold or coverage <= 0:
                    row[factor] = np.nan
                else:
                    row[factor] = float((valid[factor] * valid["weight"]).sum() / coverage)
            rows.append(row)

        if rows:
            outputs.append(pd.DataFrame(rows))

    if not outputs:
        return empty

    out = pd.concat(outputs, ignore_index=True)
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce")
    out = out.dropna(subset=["trade_date", "ts_code"])
    out = out.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    return out


def _build_qoq_growth_by_symbol(
    df: pd.DataFrame,
    value_col: str,
    symbol_col: str = "ts_code",
    date_col: str = "trade_date",
) -> pd.Series:
    """Compute per-symbol QoQ growth rate and forward-fill between snapshot dates."""
    work = df[[symbol_col, date_col, value_col]].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.sort_values([symbol_col, date_col])

    results = pd.Series(index=work.index, dtype=float)
    for _, group in work.groupby(symbol_col):
        values = group[value_col]
        base = values.shift(1)
        growth_rate = (values - base) / base.abs()
        growth_rate = growth_rate.replace([np.inf, -np.inf], np.nan)
        growth_rate = growth_rate.ffill()
        results.loc[group.index] = growth_rate.values

    return results.reindex(df.index)


def _pick_first_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first existing column name from candidates."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


__all__ = ["build_constituent_financial_factor_data"]
