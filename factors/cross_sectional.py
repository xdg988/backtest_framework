"""Cross-sectional standardization and composite scoring helpers."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def _validate_factor_weights(factor_weights: Mapping[str, float]) -> dict[str, float]:
    # 因子权重是综合评分的核心输入，不能为空。
    weights = {str(name): float(weight) for name, weight in dict(factor_weights or {}).items()}
    if not weights:
        raise ValueError("factor_weights cannot be empty")
    return weights


def standardize_cross_section(
    factor_data: pd.DataFrame,
    factor_weights: Mapping[str, float],
    date_col: str = "trade_date",
    symbol_col: str = "ts_code",
    fill_value: float = 0.0,
) -> pd.DataFrame:
    """对单期（按交易日截面）因子数据进行标准化。

    注释语义与 multi-factor-stock-selection 的 `standardize_and_score` 保持一致：
    逐期标准化后再用于综合评分。
    """
    weights = _validate_factor_weights(factor_weights)
    required_columns = {date_col, symbol_col, *weights.keys()}
    missing_columns = [column for column in required_columns if column not in factor_data.columns]
    if missing_columns:
        raise KeyError(f"missing required columns: {missing_columns}")

    scored = factor_data.copy()
    scored[date_col] = pd.to_datetime(scored[date_col])

    # 逐期标准化和评分（先做标准化，评分在下一个函数完成）
    for factor in weights:
        series = pd.to_numeric(scored[factor], errors="coerce")
        # 按 trade_date 做截面均值/标准差，而不是时间序列滚动标准化。
        mean = series.groupby(scored[date_col]).transform("mean")
        std = series.groupby(scored[date_col]).transform(lambda values: values.std(ddof=0))
        zscore = (series - mean) / std
        # 当某期标准差为0或缺失时，用 fill_value 兜底，避免 NaN 传播。
        zscore = zscore.where(std.ne(0) & std.notna(), fill_value).fillna(fill_value)
        scored[f"{factor}_z"] = zscore

    return scored.sort_values([date_col, symbol_col]).reset_index(drop=True)


def compute_composite_score(
    factor_data: pd.DataFrame,
    factor_weights: Mapping[str, float],
    date_col: str = "trade_date",
    symbol_col: str = "ts_code",
    fill_value: float = 0.0,
) -> pd.DataFrame:
    """完整流程：因子标准化 -> 综合评分。

    这里沿用了 multi-factor-stock-selection 的核心逻辑：
    `composite_score = Σ(factor_z * weight)`。
    """
    weights = _validate_factor_weights(factor_weights)
    scored = standardize_cross_section(
        factor_data=factor_data,
        factor_weights=weights,
        date_col=date_col,
        symbol_col=symbol_col,
        fill_value=fill_value,
    )
    scored["composite_score"] = sum(scored[f"{factor}_z"] * weight for factor, weight in weights.items())
    return scored


__all__ = ["standardize_cross_section", "compute_composite_score"]
