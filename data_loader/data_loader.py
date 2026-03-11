"""Data loading module using tushare API."""

import os
import pandas as pd
import tushare as ts


def get_pro_api(token: str = None):
    """Initialize and return a tushare pro API instance."""
    if token is None:
        token = os.environ.get("TUSHARE_TOKEN")
        if token is None:
            raise ValueError("Tushare token must be provided via argument or TUSHARE_TOKEN env var")
    ts.set_token(token)
    return ts.pro_api()


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
    pro = get_pro_api(token)
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df.empty:
        raise ValueError(f"No data returned for {ts_code} {start_date}-{end_date}")
    # convert date to datetime and sort
    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
    df = df.sort_values('trade_date').set_index('trade_date')
    # rename columns to lower case
    df = df.rename(columns={
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'vol': 'volume',
        'amount': 'amount'
    })
    return df
