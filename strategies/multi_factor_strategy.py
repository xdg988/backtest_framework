"""
Multi-Factor Strategy - Simple combination of RSI and MACD.
"""

import pandas as pd


class MultiFactorStrategy:
    """Signal generator combining multiple factors (RSI + MACD)."""

    def __init__(self, rsi_period: int = 14, rsi_overbought: int = 70, rsi_oversold: int = 30,
                 macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9):
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal

    def _calculate_rsi(self, data: pd.Series) -> pd.Series:
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_macd(self, data: pd.Series):
        ema_fast = data.ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = data.ewm(span=self.macd_slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=self.macd_signal, adjust=False).mean()
        return macd, signal

    def generate(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals: Buy if RSI oversold AND MACD golden cross, Sell if RSI overbought AND MACD dead cross."""
        df = data.copy()
        df['rsi'] = self._calculate_rsi(df['close'])
        df['macd'], df['macd_signal'] = self._calculate_macd(df['close'])
        signal = pd.Series(0, index=df.index)

        # Buy condition: RSI < oversold AND MACD golden cross
        buy_condition = (df['rsi'] < self.rsi_oversold) & \
                       (df['macd'] > df['macd_signal']) & (df['macd'].shift(1) <= df['macd_signal'].shift(1))
        # Sell condition: RSI > overbought AND MACD dead cross
        sell_condition = (df['rsi'] > self.rsi_overbought) & \
                        (df['macd'] < df['macd_signal']) & (df['macd'].shift(1) >= df['macd_signal'].shift(1))

        signal[buy_condition] = 1
        signal[sell_condition] = -1
        return signal