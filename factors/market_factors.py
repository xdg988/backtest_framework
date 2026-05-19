"""ETF market-derived factor engineering helpers for rotation strategies.

该模块仅包含 ETF 行情可直接衍生的因子：
- 动量（momentum）
- 波动率（volatility）
- 动量回归（momentum_regression）
- 换手率（turnover）

成分股聚合财务因子已拆分到 `financial_factors.py`。
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


DEFAULT_MOMENTUM_WINDOWS = (5, 20, 60)
DEFAULT_VOLATILITY_WINDOWS = (20, 60)
DEFAULT_MOMENTUM_REGRESSION_WINDOWS = (25,)
DEFAULT_TURNOVER_WINDOW = 20


def _normalize_windows(windows: Iterable[int] | None, default: tuple[int, ...]) -> tuple[int, ...]:
    """规范窗口参数：去重、排序、过滤非正整数。"""
    values = tuple(sorted({int(window) for window in (windows or default) if int(window) > 0}))
    if not values:
        raise ValueError("at least one positive window is required")
    return values


def build_etf_factor_data(
    close_panel: pd.DataFrame,
    volume_panel: pd.DataFrame | None = None,
    float_share_panel: pd.DataFrame | None = None,
    momentum_windows: Iterable[int] | None = None,
    volatility_windows: Iterable[int] | None = None,
    momentum_regression_windows: Iterable[int] | None = None,
    turnover_window: int = DEFAULT_TURNOVER_WINDOW,
    financial_factor_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build ETF long-form factor table from wide market panels.

    Parameters
    ----------
    close_panel
        ETF 收盘价宽表（index 为交易日，columns 为 ETF 代码）。
    volume_panel
        ETF 成交量宽表（可选）。
    float_share_panel
        ETF 流通股本宽表（可选），用于换手率。
    momentum_windows, volatility_windows, momentum_regression_windows
        各类因子窗口。
    turnover_window
        换手率平滑窗口。
    financial_factor_data
        来自 financial_factors 的 ETF 财务因子长表（可选），会按 trade_date/ts_code 合并。
    """
    if close_panel is None or close_panel.empty:
        return pd.DataFrame(columns=["trade_date", "ts_code", "close"])

    momentum_windows = _normalize_windows(momentum_windows, DEFAULT_MOMENTUM_WINDOWS)
    volatility_windows = _normalize_windows(volatility_windows, DEFAULT_VOLATILITY_WINDOWS)
    momentum_regression_windows = _normalize_windows(
        momentum_regression_windows,
        DEFAULT_MOMENTUM_REGRESSION_WINDOWS,
    )
    turnover_window = int(turnover_window)
    if turnover_window <= 0:
        raise ValueError("turnover_window must be positive")

    close_panel = close_panel.sort_index().copy()
    factor_frames: list[pd.DataFrame] = []

    # 按 ETF 逐个计算因子，再拼成长表。
    for code in close_panel.columns:
        price_series = close_panel[code].dropna()
        if price_series.empty:
            continue

        df = pd.DataFrame({"trade_date": price_series.index, "ts_code": code, "close": price_series.values})
        df = df.sort_values("trade_date").reset_index(drop=True)

        # 1) 动量因子：N 日收益率。
        for window in momentum_windows:
            df[f"momentum_{window}"] = df["close"].pct_change(window)

        # 2) 波动率因子：日收益率 rolling std。
        returns = df["close"].pct_change()
        for window in volatility_windows:
            df[f"volatility_{window}"] = returns.rolling(window).std()

        # 3) 动量回归因子：参考 s14 的 momentum_score（年化收益 * 加权R²）。
        for window in momentum_regression_windows:
            df[f"momentum_regression_{window}"] = (
                df["close"]
                .rolling(window)
                .apply(_momentum_regression_score, raw=True)
            )

        # 4) 换手率因子：turnover_rate = volume / float_share。
        if volume_panel is not None and code in volume_panel.columns:
            volume_series = volume_panel[code].reindex(price_series.index)
            df["volume"] = volume_series.values
        else:
            df["volume"] = pd.NA

        if float_share_panel is not None and code in float_share_panel.columns:
            float_share_series = float_share_panel[code].reindex(price_series.index)
            df["float_share"] = float_share_series.values
        else:
            df["float_share"] = pd.NA

        df["turnover_rate"] = pd.to_numeric(df["volume"], errors="coerce") / pd.to_numeric(df["float_share"], errors="coerce")
        df[f"turnover_rate_{turnover_window}"] = df["turnover_rate"].rolling(turnover_window).mean()

        factor_frames.append(df)

    if not factor_frames:
        return pd.DataFrame(columns=["trade_date", "ts_code", "close"])

    factor_data = pd.concat(factor_frames, ignore_index=True)
    factor_data["trade_date"] = pd.to_datetime(factor_data["trade_date"])
    factor_data = factor_data.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)

    # 合并来自 financial_factors 的 ETF 财务因子（如已提供）。
    if financial_factor_data is not None and not financial_factor_data.empty:
        fin = financial_factor_data.copy()
        required_cols = {"trade_date", "ts_code"}
        if not required_cols.issubset(fin.columns):
            raise ValueError("financial_factor_data must contain trade_date and ts_code columns")
        fin["trade_date"] = pd.to_datetime(fin["trade_date"], errors="coerce")
        fin = fin.dropna(subset=["trade_date", "ts_code"]).copy()
        fin["ts_code"] = fin["ts_code"].astype(str)

        factor_data = factor_data.merge(
            fin,
            on=["trade_date", "ts_code"],
            how="left",
            suffixes=("", "_financial"),
        )

    return factor_data


def _momentum_regression_score(window_values: np.ndarray) -> float:
    """Compute weighted-regression momentum score used by s14-like logic."""
    values = np.asarray(window_values, dtype=float)
    if len(values) < 2 or np.any(~np.isfinite(values)) or np.any(values <= 0):
        return np.nan

    y = np.log(values)
    n = len(y)
    x = np.arange(n)
    weights = np.linspace(1.0, 2.0, n)

    try:
        slope, intercept = np.polyfit(x, y, 1, w=weights)
    except Exception:
        return np.nan

    annualized_returns = np.exp(slope * 250) - 1
    fitted = slope * x + intercept
    residuals = y - fitted
    weighted_residuals = weights * residuals ** 2
    denominator = np.sum(weights * (y - np.mean(y)) ** 2)
    if denominator == 0:
        return np.nan
    r_squared = 1 - (np.sum(weighted_residuals) / denominator)
    return float(annualized_returns * r_squared)


__all__ = ["build_etf_factor_data"]
