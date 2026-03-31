"""Strategy 85: defensive ETF rotation with monthly MACD regime switch."""

from __future__ import annotations

import pandas as pd


class ETFDefensiveMACDRotation:
    """Monthly defensive ETF allocation from the original 85 strategy logic."""

    multi_asset = True

    @staticmethod
    def _norm(code: str) -> str:
        if not isinstance(code, str):
            return code
        c = code.strip().upper()
        if c.endswith('.XSHG'):
            return c.replace('.XSHG', '.SH')
        if c.endswith('.XSHE'):
            return c.replace('.XSHE', '.SZ')
        return c

    def __init__(
        self,
        etf_pool: list[str],
        benchmark_code: str = "000300.XSHG",
        growth_etf: str = "159949.XSHE",
        us_etf: str = "513100.XSHG",
        dividend_etf: str = "510880.XSHG",
        bond_etf: str = "511010.XSHG",
        gold_etf: str = "518880.XSHG",
        cash_etf: str = "511880.XSHG",
        yearly_guard_threshold: float = -0.06,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        weight_slot_1: float = 0.125,
        weight_slot_2: float = 0.125,
        weight_slot_3: float = 0.25,
        weight_slot_4: float = 0.25,
        weight_slot_5: float = 0.25,
    ):
        if not etf_pool:
            raise ValueError("etf_pool cannot be empty for ETFDefensiveMACDRotation")
        self.etf_pool = [self._norm(code) for code in etf_pool]
        self.benchmark_code = self._norm(benchmark_code)
        self.growth_etf = self._norm(growth_etf)
        self.us_etf = self._norm(us_etf)
        self.dividend_etf = self._norm(dividend_etf)
        self.bond_etf = self._norm(bond_etf)
        self.gold_etf = self._norm(gold_etf)
        self.cash_etf = self._norm(cash_etf)
        self.yearly_guard_threshold = float(yearly_guard_threshold)
        self.macd_fast = int(macd_fast)
        self.macd_slow = int(macd_slow)
        self.macd_signal = int(macd_signal)
        self.slot_weights = [
            float(weight_slot_1),
            float(weight_slot_2),
            float(weight_slot_3),
            float(weight_slot_4),
            float(weight_slot_5),
        ]

    @staticmethod
    def _first_trading_day_mask(index: pd.Index) -> pd.Series:
        months = pd.Series(index=index, data=index.to_period("M"))
        return months != months.shift(1)

    @staticmethod
    def _macd_hist(series: pd.Series, fast: int, slow: int, signal: int) -> float:
        clean = series.dropna()
        if clean.shape[0] < slow + signal:
            return float("nan")
        ema_fast = clean.ewm(span=fast, adjust=False).mean()
        ema_slow = clean.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        hist = dif - dea
        return float(hist.iloc[-1])

    def _monthly_macd_positive(self, series: pd.Series) -> bool:
        monthly_close = series.dropna().resample("ME").last().dropna()
        hist = self._macd_hist(monthly_close, self.macd_fast, self.macd_slow, self.macd_signal)
        return pd.notna(hist) and hist > 0

    def _yearly_return(self, date: pd.Timestamp, close_panel: pd.DataFrame) -> float:
        if self.dividend_etf not in close_panel.columns:
            return float("nan")
        s = close_panel[self.dividend_etf].dropna()
        s = s[s.index <= date]
        if s.empty:
            return float("nan")
        current = float(s.iloc[-1])
        prev_year = int(date.year - 1)
        prev_year_close = s[s.index.year == prev_year]
        if prev_year_close.empty:
            return float("nan")
        base = float(prev_year_close.iloc[-1])
        if base <= 0:
            return float("nan")
        return current / base - 1.0

    def _allocation_for_date(self, date: pd.Timestamp, panel: pd.DataFrame) -> pd.Series | None:
        hist = panel.loc[:date]
        if hist.empty:
            return None

        zf = self._yearly_return(date, hist)
        risk_on = pd.notna(zf) and zf > self.yearly_guard_threshold

        macd_300 = self._monthly_macd_positive(hist[self.benchmark_code]) if self.benchmark_code in hist.columns else False
        macd_100 = self._monthly_macd_positive(hist[self.us_etf]) if self.us_etf in hist.columns else False
        macd_49 = self._monthly_macd_positive(hist[self.growth_etf]) if self.growth_etf in hist.columns else False
        macd_88 = self._monthly_macd_positive(hist[self.gold_etf]) if self.gold_etf in hist.columns else False

        if macd_49:
            slot1 = self.growth_etf
        elif macd_100:
            slot1 = self.us_etf
        elif risk_on:
            slot1 = self.dividend_etf
        else:
            slot1 = self.bond_etf

        slot2 = self.dividend_etf if risk_on else self.bond_etf

        if macd_88:
            slot3 = self.gold_etf
        elif macd_300 and risk_on:
            slot3 = self.dividend_etf
        else:
            slot3 = self.gold_etf

        slot4 = self.bond_etf
        slot5 = self.cash_etf

        alloc = pd.Series(0.0, index=self.etf_pool, dtype=float)
        for code, weight in zip([slot1, slot2, slot3, slot4, slot5], self.slot_weights):
            if code in alloc.index:
                alloc.loc[code] += float(weight)

        total = float(alloc.sum())
        if total <= 0:
            return None
        return alloc / total

    def generate_target_weights(self, close_panel: pd.DataFrame) -> pd.DataFrame:
        panel = close_panel.copy()
        want_cols = [
            c for c in [
                *self.etf_pool,
                self.benchmark_code,
                self.growth_etf,
                self.us_etf,
                self.dividend_etf,
                self.bond_etf,
                self.gold_etf,
                self.cash_etf,
            ]
            if c in panel.columns
        ]
        want_cols = list(dict.fromkeys(want_cols))
        panel = panel[want_cols]

        weights_df = pd.DataFrame(index=panel.index, columns=self.etf_pool, dtype=float)
        if panel.empty:
            return weights_df

        first_mask = self._first_trading_day_mask(panel.index)
        for date, is_first in first_mask.items():
            if not is_first:
                continue
            alloc = self._allocation_for_date(date, panel)
            if alloc is None:
                continue
            weights_df.loc[date, alloc.index] = alloc.values

        return weights_df
