"""ETF factor engineering helpers for rotation strategies."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


DEFAULT_MOMENTUM_WINDOWS = (5, 20, 60)
DEFAULT_VOLATILITY_WINDOWS = (20, 60)
DEFAULT_BIAS_WINDOWS = (20, 60)


def _normalize_windows(windows: Iterable[int] | None, default: tuple[int, ...]) -> tuple[int, ...]:
    # 统一窗口参数：去重、排序、过滤非正整数。
    values = tuple(sorted({int(window) for window in (windows or default) if int(window) > 0}))
    if not values:
        raise ValueError("at least one positive window is required")
    return values


def _stack_panel(panel: pd.DataFrame, value_name: str) -> pd.DataFrame:
    # 预留的宽表转长表工具，后续如需支持更多输入面板可直接复用。
    if panel is None or panel.empty:
        return pd.DataFrame(columns=["trade_date", "ts_code", value_name])

    stacked = panel.sort_index().stack(dropna=False).rename(value_name).reset_index()
    stacked.columns = ["trade_date", "ts_code", value_name]
    return stacked


def build_etf_factor_data(
    close_panel: pd.DataFrame,
    volume_panel: pd.DataFrame | None = None,
    amount_panel: pd.DataFrame | None = None,
    momentum_windows: Iterable[int] | None = None,
    volatility_windows: Iterable[int] | None = None,
    bias_windows: Iterable[int] | None = None,
    liquidity_window: int = 20,
) -> pd.DataFrame:
    """Build a long-form ETF factor table from wide market panels.

    Parameters
    ----------
    close_panel
        Wide close-price panel. Index is trading date and columns are ETF codes.
    volume_panel
        Optional wide volume panel aligned with ``close_panel``.
    amount_panel
        Optional wide amount/turnover panel aligned with ``close_panel``.
    momentum_windows, volatility_windows, bias_windows
        Rolling windows for factor generation.
    liquidity_window
        Rolling window used by liquidity proxies.

    说明
    ----
    本函数负责把 ETF 宽表行情转成“trade_date + ts_code”的长表，
    供后续截面标准化与综合评分使用。
    """
    if close_panel is None or close_panel.empty:
        return pd.DataFrame(columns=["trade_date", "ts_code", "close"])

    momentum_windows = _normalize_windows(momentum_windows, DEFAULT_MOMENTUM_WINDOWS)
    volatility_windows = _normalize_windows(volatility_windows, DEFAULT_VOLATILITY_WINDOWS)
    bias_windows = _normalize_windows(bias_windows, DEFAULT_BIAS_WINDOWS)
    liquidity_window = int(liquidity_window)
    if liquidity_window <= 0:
        raise ValueError("liquidity_window must be positive")

    close_panel = close_panel.sort_index().copy()
    factor_frames: list[pd.DataFrame] = []

    # 按 ETF 逐个生成因子，再拼接成统一因子表。
    for code in close_panel.columns:
        price_series = close_panel[code].dropna()
        if price_series.empty:
            continue

        df = pd.DataFrame({"trade_date": price_series.index, "ts_code": code, "close": price_series.values})
        df = df.sort_values("trade_date").reset_index(drop=True)

        # 动量因子：过去 N 日收益率。
        for window in momentum_windows:
            df[f"momentum_{window}"] = df["close"].pct_change(window)

        # 波动率因子：日收益率在窗口内的标准差。
        returns = df["close"].pct_change()
        for window in volatility_windows:
            df[f"volatility_{window}"] = returns.rolling(window).std()

        # 均线乖离率：反映价格偏离趋势均线的程度。
        for window in bias_windows:
            ma = df["close"].rolling(window).mean()
            df[f"ma_{window}"] = ma
            df[f"bias_{window}"] = (df["close"] - ma) / ma

        # 流动性代理1：量比（当前成交量 / 窗口均量）。
        if volume_panel is not None and code in volume_panel.columns:
            volume_series = volume_panel[code].reindex(price_series.index)
            df["volume"] = volume_series.values
            df["volume_ratio"] = df["volume"] / df["volume"].rolling(liquidity_window).mean()
        else:
            df["volume"] = pd.NA
            df["volume_ratio"] = pd.NA

        # 流动性代理2：成交额移动均值。
        if amount_panel is not None and code in amount_panel.columns:
            amount_series = amount_panel[code].reindex(price_series.index)
            df["amount"] = amount_series.values
            df["liquidity"] = df["amount"].rolling(liquidity_window).mean()
        else:
            df["amount"] = pd.NA
            df["liquidity"] = pd.NA

        factor_frames.append(df)

    if not factor_frames:
        return pd.DataFrame(columns=["trade_date", "ts_code", "close"])

    # 统一按日期、代码排序，保证后续 groupby(date) 的稳定性。
    factor_data = pd.concat(factor_frames, ignore_index=True)
    factor_data["trade_date"] = pd.to_datetime(factor_data["trade_date"])
    factor_data = factor_data.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    return factor_data


__all__ = ["build_etf_factor_data"]
