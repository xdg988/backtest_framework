"""
RSI Strategy - RSI Overbought/Oversold.
"""

import pandas as pd


class RSIStrategy:
    """Signal generator using RSI overbought/oversold levels."""

    def __init__(self, period: int = 14, overbought: int = 70, oversold: int = 30):
        self.period = period
        self.overbought = overbought
        self.oversold = oversold

    def _calculate_rsi(self, data: pd.Series) -> pd.Series:
        """Calculate RSI indicator."""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def generate(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals: 1 for buy when oversold, -1 for sell when overbought."""
        df = data.copy()
        df['rsi'] = self._calculate_rsi(df['close'])
        signal = pd.Series(0, index=df.index)
        # Buy when RSI crosses below oversold
        buy_signal = (df['rsi'] < self.oversold) & (df['rsi'].shift(1) >= self.oversold)
        # Sell when RSI crosses above overbought
        sell_signal = (df['rsi'] > self.overbought) & (df['rsi'].shift(1) <= self.overbought)
        signal[buy_signal] = 1
        signal[sell_signal] = -1
        return signal