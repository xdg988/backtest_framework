"""
Visualization module for backtest results.
"""

import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from typing import List, Dict, Any, Optional
import plotly.graph_objects as go


class BacktestVisualizer:
    """Visualization tools for backtest results using matplotlib."""

    def __init__(self, output_dir: str = "./results", figsize: tuple = (12, 6)):
        """
        Initialize visualizer.

        Args:
            output_dir: Directory to save plots
            figsize: Default figure size for plots
        """
        self.output_dir = output_dir
        self.figsize = figsize
        os.makedirs(output_dir, exist_ok=True)

        # Set matplotlib style
        plt.style.use('default')
        plt.rcParams['figure.figsize'] = figsize
        plt.rcParams['font.size'] = 10
        plt.rcParams['axes.labelsize'] = 10
        plt.rcParams['axes.titlesize'] = 12
        plt.rcParams['xtick.labelsize'] = 8
        plt.rcParams['ytick.labelsize'] = 8
        plt.rcParams['legend.fontsize'] = 10

    def plot_portfolio_value(self, records: pd.DataFrame, benchmark: Optional[pd.Series] = None,
                           save_path: Optional[str] = None, show_plot: bool = False) -> str:
        """
        Plot portfolio value over time.

        Args:
            records: DataFrame with 'date', 'value', 'cash' columns
            benchmark: Optional benchmark series to compare
            save_path: Path to save the plot (relative to output_dir if not absolute)
            show_plot: Whether to display the plot

        Returns:
            Path to saved plot
        """
        fig, ax = plt.subplots(figsize=self.figsize)

        # Plot portfolio value
        ax.plot(records.index, records['value'], label='Portfolio Value', linewidth=2, color='#1f77b4')

        # Plot cash if available
        if 'cash' in records.columns:
            ax.plot(records.index, records['cash'], label='Cash', alpha=0.7, color='#ff7f0e')

        # Plot benchmark if provided
        if benchmark is not None:
            ax.plot(benchmark.index, benchmark.values, label='Benchmark', linewidth=2,
                   color='#2ca02c', linestyle='--')

        ax.set_title('Portfolio Value Over Time', fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Value')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)

        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        # Add value labels
        final_value = records['value'].iloc[-1]
        ax.text(0.02, 0.98, f'Final Value: ${final_value:,.0f}',
               transform=ax.transAxes, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        plt.tight_layout()

        if save_path is None:
            save_path = os.path.join(self.output_dir, 'portfolio_value.png')
        elif not os.path.isabs(save_path):
            save_path = os.path.join(self.output_dir, save_path)

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        if show_plot:
            plt.show()
        else:
            plt.close()

        return save_path

    def plot_drawdown(self, records: pd.DataFrame, save_path: Optional[str] = None,
                     show_plot: bool = False) -> str:
        """
        Plot drawdown chart.

        Args:
            records: DataFrame with 'value' column
            save_path: Path to save the plot
            show_plot: Whether to display the plot

        Returns:
            Path to saved plot
        """
        fig, ax = plt.subplots(figsize=self.figsize)

        portfolio_value = records['value']
        peak = portfolio_value.expanding().max()
        drawdown = (portfolio_value - peak) / peak * 100

        # Fill drawdown area
        ax.fill_between(records.index, drawdown, 0, color='red', alpha=0.3, label='Drawdown')
        ax.plot(records.index, drawdown, color='red', linewidth=1)

        ax.set_title('Portfolio Drawdown', fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Drawdown (%)')
        ax.legend(loc='lower left')
        ax.grid(True, alpha=0.3)

        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        # Add max drawdown label
        max_dd = drawdown.min()
        ax.text(0.02, 0.02, f'Max Drawdown: {max_dd:.2f}%',
               transform=ax.transAxes, verticalalignment='bottom',
               bbox=dict(boxstyle='round', facecolor='lightcoral', alpha=0.5))

        plt.tight_layout()

        if save_path is None:
            save_path = os.path.join(self.output_dir, 'drawdown.png')
        elif not os.path.isabs(save_path):
            save_path = os.path.join(self.output_dir, save_path)

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        if show_plot:
            plt.show()
        else:
            plt.close()

        return save_path

    def plot_signals_and_price(self, data: pd.DataFrame, signals: pd.Series,
                              save_path: Optional[str] = None, show_plot: bool = False) -> str:
        """
        Plot price with buy/sell signals.

        Args:
            data: DataFrame with OHLC data
            signals: Series with signals (1=buy, -1=sell, 0=hold)
            save_path: Path to save the plot
            show_plot: Whether to display the plot

        Returns:
            Path to saved plot
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(self.figsize[0], self.figsize[1]*1.5),
                                      sharex=True, gridspec_kw={'height_ratios': [3, 1]})

        # Price chart
        ax1.plot(data.index, data['close'], label='Close Price', linewidth=1, color='black')
        ax1.plot(data.index, data['close'].rolling(20).mean(), label='20-day MA', alpha=0.7, color='blue')
        ax1.plot(data.index, data['close'].rolling(50).mean(), label='50-day MA', alpha=0.7, color='red')

        # Plot signals
        buy_signals = signals[signals == 1]
        sell_signals = signals[signals == -1]

        if not buy_signals.empty:
            ax1.scatter(buy_signals.index, data.loc[buy_signals.index, 'close'],
                       marker='^', color='green', s=80, label='Buy Signal', zorder=5)
        if not sell_signals.empty:
            ax1.scatter(sell_signals.index, data.loc[sell_signals.index, 'close'],
                       marker='v', color='red', s=80, label='Sell Signal', zorder=5)

        ax1.set_title('Price Chart with Trading Signals', fontweight='bold')
        ax1.set_ylabel('Price')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)

        # Volume chart
        ax2.bar(data.index, data['volume'], alpha=0.6, color='blue', width=1)
        ax2.set_title('Volume')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Volume')
        ax2.grid(True, alpha=0.3)

        # Format x-axis dates
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

        plt.tight_layout()

        if save_path is None:
            save_path = os.path.join(self.output_dir, 'signals_price.png')
        elif not os.path.isabs(save_path):
            save_path = os.path.join(self.output_dir, save_path)

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        if show_plot:
            plt.show()
        else:
            plt.close()

        return save_path

    def plot_returns_distribution(self, returns: pd.Series, save_path: Optional[str] = None,
                                 show_plot: bool = False) -> str:
        """
        Plot returns distribution histogram.

        Args:
            returns: Series of daily returns
            save_path: Path to save the plot
            show_plot: Whether to display the plot

        Returns:
            Path to saved plot
        """
        fig, ax = plt.subplots(figsize=self.figsize)

        ax.hist(returns * 100, bins=50, alpha=0.7, color='skyblue', edgecolor='black')
        ax.axvline(returns.mean() * 100, color='red', linestyle='--', linewidth=2,
                  label=f'Mean: {returns.mean()*100:.2f}%')
        ax.axvline(returns.median() * 100, color='green', linestyle='--', linewidth=2,
                  label=f'Median: {returns.median()*100:.2f}%')

        ax.set_title('Daily Returns Distribution', fontweight='bold')
        ax.set_xlabel('Daily Return (%)')
        ax.set_ylabel('Frequency')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path is None:
            save_path = os.path.join(self.output_dir, 'returns_distribution.png')
        elif not os.path.isabs(save_path):
            save_path = os.path.join(self.output_dir, save_path)

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        if show_plot:
            plt.show()
        else:
            plt.close()

        return save_path

    def create_summary_dashboard(self, records: pd.DataFrame, metrics: Dict[str, float],
                               trades: List[Dict[str, Any]], data: pd.DataFrame,
                               signals: pd.Series, benchmark: Optional[pd.Series] = None) -> Dict[str, str]:
        """
        Create a complete dashboard with multiple plots.

        Args:
            records: Portfolio records DataFrame
            metrics: Performance metrics dictionary
            trades: List of trade records
            data: Price data DataFrame
            signals: Trading signals Series
            benchmark: Optional benchmark portfolio-value-like series

        Returns:
            Dictionary mapping plot names to file paths
        """
        plots = {}

        # Interactive returns curve (single-file HTML embed)
        plots['returns_curve_html'] = self.build_interactive_returns_curve(records, benchmark=benchmark)

        # Drawdown plot
        plots['drawdown'] = self.plot_drawdown(records)

        # Signals and price plot
        plots['signals'] = self.plot_signals_and_price(data, signals)

        # Returns distribution
        returns = records['value'].pct_change().dropna()
        plots['returns_dist'] = self.plot_returns_distribution(returns)

        return plots

    def build_interactive_returns_curve(self, records: pd.DataFrame,
                                        benchmark: Optional[pd.Series] = None) -> str:
        """Build interactive cumulative returns curve HTML.

        Features:
        - Hover tooltip
        - Range buttons (1W/1M/6M/1Y/ALL)
        - Bottom range slider for custom date window
        """
        value = records['value'].dropna()
        if value.empty:
            return '<div>无可用收益曲线数据</div>'

        strat_ret = (value / value.iloc[0] - 1.0) * 100

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=strat_ret.index,
            y=strat_ret.values,
            mode='lines',
            name='策略收益率',
            line=dict(color='#1f77b4', width=2),
            hovertemplate='日期: %{x|%Y-%m-%d}<br>策略收益: %{y:.2f}%<extra></extra>'
        ))

        if benchmark is not None and not benchmark.empty:
            bench_aligned = benchmark.reindex(strat_ret.index).ffill().dropna()
            if not bench_aligned.empty and bench_aligned.iloc[0] != 0:
                bench_ret = (bench_aligned / bench_aligned.iloc[0] - 1.0) * 100
                fig.add_trace(go.Scatter(
                    x=bench_ret.index,
                    y=bench_ret.values,
                    mode='lines',
                    name='沪深300基准收益率',
                    line=dict(color='#2ca02c', width=2, dash='dash'),
                    hovertemplate='日期: %{x|%Y-%m-%d}<br>基准收益: %{y:.2f}%<extra></extra>'
                ))

        fig.update_layout(
            title='收益曲线（策略 vs 基准）',
            xaxis=dict(
                title='日期',
                rangeselector=dict(
                    buttons=list([
                        dict(count=7, label='近一周', step='day', stepmode='backward'),
                        dict(count=1, label='一个月', step='month', stepmode='backward'),
                        dict(count=6, label='六个月', step='month', stepmode='backward'),
                        dict(count=1, label='一年', step='year', stepmode='backward'),
                        dict(step='all', label='全部'),
                    ])
                ),
                rangeslider=dict(visible=True),
                type='date'
            ),
            yaxis=dict(title='累计收益率 (%)'),
            hovermode='x unified',
            template='plotly_white',
            margin=dict(l=40, r=20, t=60, b=40),
            height=520,
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        return fig.to_html(full_html=False, include_plotlyjs='inline', config={'displaylogo': False})