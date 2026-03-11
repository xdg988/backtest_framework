"""Local CSV data loading demo.

This module demonstrates how to load OHLCV stock data from a local CSV file
into the same format expected by the backtest engine.
"""

import pandas as pd


def load_stock_csv(csv_path: str, date_col: str = "trade_date") -> pd.DataFrame:
    """Load local stock CSV and normalize columns for backtest usage.

    Expected columns (example):
    - trade_date (YYYYMMDD or YYYY-MM-DD)
    - open, high, low, close
    - vol or volume
    - amount (optional)
    """
    df = pd.read_csv(csv_path)

    if date_col not in df.columns:
        raise ValueError(f"Missing date column: {date_col}")

    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).set_index(date_col)

    if "vol" in df.columns and "volume" not in df.columns:
        df = df.rename(columns={"vol": "volume"})

    required = ["open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    keep_cols = ["open", "high", "low", "close", "volume"]
    if "amount" in df.columns:
        keep_cols.append("amount")

    return df[keep_cols]


if __name__ == "__main__":
    # Demo usage (replace with your own local file)
    sample_path = "./sample_stock.csv"
    print("CSV loading demo, file path:", sample_path)
    print("Example:")
    print("    from data_loader.load_csv import load_stock_csv")
    print("    data = load_stock_csv('./sample_stock.csv')")
