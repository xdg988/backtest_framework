"""
KDJ Strategy - KDJ Crossover (simplified divergence approach).
"""

import pandas as pd


class KDJStrategy:
    """Signal generator using KDJ indicator crossover."""

    def __init__(self, period: int = 14, k_period: int = 3, d_period: int = 3):
        self.period = period
        self.k_period = k_period
        self.d_period = d_period

    def _calculate_kdj(self, data: pd.DataFrame):
        """Calculate KDJ indicators."""
        high = data['high']
        low = data['low']
        close = data['close']

        # RSV = (close - lowest_low) / (highest_high - lowest_low) * 100
        lowest_low = low.rolling(window=self.period).min()
        highest_high = high.rolling(window=self.period).max()
        rsv = (close - lowest_low) / (highest_high - lowest_low) * 100

        # K = EMA(RSV, k_period)
        k = rsv.ewm(span=self.k_period, adjust=False).mean()
        # D = EMA(K, d_period)
        d = k.ewm(span=self.d_period, adjust=False).mean()
        # J = 3*K - 2*D
        j = 3 * k - 2 * d

        return k, d, j

    def generate(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals based on K crossing D."""
        df = data.copy()
        df['k'], df['d'], df['j'] = self._calculate_kdj(df)
        signal = pd.Series(0, index=df.index)
        # Buy when K crosses above D
        buy_signal = (df['k'] > df['d']) & (df['k'].shift(1) <= df['d'].shift(1))
        # Sell when K crosses below D
        sell_signal = (df['k'] < df['d']) & (df['k'].shift(1) >= df['d'].shift(1))
        signal[buy_signal] = 1
        signal[sell_signal] = -1
        return signal