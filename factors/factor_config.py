"""ETF factor whitelist and direction configuration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

# 因子方向：1 表示值越大越好，-1 表示值越小越好。
DEFAULT_FACTOR_DIRECTIONS: dict[str, int] = {
    "momentum_5": 1,
    "momentum_20": 1,
    "momentum_60": 1,
    "volatility_20": -1,
    "volatility_60": -1,
    "bias_20": -1,
    "bias_60": -1,
    "volume_ratio": 1,
    "liquidity": 1,
}

# 第一版 ETF 多因子白名单（技术因子 + 流动性代理因子）
DEFAULT_FACTOR_WHITELIST: tuple[str, ...] = tuple(DEFAULT_FACTOR_DIRECTIONS.keys())


def get_default_factor_directions() -> dict[str, int]:
    """返回默认因子方向配置。"""
    return dict(DEFAULT_FACTOR_DIRECTIONS)


def get_default_factor_whitelist() -> tuple[str, ...]:
    """返回默认 ETF 因子白名单。"""
    return tuple(DEFAULT_FACTOR_WHITELIST)


def resolve_factor_weights(
    available_columns: Sequence[str],
    factor_weights: Mapping[str, float] | None = None,
    factor_directions: Mapping[str, int] | None = None,
    whitelist: Sequence[str] | None = None,
) -> dict[str, float]:
    """根据白名单、方向和可用列生成可用权重。

    规则：
    1) 先按 whitelist 过滤；
    2) 再与 available_columns 取交集；
    3) 若传入 factor_weights，则优先使用传入权重；
    4) 否则使用方向值等绝对权重归一化生成默认权重。
    """
    allowed = tuple(whitelist or DEFAULT_FACTOR_WHITELIST)
    columns = set(str(column) for column in available_columns)
    candidates = [name for name in allowed if name in columns]

    if not candidates:
        return {}

    if factor_weights:
        configured = {str(name): float(weight) for name, weight in factor_weights.items()}
        return {name: configured[name] for name in candidates if name in configured}

    directions = {str(name): int(value) for name, value in dict(factor_directions or DEFAULT_FACTOR_DIRECTIONS).items()}
    raw = {name: float(directions.get(name, 0)) for name in candidates}
    raw = {name: value for name, value in raw.items() if value != 0.0}
    if not raw:
        return {}

    total = sum(abs(value) for value in raw.values())
    if total <= 0:
        return {}
    return {name: value / total for name, value in raw.items()}


def summarize_factor_availability(
    factor_data: pd.DataFrame,
    whitelist: Sequence[str] | None = None,
    factor_directions: Mapping[str, int] | None = None,
) -> pd.DataFrame:
    """统计白名单因子的可用性与覆盖率，便于回测前检查。"""
    allowed = tuple(whitelist or DEFAULT_FACTOR_WHITELIST)
    directions = dict(factor_directions or DEFAULT_FACTOR_DIRECTIONS)

    rows: list[dict[str, object]] = []
    row_count = len(factor_data)

    for factor in allowed:
        exists = factor in factor_data.columns
        non_null = int(factor_data[factor].notna().sum()) if exists else 0
        coverage = (non_null / row_count) if row_count > 0 else 0.0
        rows.append(
            {
                "factor": factor,
                "direction": int(directions.get(factor, 0)),
                "available": bool(exists),
                "coverage": float(coverage),
            }
        )

    summary = pd.DataFrame(rows)
    return summary.sort_values(["available", "coverage", "factor"], ascending=[False, False, True]).reset_index(drop=True)


__all__ = [
    "DEFAULT_FACTOR_DIRECTIONS",
    "DEFAULT_FACTOR_WHITELIST",
    "get_default_factor_directions",
    "get_default_factor_whitelist",
    "resolve_factor_weights",
    "summarize_factor_availability",
]
