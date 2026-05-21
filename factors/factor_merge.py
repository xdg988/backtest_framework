"""Utilities for merging factor tables from different sources."""

from __future__ import annotations

import pandas as pd


def merge_factor_tables(
    market_factor_data: pd.DataFrame,
    extra_factor_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge market-derived factors with optional extra factor table.

    Parameters
    ----------
    market_factor_data
        Base factor table from market_factors (must contain trade_date/ts_code).
    extra_factor_data
        Optional table from other sources (e.g. constituent financial aggregation).

    Returns
    -------
    pd.DataFrame
        Merged factor table aligned by trade_date/ts_code.
    """
    if market_factor_data is None or market_factor_data.empty:
        return pd.DataFrame(columns=["trade_date", "ts_code"])

    base = market_factor_data.copy()
    required_cols = {"trade_date", "ts_code"}
    if not required_cols.issubset(base.columns):
        raise ValueError("market_factor_data must contain trade_date and ts_code columns")
    base["trade_date"] = pd.to_datetime(base["trade_date"], errors="coerce")
    base = base.dropna(subset=["trade_date", "ts_code"]).copy()
    base["ts_code"] = base["ts_code"].astype(str)

    if extra_factor_data is None or extra_factor_data.empty:
        return base.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)

    extra = extra_factor_data.copy()
    if not required_cols.issubset(extra.columns):
        raise ValueError("extra_factor_data must contain trade_date and ts_code columns")
    extra["trade_date"] = pd.to_datetime(extra["trade_date"], errors="coerce")
    extra = extra.dropna(subset=["trade_date", "ts_code"]).copy()
    extra["ts_code"] = extra["ts_code"].astype(str)

    merged = base.merge(
        extra,
        on=["trade_date", "ts_code"],
        how="left",
        suffixes=("", "_extra"),
    )
    return merged.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)


__all__ = ["merge_factor_tables"]
