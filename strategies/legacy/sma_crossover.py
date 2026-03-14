"""
SMA Crossover Strategy - Double Moving Average Crossover.
"""

import pandas as pd


class SMACrossover:
    """Signal generator using two simple moving averages crossover."""

    def __init__(self, short_window: int = 20, long_window: int = 50):
        self.short_window = short_window
        self.long_window = long_window

    def generate(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals: 1 for buy, -1 for sell, 0 for hold.

        The signal is +1 when short SMA crosses above long SMA,
        -1 when short SMA crosses below long SMA.
        """
        df = data.copy()
        df['sma_short'] = df['close'].rolling(self.short_window).mean()
        df['sma_long'] = df['close'].rolling(self.long_window).mean()
        signal = pd.Series(0, index=df.index)
        cross_up = (df['sma_short'] > df['sma_long']) & (df['sma_short'].shift(1) <= df['sma_long'].shift(1))
        cross_down = (df['sma_short'] < df['sma_long']) & (df['sma_short'].shift(1) >= df['sma_long'].shift(1))
        signal[cross_up] = 1
        signal[cross_down] = -1
        return signal