"""Data loading module using tushare API."""

import os
import pandas as pd
import tushare as ts
from typing import Dict, List, Optional


def get_pro_api(token: str = None):
    """Initialize and return a tushare pro API instance."""
    if token is None:
        token = os.environ.get("TUSHARE_TOKEN")
        if token is None:
            raise ValueError("Tushare token must be provided via argument or TUSHARE_TOKEN env var")
    ts.set_token(token)
    return ts.pro_api()


def normalize_ts_code(ts_code: str) -> str:
    """Convert common JoinQuant suffix to tushare suffix if needed."""
    code = ts_code.strip()
    if code.endswith('.XSHG'):
        return code.replace('.XSHG', '.SH')
    if code.endswith('.XSHE'):
        return code.replace('.XSHE', '.SZ')
    return code


def _standardize_daily_df(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df.empty:
        raise ValueError(f"No data returned for {ts_code}")

    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
    df = df.sort_values('trade_date').set_index('trade_date')
    df = df.rename(columns={
        'vol': 'volume',
        'amount': 'amount',
    })

    needed_cols = ['open', 'high', 'low', 'close', 'volume']
    for col in needed_cols:
        if col not in df.columns:
            df[col] = 0.0
    return df


def fetch_daily(ts_code: str, start_date: str, end_date: str, token: str = None) -> pd.DataFrame:
    """Fetch daily bar data for a given security code.

    Parameters
    ----------
    ts_code : str
        Tushare stock code, e.g. '000001.SZ'.
    start_date : str
        YYYYMMDD format.
    end_date : str
        YYYYMMDD format.
    token : str
        Optional tushare token.

    Returns
    -------
    pd.DataFrame
        DataFrame indexed by date with columns ['open','high','low','close','vol','amount'].
    """
    code = normalize_ts_code(ts_code)
    pro = get_pro_api(token)

    # ETF/fund first, then fallback to stock daily.
    df = pro.fund_daily(ts_code=code, start_date=start_date, end_date=end_date)
    if df.empty:
        df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
    if df.empty:
        raise ValueError(f"No data returned for {code} {start_date}-{end_date}")

    return _standardize_daily_df(df, code)


def fetch_daily_multiple(ts_codes: List[str], start_date: str, end_date: str, token: str = None) -> Dict[str, pd.DataFrame]:
    """Fetch daily bars for multiple symbols.

    Returns a mapping of normalized tushare code -> standardized OHLCV DataFrame.
    """
    if not ts_codes:
        raise ValueError("ts_codes cannot be empty")

    pro = get_pro_api(token)
    data_map: Dict[str, pd.DataFrame] = {}

    for raw_code in ts_codes:
        code = normalize_ts_code(raw_code)

        df = pro.fund_daily(ts_code=code, start_date=start_date, end_date=end_date)
        if df.empty:
            df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
        if df.empty:
            continue

        data_map[code] = _standardize_daily_df(df, code)

    if not data_map:
        raise ValueError(f"No data returned for any symbol in pool ({len(ts_codes)} symbols)")

    return data_map


def fetch_benchmark_series(start_date: str,
                           end_date: str,
                           token: str = None,
                           benchmark_code: str = '000300.SH') -> Optional[pd.Series]:
    """Fetch benchmark close series (default HS300) with multiple tushare fallbacks."""
    code = normalize_ts_code(benchmark_code)
    pro = get_pro_api(token)

    df = pd.DataFrame()

    # Preferred: index daily API.
    try:
        df = pro.index_daily(ts_code=code, start_date=start_date, end_date=end_date)
    except Exception:
        df = pd.DataFrame()

    # Fallback: pro_bar index asset.
    if df is None or df.empty:
        try:
            df = ts.pro_bar(ts_code=code, start_date=start_date, end_date=end_date, asset='I')
        except Exception:
            df = pd.DataFrame()

    # Final fallback for HS300 when index permissions are restricted.
    if (df is None or df.empty) and code == '000300.SH':
        try:
            df = pro.fund_daily(ts_code='510300.SH', start_date=start_date, end_date=end_date)
        except Exception:
            df = pd.DataFrame()

    if df is None or df.empty:
        return None

    if 'trade_date' not in df.columns or 'close' not in df.columns:
        return None

    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
    df = df.sort_values('trade_date').set_index('trade_date')
    benchmark = df['close'].dropna()
    if benchmark.empty:
        return None
    benchmark.name = code
    return benchmark
