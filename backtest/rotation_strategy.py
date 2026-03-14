"""Backtrader strategy for multi-asset ETF rotation signals."""

import backtrader as bt
import pandas as pd


class RotationBacktestStrategy(bt.Strategy):
    """Execute target-ETF rotation generated from a multi-asset signal generator."""

    params = (
        ('signal_generator', None),
    )

    def __init__(self):
        self.pending_orders = []
        self.trades = []
        self.records = []
        self.target_series = None
        self.data_by_name = {data._name: data for data in self.datas}

    def _build_close_panel(self) -> pd.DataFrame:
        panel = {}
        for data in self.datas:
            df = data.p.dataname
            if isinstance(df, pd.DataFrame) and 'close' in df.columns:
                panel[data._name] = df['close'].copy()
        close_panel = pd.DataFrame(panel).sort_index()
        return close_panel

    def _has_pending_order(self) -> bool:
        self.pending_orders = [o for o in self.pending_orders if o.alive()]
        return len(self.pending_orders) > 0

    def next(self):
        if self._has_pending_order():
            return

        if self.target_series is None:
            close_panel = self._build_close_panel()
            self.target_series = self.params.signal_generator.generate_targets(close_panel)

        dt = self.datas[0].datetime.date(0)
        ts = pd.Timestamp(dt)
        target_code = self.target_series.get(ts, None)

        holding_codes = [
            data._name for data in self.datas
            if self.getposition(data).size > 0
        ]

        self.records.append({
            'date': dt,
            'cash': self.broker.getcash(),
            'value': self.broker.getvalue(),
            'position': len(holding_codes),
            'target': target_code if target_code is not None else ''
        })

        if target_code is None or target_code not in self.data_by_name:
            return

        # Close non-target positions.
        for data in self.datas:
            pos = self.getposition(data)
            if pos.size > 0 and data._name != target_code:
                order = self.order_target_size(data=data, target=0)
                if order is not None:
                    self.pending_orders.append(order)

        target_data = self.data_by_name[target_code]
        target_pos = self.getposition(target_data)
        if target_pos.size <= 0:
            order = self.order_target_percent(data=target_data, target=1.0)
            if order is not None:
                self.pending_orders.append(order)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order in self.pending_orders:
            self.pending_orders.remove(order)

        if order.status == order.Completed:
            size = float(order.executed.size)
            action = 'BUY' if size > 0 else 'SELL'
            self.trades.append({
                'date': self.datas[0].datetime.date(0).isoformat(),
                'action': action,
                'symbol': order.data._name,
                'price': float(order.executed.price),
                'size': int(abs(size)),
            })
