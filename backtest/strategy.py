"""
Backtrader strategy class that uses external signal generators.
"""

import backtrader as bt
import pandas as pd

from strategies import SMACrossover, RSIStrategy, MACDStrategy, KDJStrategy, BollingerStrategy, MultiFactorStrategy


class BacktestStrategy(bt.Strategy):
    """Backtrader strategy that uses an external signal generator and position manager."""

    params = (
        ('signal_generator', None),
        ('position_manager', None),
        ('risk_manager', None),
    )

    def __init__(self):
        # keep references for analyzers
        self.order = None
        self.signal = None
        self.entry_price = None  # track entry price for risk management
        # history of daily metrics
        self.records = []  # will hold dicts with date, cash, value, position

    def next(self):
        # if we have a pending order, skip
        if self.order:
            return

        # compute signal for the current bar
        # note: our signal generator expects a pandas DataFrame; we grab all history
        if self.signal is None:
            self.signal = self.params.signal_generator.generate(self.datas[0].p.dataname.copy())

        dt = self.datas[0].datetime.date(0)
        sig = self.signal.get(pd.Timestamp(dt), 0)

        position_size = self.position.size
        # record daily state regardless of signal
        self.records.append({
            'date': dt,
            'cash': self.broker.getcash(),
            'value': self.broker.getvalue(),
            'position': position_size,
        })

        # if buy signal and no position
        if sig == 1 and position_size <= 0:
            size = self.params.position_manager.size(self.broker, self.datas[0])
            if size > 0:
                self.order = self.buy(size=size)
                self.entry_price = self.datas[0].close[0]  # record entry price
        # if sell signal and have long
        elif sig == -1 and position_size > 0:
            self.order = self.sell(size=position_size)
            self.entry_price = None  # reset entry price

        # Check risk management conditions
        if self.params.risk_manager and position_size > 0 and self.entry_price:
            current_price = self.datas[0].close[0]
            portfolio_value = self.broker.getvalue()
            if self.params.risk_manager.should_exit_position(current_price, self.entry_price, portfolio_value):
                self.log(f'RISK EXIT: Current price {current_price:.2f}, Entry price {self.entry_price:.2f}')
                self.order = self.sell(size=position_size)
                self.entry_price = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # order is active but not yet executed
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size}')
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size}')
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        # reset order pointer
        self.order = None

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')
