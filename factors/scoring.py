"""High-level ETF cross-sectional scoring helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from .cross_sectional import compute_composite_score
from .factor_config import resolve_factor_weights


def score_etf_cross_section(
    factor_data: pd.DataFrame,
    factor_weights: Mapping[str, float] | None = None,
    factor_directions: Mapping[str, int] | None = None,
    whitelist: Sequence[str] | None = None,
    date_col: str = "trade_date",
    symbol_col: str = "ts_code",
    fill_value: float = 0.0,
    drop_missing_factors: bool = False,
) -> pd.DataFrame:
    """完整流程：解析可用因子 -> 因子标准化 -> 综合评分 -> 截面排序。

    这一步把 ETF 多因子评分封装成独立函数，后续策略类只需要调用本函数，
    不再关心白名单过滤、权重解析和标准化的细节。
    """
    if factor_data is None or factor_data.empty:
        return pd.DataFrame(columns=[date_col, symbol_col, "composite_score", "score_rank"])

    working = factor_data.copy()
    working[date_col] = pd.to_datetime(working[date_col])

    weights = resolve_factor_weights(
        available_columns=working.columns,
        factor_weights=factor_weights,
        factor_directions=factor_directions,
        whitelist=whitelist,
    )
    if not weights:
        raise ValueError("no usable factors found after applying whitelist/weights")

    # 缺失值处理策略：如果要求严格模式，则剔除当前评分所需因子中有缺失的行。
    if drop_missing_factors:
        working = working.dropna(subset=list(weights.keys()))
        if working.empty:
            return pd.DataFrame(columns=[date_col, symbol_col, "composite_score", "score_rank", "selected_factors"])

    # 逐期标准化和评分。
    scored = compute_composite_score(
        factor_data=working,
        factor_weights=weights,
        date_col=date_col,
        symbol_col=symbol_col,
        fill_value=fill_value,
    )

    # 逐期按综合得分做截面排序，分数越高排名越靠前。
    scored["score_rank"] = scored.groupby(date_col)["composite_score"].rank(method="first", ascending=False)
    scored["selected_factors"] = ",".join(weights.keys())
    return scored.sort_values([date_col, "score_rank", symbol_col]).reset_index(drop=True)


def select_top_etfs(
    scored_data: pd.DataFrame,
    top_n: int = 3,
    date_col: str = "trade_date",
    symbol_col: str = "ts_code",
    score_col: str = "composite_score",
    min_score: float | None = None,
    weight_method: str = "equal",
) -> pd.DataFrame:
    """根据因子评分选出 Top N ETF，并生成权重。

    注释语义参考 multi-factor-stock-selection 的 `select_stocks_by_score`：
    先按 `composite_score` 排序，再生成持仓权重。
    """
    if scored_data is None or scored_data.empty:
        return pd.DataFrame(columns=[date_col, symbol_col, score_col, "weight", "score_rank"])
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    selected_groups: list[pd.DataFrame] = []
    for _, group in scored_data.groupby(date_col, sort=True):
        group = group.sort_values(by=score_col, ascending=False)
        if min_score is not None:
            group = group[group[score_col] >= float(min_score)]
        group = group.head(int(top_n)).copy()
        if group.empty:
            continue

        # 等权配置是第一版默认方案；后续可扩展为按评分加权。
        if weight_method == "equal":
            group["weight"] = 1.0 / len(group)
        elif weight_method == "score":
            positive_score = group[score_col].clip(lower=0)
            total = float(positive_score.sum())
            if total <= 0:
                group["weight"] = 1.0 / len(group)
            else:
                group["weight"] = positive_score / total
        else:
            raise ValueError(f"unsupported weight_method: {weight_method}")
        selected_groups.append(group[[date_col, symbol_col, score_col, "score_rank", "weight"]])

    if not selected_groups:
        return pd.DataFrame(columns=[date_col, symbol_col, score_col, "weight", "score_rank"])
    return pd.concat(selected_groups, ignore_index=True)


__all__ = ["score_etf_cross_section", "select_top_etfs"]
