"""Data loaders for constituent-based multi-factor workflows."""

from __future__ import annotations

import time
from typing import List, Optional

import pandas as pd

from .data_loader import get_pro_api, normalize_ts_code


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
    """Forward-fill index constituent weights to daily frequency."""
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


__all__ = [
    'fetch_index_weight',
    'fetch_income_statements',
    'fetch_balancesheet_statements',
    'build_daily_constituent_weight_snapshot',
    'build_daily_financial_snapshot',
]
