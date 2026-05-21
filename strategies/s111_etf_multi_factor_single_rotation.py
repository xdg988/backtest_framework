"""ETF multi-factor rotation strategy (single-target mode)."""

from __future__ import annotations

import pandas as pd

from .s110_etf_multi_factor_rotation import ETFMultiFactorRotation


class ETFMultiFactorSingleRotation(ETFMultiFactorRotation):
    """Single-ETF wrapper based on the same unified factor entry pipeline.

    设计目标：
    - 复用 `ETFMultiFactorRotation` 的统一入口因子与评分逻辑；
    - 输出 `generate_targets`，供 RotationBacktestStrategy 使用；
    - 与权重版在同一天的第一名标的保持一致。
    """

    def generate_targets(self, close_panel: pd.DataFrame) -> pd.Series:
        """Generate one target ETF code per rebalance date.

        输出格式：
        - index: trade_date
        - value: ETF code（调仓日给出代码，非调仓日为 NaN）
        """
        weights = self.generate_target_weights(close_panel)
        targets = pd.Series(index=weights.index, dtype="object")

        for ts in weights.index:
            row = weights.loc[ts].dropna()
            row = row[row > 0]
            if row.empty:
                targets.loc[ts] = pd.NA
                continue

            # 同分时按代码字母序稳定排序，保证可重复性。
            selected_code = row.sort_values(ascending=False).index[0]
            targets.loc[ts] = selected_code

        return targets


__all__ = ["ETFMultiFactorSingleRotation"]
