"""Test script to verify reporting functionality with mock data."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from reporting import BacktestVisualizer, PerformanceMetrics, ReportGenerator

def create_mock_data():
    """Create mock trading data for testing."""
    dates = pd.date_range('2021-01-01', '2021-12-31', freq='D')
    np.random.seed(42)

    # Generate mock price data
    prices = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)

    df = pd.DataFrame({
        'trade_date': dates,
        'open': prices * 0.99,
        'high': prices * 1.01,
        'low': prices * 0.99,
        'close': prices,
        'volume': np.random.randint(100000, 1000000, len(dates))
    })

    # Convert to backtrader format
    df['date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('date')
    df = df[['open', 'high', 'low', 'close', 'volume']]

    return df

def create_mock_records():
    """Create mock portfolio records."""
    dates = pd.date_range('2021-01-01', '2021-12-31', freq='D')
    cash = 100000.0
    records = []

    for i, date in enumerate(dates):
        # Simulate some trades
        if i % 30 == 0 and i > 0:  # Trade every 30 days
            position = 100 if np.random.random() > 0.5 else -100
            cash -= position * 10  # Mock price impact
        else:
            position = 0

        value = cash + (position * 10 if position != 0 else 0)
        records.append({
            'date': date,
            'cash': cash,
            'value': value,
            'position': position
        })

    return pd.DataFrame(records).set_index('date')

def create_mock_trades():
    """Create mock trade records."""
    return [
        {'date': '2021-01-30', 'type': 'BUY', 'price': 98.5, 'size': 100},
        {'date': '2021-03-01', 'type': 'SELL', 'price': 102.3, 'size': 100},
        {'date': '2021-06-15', 'type': 'BUY', 'price': 105.7, 'size': 150},
        {'date': '2021-09-20', 'type': 'SELL', 'price': 108.9, 'size': 150},
    ]

def create_mock_signals():
    """Create mock signal data."""
    dates = pd.date_range('2021-01-01', '2021-12-31', freq='D')
    signals = pd.Series(np.random.choice([-1, 0, 1], len(dates), p=[0.1, 0.8, 0.1]), index=dates)
    return signals

def test_reporting():
    """Test the complete reporting functionality."""
    print("Creating mock data...")

    # Create mock data
    df = create_mock_data()
    records = create_mock_records()
    trades = create_mock_trades()
    signals = create_mock_signals()

    print("Generating comprehensive report...")

    # Create report generator
    report_gen = ReportGenerator()

    # Generate report
    report_path = report_gen.generate_report(
        strategy_name='TestStrategy',
        start_date='20210101',
        end_date='20211231',
        records=records,
        trades=trades,
        data=df,
        signals=signals,
        output_dir='./results',
        initial_cash=100000
    )

    print(f"Report generated successfully: {report_path}")

    # Check if files were created
    import os
    if os.path.exists('./results/backtest_report.html'):
        print("✓ HTML report created")
    else:
        print("✗ HTML report not found")

    if os.path.exists('./results/portfolio_value.png'):
        print("✓ Portfolio chart created")
    else:
        print("✗ Portfolio chart not found")

    if os.path.exists('./results/price_signals.png'):
        print("✓ Price/signals chart created")
    else:
        print("✗ Price/signals chart not found")

if __name__ == '__main__':
    test_reporting()