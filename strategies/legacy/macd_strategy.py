"""
MACD Strategy - MACD Golden/Dead Cross.
"""

import pandas as pd


class MACDStrategy:
    """Signal generator using MACD crossover."""

    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def _calculate_macd(self, data: pd.Series):
        """Calculate MACD, signal line, and histogram."""
        ema_fast = data.ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = data.ewm(span=self.slow_period, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=self.signal_period, adjust=False).mean()
        return macd, signal

    def generate(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals: 1 for buy on golden cross, -1 for sell on dead cross."""
        df = data.copy()
        df['macd'], df['signal'] = self._calculate_macd(df['close'])
        signal = pd.Series(0, index=df.index)
        # Golden cross: MACD crosses above signal
        golden_cross = (df['macd'] > df['signal']) & (df['macd'].shift(1) <= df['signal'].shift(1))
        # Dead cross: MACD crosses below signal
        dead_cross = (df['macd'] < df['signal']) & (df['macd'].shift(1) >= df['signal'].shift(1))
        signal[golden_cross] = 1
        signal[dead_cross] = -1
        return signal