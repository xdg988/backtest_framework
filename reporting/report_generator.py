"""
Report generation module for creating HTML reports and saving results.
"""

import os
import base64
import pandas as pd
from jinja2 import Template, Environment
from typing import Dict, Any, List, Optional
from datetime import datetime

from .visualizer import BacktestVisualizer
from backtest.performance import PerformanceMetrics


class ReportGenerator:
    """Generate comprehensive HTML reports from backtest results."""

    def __init__(self, template_path: Optional[str] = None):
        """
        Initialize report generator.

        Args:
            template_path: Path to HTML template file
        """
        if template_path is None:
            template_path = os.path.join(os.path.dirname(__file__), 'report_template.html')
        self.template = self._load_template(template_path)

    def _load_template(self, template_path: str) -> Template:
        """Load HTML template."""
        # Create Jinja2 environment with custom filters
        env = Environment()

        # Add number_format filter
        def number_format(value):
            """Format number with commas and 2 decimal places."""
            try:
                return f"{float(value):,.2f}"
            except (ValueError, TypeError):
                return str(value)

        env.filters['number_format'] = number_format

        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return env.from_string(f.read())
        else:
            # Use embedded template
            return env.from_string(self._get_default_template())

    def _get_default_template(self) -> str:
        """Get default HTML template."""
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>量化回测报告</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            border-bottom: 2px solid #007acc;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #007acc;
            margin: 0;
            font-size: 2.5em;
        }
        .header p {
            color: #666;
            margin: 10px 0 0 0;
        }
        .section {
            margin-bottom: 40px;
        }
        .section h2 {
            color: #007acc;
            border-bottom: 1px solid #ddd;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .metric-card h3 {
            margin: 0 0 10px 0;
            color: #495057;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .metric-card .value {
            font-size: 1.8em;
            font-weight: bold;
            color: #007acc;
        }
        .metric-card .value.positive { color: #28a745; }
        .metric-card .value.negative { color: #dc3545; }
        .chart-container {
            margin: 20px 0;
            text-align: center;
        }
        .chart-container img {
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
        }
        table th, table td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        table th {
            background-color: #007acc;
            color: white;
            font-weight: 600;
        }
        table tr:nth-child(even) {
            background-color: #f8f9fa;
        }
        table tr:hover {
            background-color: #e3f2fd;
        }
        .footer {
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #666;
            font-size: 0.9em;
        }
        .summary-stats {
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
            margin: 20px 0;
        }
        .stat-item {
            text-align: center;
            margin: 10px;
        }
        .stat-item .number {
            font-size: 2em;
            font-weight: bold;
            color: #007acc;
        }
        .stat-item .label {
            color: #666;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>量化回测报告</h1>
            <p>生成时间: {{ generation_time }}</p>
        </div>

        <div class="section">
            <h2>策略概览</h2>
            <div class="summary-stats">
                <div class="stat-item">
                    <div class="number">{{ strategy_name }}</div>
                    <div class="label">策略名称</div>
                </div>
                <div class="stat-item">
                    <div class="number">{{ start_date }} - {{ end_date }}</div>
                    <div class="label">回测期间</div>
                </div>
                <div class="stat-item">
                    <div class="number">${{ initial_cash|number_format }}</div>
                    <div class="label">初始资金</div>
                </div>
                <div class="stat-item">
                    <div class="number">${{ final_value|number_format }}</div>
                    <div class="label">最终价值</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>绩效指标</h2>
            <div class="metrics-grid">
                {% for metric in key_metrics %}
                <div class="metric-card">
                    <h3>{{ metric.name }}</h3>
                    <div class="value{% if metric.positive %} positive{% elif metric.negative %} negative{% endif %}">
                        {{ metric.value }}
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>

        <div class="section">
            <h2>收益曲线</h2>
            <div class="chart-container">
                {{ returns_curve_html | safe }}
            </div>
        </div>

        <div class="section">
            <h2>回撤分析</h2>
            <div class="chart-container">
                <img src="{{ drawdown_chart }}" alt="Drawdown Chart">
            </div>
        </div>

        <div class="section">
            <h2>交易信号</h2>
            <div class="chart-container">
                <img src="{{ signals_chart }}" alt="Signals and Price Chart">
            </div>
        </div>

        <div class="section">
            <h2>收益率分布</h2>
            <div class="chart-container">
                <img src="{{ returns_dist_chart }}" alt="Returns Distribution">
            </div>
        </div>

        <div class="section">
            <h2>交易统计</h2>
            <table>
                <thead>
                    <tr>
                        <th>指标</th>
                        <th>数值</th>
                    </tr>
                </thead>
                <tbody>
                    {% for metric in trade_metrics %}
                    <tr>
                        <td>{{ metric.name }}</td>
                        <td>{{ metric.value }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>交易记录</h2>
            <table>
                <thead>
                    <tr>
                        <th>日期</th>
                        <th>操作</th>
                        <th>价格</th>
                        <th>数量</th>
                    </tr>
                </thead>
                <tbody>
                    {% for trade in trades %}
                    <tr>
                        <td>{{ trade.date }}</td>
                        <td>{{ trade.action }}</td>
                        <td>${{ "%.2f"|format(trade.price) }}</td>
                        <td>{{ trade.size }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>详细指标</h2>
            <table>
                <thead>
                    <tr>
                        <th>类别</th>
                        <th>指标</th>
                        <th>数值</th>
                    </tr>
                </thead>
                <tbody>
                    {% for metric in all_metrics %}
                    <tr>
                        <td>{{ metric.category }}</td>
                        <td>{{ metric.name }}</td>
                        <td>{{ metric.value }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="footer">
            <p>报告由量化回测框架自动生成 | {{ generation_time }}</p>
        </div>
    </div>
</body>
</html>
        """

    def generate_report(self, strategy_name: str, start_date: str, end_date: str,
                       records: pd.DataFrame, trades: List[Dict[str, Any]],
                       data: pd.DataFrame, signals: pd.Series,
                       benchmark: Optional[pd.Series] = None,
                       output_dir: str = "./results",
                       initial_cash: float = 100000) -> str:
        """
        Generate complete HTML report.

        Args:
            strategy_name: Name of the strategy
            start_date: Start date of backtest
            end_date: End date of backtest
            records: Portfolio records DataFrame
            trades: List of trade records
            data: Price data DataFrame
            signals: Trading signals Series
            benchmark: Optional benchmark series aligned to records index
            output_dir: Directory to save report and charts
            initial_cash: Initial cash amount

        Returns:
            Path to generated HTML report
        """
        os.makedirs(output_dir, exist_ok=True)

        # Calculate metrics
        perf_metrics = PerformanceMetrics(records, trades, initial_cash)
        all_metrics = perf_metrics.get_all_metrics()

        # Generate charts
        visualizer = BacktestVisualizer(output_dir)
        charts = visualizer.create_summary_dashboard(records, all_metrics, trades, data, signals, benchmark)

        # Prepare key metrics for display
        key_metrics = [
            {'name': '年化收益率', 'value': f"{all_metrics['basic']['annualized_return']:.2%}",
             'positive': all_metrics['basic']['annualized_return'] > 0},
            {'name': '夏普比率', 'value': f"{all_metrics['basic']['sharpe_ratio']:.2f}",
             'positive': all_metrics['basic']['sharpe_ratio'] > 1},
            {'name': '最大回撤', 'value': f"{all_metrics['basic']['max_drawdown']:.2%}",
             'negative': True},
            {'name': '胜率', 'value': f"{all_metrics['trading']['win_rate']:.1%}",
             'positive': all_metrics['trading']['win_rate'] > 0.5},
            {'name': '总交易次数', 'value': f"{all_metrics['trading']['total_trades']}"},
            {'name': '年化波动率', 'value': f"{all_metrics['basic']['annualized_volatility']:.2%}"},
        ]

        # Prepare trade metrics
        trade_metrics = [
            {'name': '总交易次数', 'value': all_metrics['trading']['total_trades']},
            {'name': '盈利交易', 'value': all_metrics['trading']['winning_trades']},
            {'name': '亏损交易', 'value': all_metrics['trading']['losing_trades']},
            {'name': '胜率', 'value': f"{all_metrics['trading']['win_rate']:.1%}"},
            {'name': '平均盈利', 'value': f"${all_metrics['trading']['avg_win']:.2f}"},
            {'name': '平均亏损', 'value': f"${all_metrics['trading']['avg_loss']:.2f}"},
            {'name': '盈利因子', 'value': f"{all_metrics['trading']['profit_factor']:.2f}"},
            {'name': '平均持仓天数', 'value': f"{all_metrics['trading']['avg_trade_duration']:.1f} 天"},
        ]

        # Prepare all metrics for detailed table
        detailed_metrics = []
        for category, cat_metrics in all_metrics.items():
            for key, value in cat_metrics.items():
                if isinstance(value, float):
                    if any(term in key for term in ['return', 'drawdown', 'var', 'cvar', 'rate']):
                        formatted_value = f"{value:.4f}"
                    elif 'ratio' in key:
                        formatted_value = f"{value:.2f}"
                    else:
                        formatted_value = f"{value:.4f}"
                elif isinstance(value, int):
                    formatted_value = f"{value:,}"
                else:
                    formatted_value = str(value)

                detailed_metrics.append({
                    'category': self._get_category_name(category),
                    'name': self._get_metric_name(key),
                    'value': formatted_value
                })

        # Prepare trades for display
        display_trades = trades[-20:]  # Show last 20 trades

        # Context for template
        context = {
            'strategy_name': strategy_name,
            'start_date': start_date,
            'end_date': end_date,
            'initial_cash': initial_cash,
            'final_value': records['value'].iloc[-1],
            'generation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'key_metrics': key_metrics,
            'trade_metrics': trade_metrics,
            'all_metrics': detailed_metrics,
            'trades': display_trades,
            'returns_curve_html': charts['returns_curve_html'],
            'drawdown_chart': self._image_to_base64(charts['drawdown']),
            'signals_chart': self._image_to_base64(charts['signals']),
            'returns_dist_chart': self._image_to_base64(charts['returns_dist']),
        }

        # Generate HTML
        html_content = self.template.render(context)

        # Save report
        report_path = os.path.join(output_dir, 'backtest_report.html')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return report_path

    def _image_to_base64(self, image_path: str) -> str:
        """Convert local image file to a data URI for single-file HTML embedding."""
        with open(image_path, 'rb') as image_file:
            encoded = base64.b64encode(image_file.read()).decode('utf-8')
        return f"data:image/png;base64,{encoded}"

    def _get_category_name(self, category: str) -> str:
        """Get display name for metric category."""
        names = {
            'basic': '基础指标',
            'trading': '交易指标',
            'risk': '风险指标'
        }
        return names.get(category, category)

    def _get_metric_name(self, key: str) -> str:
        """Get display name for metric."""
        names = {
            'total_return': '总收益率',
            'annualized_return': '年化收益率',
            'annualized_volatility': '年化波动率',
            'sharpe_ratio': '夏普比率',
            'max_drawdown': '最大回撤',
            'calmar_ratio': '卡玛比率',
            'sortino_ratio': '索提诺比率',
            'final_value': '最终价值',
            'initial_cash': '初始资金',
            'total_trades': '总交易次数',
            'winning_trades': '盈利交易',
            'losing_trades': '亏损交易',
            'win_rate': '胜率',
            'avg_win': '平均盈利',
            'avg_loss': '平均亏损',
            'profit_factor': '盈利因子',
            'avg_trade_duration': '平均持仓天数',
            'var_95': 'VaR (95%)',
            'cvar_95': 'CVaR (95%)',
            'skewness': '偏度',
            'kurtosis': '峰度',
            'max_consecutive_losses': '最大连续亏损次数'
        }
        return names.get(key, key)

    def save_metrics_csv(self, metrics: Dict[str, Any], output_path: str):
        """Save metrics to CSV file."""
        # Flatten metrics
        flat_metrics = {}
        for category, cat_metrics in metrics.items():
            for key, value in cat_metrics.items():
                flat_metrics[f"{category}_{key}"] = value

        df = pd.DataFrame(list(flat_metrics.items()), columns=['Metric', 'Value'])
        df.to_csv(output_path, index=False)