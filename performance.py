"""
Performance calculation utilities and comprehensive metrics analysis.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
import backtrader as bt


def compute_performance(equity: pd.Series, trading_days: int = 252) -> dict:
    """Compute basic performance statistics from equity curve.

    Parameters
    ----------
    equity : pd.Series
        Daily portfolio value indexed by date.
    trading_days : int
        Number of trading days per year for annualization.

    Returns
    -------
    dict
        Contains 'annual_return', 'sharpe', 'max_drawdown'.
    """
    returns = equity.pct_change().dropna()
    # annualized return (geometric)
    total_days = (equity.index[-1] - equity.index[0]).days
    total_years = total_days / 365.25
    annual_return = (equity.iloc[-1] / equity.iloc[0]) ** (1 / total_years) - 1

    # Sharpe ratio (assume rf=0)
    if returns.std() == 0 or np.isnan(returns.std()):
        sharpe = np.nan
    else:
        sharpe = np.sqrt(trading_days) * returns.mean() / returns.std()

    # max drawdown
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    return {
        'annual_return': annual_return,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
    }


class PerformanceMetrics:
    """Calculate and organize performance metrics from backtest results."""

    def __init__(self, records: pd.DataFrame, trades: List[Dict[str, Any]],
                 initial_cash: float = 100000, risk_free_rate: float = 0.02):
        """
        Initialize with backtest results.

        Args:
            records: DataFrame with daily portfolio records
            trades: List of trade dictionaries
            initial_cash: Initial portfolio value
            risk_free_rate: Annual risk-free rate for Sharpe ratio
        """
        self.records = records
        self.trades = trades
        self.initial_cash = initial_cash
        self.risk_free_rate = risk_free_rate
        self.returns = self._calculate_returns()

    def _calculate_returns(self) -> pd.Series:
        """Calculate daily returns from portfolio value."""
        return self.records['value'].pct_change().dropna()

    def calculate_basic_metrics(self) -> Dict[str, float]:
        """Calculate basic performance metrics."""
        final_value = self.records['value'].iloc[-1]
        total_return = (final_value - self.initial_cash) / self.initial_cash

        # Annualized return
        days = (self.records.index[-1] - self.records.index[0]).days
        years = days / 365.25
        annualized_return = (final_value / self.initial_cash) ** (1 / years) - 1

        # Volatility (annualized)
        daily_volatility = self.returns.std()
        annualized_volatility = daily_volatility * np.sqrt(252)  # Assuming 252 trading days

        # Sharpe ratio
        excess_returns = self.returns - self.risk_free_rate / 252
        sharpe_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(252)

        # Maximum drawdown
        peak = self.records['value'].expanding().max()
        drawdown = (self.records['value'] - peak) / peak
        max_drawdown = drawdown.min()

        # Calmar ratio
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else np.nan

        # Sortino ratio (downside deviation)
        downside_returns = self.returns[self.returns < 0]
        downside_deviation = downside_returns.std() * np.sqrt(252)
        sortino_ratio = (annualized_return - self.risk_free_rate) / downside_deviation if downside_deviation != 0 else np.nan

        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'annualized_volatility': annualized_volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'calmar_ratio': calmar_ratio,
            'sortino_ratio': sortino_ratio,
            'final_value': final_value,
            'initial_cash': self.initial_cash,
        }

    def calculate_trade_metrics(self) -> Dict[str, Any]:
        """Calculate trading-related metrics."""
        if not self.trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'avg_trade_duration': 0,
            }

        # Convert trades to DataFrame for easier analysis
        trades_df = pd.DataFrame(self.trades)

        # Calculate P&L for each trade
        trade_pnl = []
        for i in range(0, len(trades_df), 2):  # Assuming buy-sell pairs
            if i + 1 < len(trades_df):
                buy_trade = trades_df.iloc[i]
                sell_trade = trades_df.iloc[i + 1]
                pnl = (sell_trade['price'] - buy_trade['price']) * buy_trade['size']
                trade_pnl.append(pnl)

        trade_pnl = np.array(trade_pnl)
        winning_trades = trade_pnl[trade_pnl > 0]
        losing_trades = trade_pnl[trade_pnl < 0]

        total_trades = len(trade_pnl)
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)
        win_rate = winning_count / total_trades if total_trades > 0 else 0

        avg_win = winning_trades.mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades.mean() if len(losing_trades) > 0 else 0

        total_profit = winning_trades.sum()
        total_loss = abs(losing_trades.sum())
        profit_factor = total_profit / total_loss if total_loss != 0 else np.inf

        # Average trade duration (simplified)
        if len(trades_df) >= 2:
            durations = []
            for i in range(0, len(trades_df), 2):
                if i + 1 < len(trades_df):
                    buy_date = pd.to_datetime(trades_df.iloc[i]['date'])
                    sell_date = pd.to_datetime(trades_df.iloc[i + 1]['date'])
                    duration = (sell_date - buy_date).days
                    durations.append(duration)
            avg_trade_duration = np.mean(durations) if durations else 0
        else:
            avg_trade_duration = 0

        return {
            'total_trades': total_trades,
            'winning_trades': winning_count,
            'losing_trades': losing_count,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_trade_duration': avg_trade_duration,
        }

    def calculate_risk_metrics(self) -> Dict[str, float]:
        """Calculate risk-related metrics."""
        returns = self.returns

        # Value at Risk (95% confidence)
        var_95 = np.percentile(returns, 5)

        # Expected Shortfall (CVaR)
        cvar_95 = returns[returns <= var_95].mean()

        # Skewness and Kurtosis
        skewness = returns.skew()
        kurtosis = returns.kurtosis()

        # Maximum consecutive losses
        signs = np.sign(returns)
        consecutive_losses = 0
        max_consecutive_losses = 0

        for sign in signs:
            if sign < 0:
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_losses = 0

        return {
            'var_95': var_95,
            'cvar_95': cvar_95,
            'skewness': skewness,
            'kurtosis': kurtosis,
            'max_consecutive_losses': max_consecutive_losses,
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all performance metrics organized by category."""
        return {
            'basic': self.calculate_basic_metrics(),
            'trading': self.calculate_trade_metrics(),
            'risk': self.calculate_risk_metrics(),
        }

    def create_metrics_table(self) -> pd.DataFrame:
        """Create a formatted DataFrame of all metrics for display."""
        metrics = self.get_all_metrics()

        # Flatten the nested dictionary
        flat_metrics = {}
        for category, cat_metrics in metrics.items():
            for key, value in cat_metrics.items():
                flat_metrics[f"{category}_{key}"] = value

        # Create DataFrame
        df = pd.DataFrame(list(flat_metrics.items()), columns=['Metric', 'Value'])

        # Format values
        def format_value(row):
            key, value = row['Metric'], row['Value']
            if isinstance(value, float):
                if 'return' in key or 'drawdown' in key or 'var' in key or 'cvar' in key:
                    return f"{value:.4f}"
                elif 'ratio' in key:
                    return f"{value:.2f}"
                elif 'rate' in key:
                    return f"{value:.1%}"
                else:
                    return f"{value:.4f}"
            elif isinstance(value, int):
                return f"{value:,}"
            else:
                return str(value)

        df['Formatted_Value'] = df.apply(format_value, axis=1)

        return df

    @staticmethod
    def extract_backtrader_analyzers(strategy) -> Dict[str, Any]:
        """
        Extract results from Backtrader analyzers.

        Args:
            strategy: Backtrader strategy instance

        Returns:
            Dictionary of analyzer results
        """
        analyzers_results = {}

        # Common analyzers
        if hasattr(strategy, 'analyzers'):
            for name, analyzer in strategy.analyzers.items():
                if hasattr(analyzer, 'get_analysis'):
                    analyzers_results[name] = analyzer.get_analysis()

        return analyzers_results
