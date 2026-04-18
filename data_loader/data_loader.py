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


def _apply_fund_adjustment(pro, df: pd.DataFrame, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Apply forward-adjusted prices for funds/ETFs using tushare fund_adj factors.

    Keep the latest price unchanged by normalizing adj_factor to the last available value.
    """
    if df.empty:
        return df

    try:
        adj = pro.fund_adj(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception:
        return df

    if adj is None or adj.empty or 'trade_date' not in adj.columns or 'adj_factor' not in adj.columns:
        return df

    adj = adj[['trade_date', 'adj_factor']].copy()
    adj['trade_date'] = pd.to_datetime(adj['trade_date'], format='%Y%m%d')
    adj = adj.sort_values('trade_date').set_index('trade_date')
    factors = adj['adj_factor'].reindex(df.index).ffill().bfill()

    if factors.empty or not pd.notna(factors.iloc[-1]) or float(factors.iloc[-1]) == 0:
        return df

    norm = factors / float(factors.iloc[-1])
    for col in ('open', 'high', 'low', 'close'):
        if col in df.columns:
            df[col] = df[col] * norm

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
    is_fund_data = True
    df = pro.fund_daily(ts_code=code, start_date=start_date, end_date=end_date)
    if df.empty:
        is_fund_data = False
        df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
    if df.empty:
        raise ValueError(f"No data returned for {code} {start_date}-{end_date}")

    out = _standardize_daily_df(df, code)
    out['close_raw'] = out['close']
    if is_fund_data:
        out = _apply_fund_adjustment(pro, out, code, start_date, end_date)
    return out


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

        is_fund_data = True
        df = pro.fund_daily(ts_code=code, start_date=start_date, end_date=end_date)
        if df.empty:
            is_fund_data = False
            df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
        if df.empty:
            continue

        out = _standardize_daily_df(df, code)
        out['close_raw'] = out['close']
        if is_fund_data:
            out = _apply_fund_adjustment(pro, out, code, start_date, end_date)
        data_map[code] = out

    if not data_map:
        raise ValueError(f"No data returned for any symbol in pool ({len(ts_codes)} symbols)")

    return data_map


def fetch_fund_nav_history_multiple(
    ts_codes: List[str],
    start_date: str,
    end_date: str,
    token: str = None,
) -> Dict[str, pd.Series]:
    """Fetch fund NAV history for multiple symbols via tushare fund_nav.

    Returns
    -------
    Dict[str, pd.Series]
        Mapping code -> NAV series indexed by trade date (Timestamp).
    """
    if not ts_codes:
        return {}

    pro = get_pro_api(token)
    nav_history: Dict[str, pd.Series] = {}

    for raw_code in ts_codes:
        code = normalize_ts_code(raw_code)
        try:
            df = pro.fund_nav(ts_code=code, start_date=start_date, end_date=end_date)
        except Exception:
            continue

        if df is None or len(df) == 0:
            continue

        # Source-style premium logic aligns to unit net value on trade date.
        # Prefer nav_date/trade_date and unit_nav; ann_date/other nav fields are fallback only.
        date_col = next((c for c in ["nav_date", "trade_date", "ann_date"] if c in df.columns), None)
        nav_col = next((c for c in ["unit_nav", "adj_nav", "accum_nav"] if c in df.columns), None)
        if date_col is None or nav_col is None:
            continue

        tmp = df[[date_col, nav_col]].dropna().copy()
        if tmp.empty:
            continue

        tmp[date_col] = tmp[date_col].astype(str)
        tmp[nav_col] = pd.to_numeric(tmp[nav_col], errors="coerce")

        s = (
            tmp.sort_values(date_col)
            .drop_duplicates(subset=[date_col], keep="last")
            .set_index(date_col)[nav_col]
            .dropna()
        )
        if s.empty:
            continue

        try:
            s.index = pd.to_datetime(s.index, format='%Y%m%d', errors='coerce')
        except Exception:
            s.index = pd.to_datetime(s.index, errors='coerce')
        s = s[~s.index.isna()].sort_index()
        if s.empty:
            continue

        nav_history[code] = s

    return nav_history


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
