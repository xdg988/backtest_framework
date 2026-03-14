"""
Bollinger Bands Strategy - Bollinger Bands Breakout.
"""

import pandas as pd


class BollingerStrategy:
    """Signal generator using Bollinger Bands breakout."""

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev

    def _calculate_bollinger(self, data: pd.Series):
        """Calculate Bollinger Bands."""
        sma = data.rolling(window=self.period).mean()
        std = data.rolling(window=self.period).std()
        upper = sma + (std * self.std_dev)
        lower = sma - (std * self.std_dev)
        return sma, upper, lower

    def generate(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals: 1 for buy on lower breakout, -1 for sell on upper breakout."""
        df = data.copy()
        df['sma'], df['upper'], df['lower'] = self._calculate_bollinger(df['close'])
        signal = pd.Series(0, index=df.index)
        # Buy when close crosses above lower band
        buy_signal = (df['close'] > df['lower']) & (df['close'].shift(1) <= df['lower'].shift(1))
        # Sell when close crosses below upper band
        sell_signal = (df['close'] < df['upper']) & (df['close'].shift(1) >= df['upper'].shift(1))
        signal[buy_signal] = 1
        signal[sell_signal] = -1
        return signal