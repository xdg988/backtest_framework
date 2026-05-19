"""Data loading module using tushare API."""

import os
import time
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


def fetch_index_weight(
    index_code: str,
    start_date: str,
    end_date: str,
    token: str = None,
) -> pd.DataFrame:
    """Fetch index constituents and their weights from tushare index_weight.

    Returns
    -------
    pd.DataFrame
        Columns include ['index_code', 'con_code', 'trade_date', 'weight'].
        `weight` is normalized to sum to 1 per (index_code, trade_date).
    """
    code = normalize_ts_code(index_code)
    pro = get_pro_api(token)

    df = pro.index_weight(index_code=code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return pd.DataFrame(columns=['index_code', 'con_code', 'trade_date', 'weight'])

    required = {'index_code', 'con_code', 'trade_date', 'weight'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"index_weight missing columns: {sorted(missing)}")

    out = df[['index_code', 'con_code', 'trade_date', 'weight']].copy()
    out['index_code'] = out['index_code'].map(normalize_ts_code)
    out['con_code'] = out['con_code'].map(normalize_ts_code)
    out['trade_date'] = pd.to_datetime(out['trade_date'], format='%Y%m%d', errors='coerce')
    out['weight'] = pd.to_numeric(out['weight'], errors='coerce')
    out = out.dropna(subset=['trade_date', 'weight'])

    # Tushare weights are often percentage values (sum around 100), normalize robustly.
    sum_by_day = out.groupby(['index_code', 'trade_date'])['weight'].transform('sum')
    out['weight'] = out['weight'] / sum_by_day.where(sum_by_day != 0)
    out = out.dropna(subset=['weight'])
    out = out.sort_values(['index_code', 'trade_date', 'con_code']).reset_index(drop=True)
    return out


def _fetch_financial_statement_batch(
    api_name: str,
    ts_codes: List[str],
    start_date: str,
    end_date: str,
    token: str = None,
    fields: Optional[str] = None,
    sleep_seconds: float = 0.0,
) -> pd.DataFrame:
    if not ts_codes:
        return pd.DataFrame()

    pro = get_pro_api(token)
    api_func = getattr(pro, api_name)
    frames: list[pd.DataFrame] = []

    for raw_code in ts_codes:
        code = normalize_ts_code(raw_code)
        kwargs = {
            'ts_code': code,
            'start_date': start_date,
            'end_date': end_date,
        }
        if fields:
            kwargs['fields'] = fields
        try:
            item = api_func(**kwargs)
        except Exception:
            item = pd.DataFrame()

        if item is not None and not item.empty:
            if 'ts_code' not in item.columns:
                item['ts_code'] = code
            item['ts_code'] = item['ts_code'].map(normalize_ts_code)
            frames.append(item)

        if sleep_seconds and sleep_seconds > 0:
            time.sleep(float(sleep_seconds))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_income_statements(
    ts_codes: List[str],
    start_date: str,
    end_date: str,
    token: str = None,
    fields: Optional[str] = None,
    sleep_seconds: float = 0.0,
) -> pd.DataFrame:
    """Fetch income statements for multiple stocks via tushare income API."""
    return _fetch_financial_statement_batch(
        api_name='income',
        ts_codes=ts_codes,
        start_date=start_date,
        end_date=end_date,
        token=token,
        fields=fields,
        sleep_seconds=sleep_seconds,
    )


def fetch_balancesheet_statements(
    ts_codes: List[str],
    start_date: str,
    end_date: str,
    token: str = None,
    fields: Optional[str] = None,
    sleep_seconds: float = 0.0,
) -> pd.DataFrame:
    """Fetch balance sheet statements for multiple stocks via tushare balancesheet API."""
    return _fetch_financial_statement_batch(
        api_name='balancesheet',
        ts_codes=ts_codes,
        start_date=start_date,
        end_date=end_date,
        token=token,
        fields=fields,
        sleep_seconds=sleep_seconds,
    )


def build_daily_constituent_weight_snapshot(
    index_weight_df: pd.DataFrame,
    start_date: str,
    end_date: str,
    trading_index: Optional[pd.DatetimeIndex] = None,
) -> pd.DataFrame:
    """Forward-fill index constituent weights to daily frequency.

    Parameters
    ----------
    index_weight_df
        Result from `fetch_index_weight`.
    start_date, end_date
        Snapshot date range in YYYYMMDD.
    trading_index
        Optional trading calendar index. If not provided, business-day range is used.
    """
    if index_weight_df is None or index_weight_df.empty:
        return pd.DataFrame(columns=['trade_date', 'index_code', 'con_code', 'weight'])

    required = {'index_code', 'con_code', 'trade_date', 'weight'}
    missing = required - set(index_weight_df.columns)
    if missing:
        raise ValueError(f"index_weight_df missing columns: {sorted(missing)}")

    work = index_weight_df.copy()
    work['trade_date'] = pd.to_datetime(work['trade_date'])
    work = work.sort_values(['index_code', 'trade_date', 'con_code']).reset_index(drop=True)

    if trading_index is None:
        calendar = pd.date_range(pd.Timestamp(start_date), pd.Timestamp(end_date), freq='B')
    else:
        calendar = pd.DatetimeIndex(trading_index)
    calendar_df = pd.DataFrame({'trade_date': calendar})

    snapshots: list[pd.DataFrame] = []
    for index_code, group in work.groupby('index_code'):
        rebalance_days = pd.DataFrame({'rebalance_date': sorted(group['trade_date'].drop_duplicates())})
        day_map = pd.merge_asof(
            calendar_df.sort_values('trade_date'),
            rebalance_days.sort_values('rebalance_date'),
            left_on='trade_date',
            right_on='rebalance_date',
            direction='backward',
        )
        day_map = day_map.dropna(subset=['rebalance_date'])
        if day_map.empty:
            continue

        merged = day_map.merge(
            group,
            left_on='rebalance_date',
            right_on='trade_date',
            how='left',
            suffixes=('_snapshot', '_rebalance'),
        )
        if merged.empty:
            continue

        merged['index_code'] = index_code
        merged = merged.rename(columns={'trade_date_snapshot': 'trade_date'})
        snapshots.append(merged[['trade_date', 'index_code', 'con_code', 'weight']])

    if not snapshots:
        return pd.DataFrame(columns=['trade_date', 'index_code', 'con_code', 'weight'])

    out = pd.concat(snapshots, ignore_index=True)
    out = out.dropna(subset=['con_code', 'weight'])
    out = out.sort_values(['trade_date', 'index_code', 'con_code']).reset_index(drop=True)
    return out


def build_daily_financial_snapshot(
    financial_df: pd.DataFrame,
    start_date: str,
    end_date: str,
    trading_index: Optional[pd.DatetimeIndex] = None,
    id_column: str = 'ts_code',
    date_priority: Optional[List[str]] = None,
    value_columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Convert quarterly financial statements into announcement-date daily snapshots.

    The snapshot only uses data with effective_date <= trade_date to avoid look-ahead.
    """
    if financial_df is None or financial_df.empty:
        columns = ['trade_date', id_column]
        if value_columns:
            columns.extend(value_columns)
        return pd.DataFrame(columns=columns)

    work = financial_df.copy()
    priority = date_priority or ['ann_date', 'f_ann_date', 'end_date']
    effective_col = next((col for col in priority if col in work.columns), None)
    if effective_col is None:
        raise ValueError(f"No date column found in priority list: {priority}")
    if id_column not in work.columns:
        raise ValueError(f"financial_df missing id_column: {id_column}")

    work['effective_date'] = pd.to_datetime(work[effective_col], format='%Y%m%d', errors='coerce')
    work[id_column] = work[id_column].astype(str).map(normalize_ts_code)
    work = work.dropna(subset=['effective_date', id_column])
    if work.empty:
        return pd.DataFrame(columns=['trade_date', id_column])

    if value_columns is None:
        excluded = {id_column, 'effective_date', 'ann_date', 'f_ann_date', 'end_date', 'ts_code'}
        value_columns = [col for col in work.columns if col not in excluded]
    value_columns = [col for col in value_columns if col in work.columns]
    for col in value_columns:
        work[col] = pd.to_numeric(work[col], errors='coerce')

    if trading_index is None:
        calendar = pd.date_range(pd.Timestamp(start_date), pd.Timestamp(end_date), freq='B')
    else:
        calendar = pd.DatetimeIndex(trading_index)

    snapshots: list[pd.DataFrame] = []
    for symbol, group in work.groupby(id_column):
        group = group.sort_values('effective_date').drop_duplicates(subset=['effective_date'], keep='last')
        value_frame = group.set_index('effective_date')[value_columns]
        daily = value_frame.reindex(calendar).ffill()
        daily = daily.reset_index().rename(columns={'index': 'trade_date'})
        daily[id_column] = symbol
        snapshots.append(daily[['trade_date', id_column] + value_columns])

    if not snapshots:
        return pd.DataFrame(columns=['trade_date', id_column] + value_columns)

    out = pd.concat(snapshots, ignore_index=True)
    out = out.sort_values(['trade_date', id_column]).reset_index(drop=True)
    return out
