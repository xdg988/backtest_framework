"""Backtrader strategy for multi-asset weight-based ETF rotation signals."""

import backtrader as bt
import pandas as pd


class WeightRotationBacktestStrategy(bt.Strategy):
    """Execute weight-target ETF rotation generated from a signal generator."""

    params = (
        ('signal_generator', None),
        ('target_percent', 0.98),
        ('cost_buffer', 0.003),
        ('start_date', None),
    )

    def __init__(self):
        self.pending_orders = []
        self.trades = []
        self.records = []
        self.target_weights = None
        self.last_target_weights = {}
        self.data_by_name = {data._name: data for data in self.datas}
        self.start_ts = pd.Timestamp(self.params.start_date) if self.params.start_date is not None else None

    def _build_close_panel(self) -> pd.DataFrame:
        panel = {}
        for data in self.datas:
            df = data.p.dataname
            if isinstance(df, pd.DataFrame) and 'close' in df.columns:
                panel[data._name] = df['close'].copy()
        return pd.DataFrame(panel).sort_index()

    def _has_pending_order(self) -> bool:
        self.pending_orders = [o for o in self.pending_orders if o.alive()]
        return len(self.pending_orders) > 0

    def _current_position_percent(self, data) -> float:
        pos = self.getposition(data)
        if pos.size == 0:
            return 0.0
        price = float(data.close[0]) if len(data) > 0 else 0.0
        if price <= 0:
            return 0.0
        value = float(self.broker.getvalue())
        if value <= 0:
            return 0.0
        return (float(pos.size) * price) / value

    def next(self):
        if self._has_pending_order():
            return

        if self.target_weights is None:
            close_panel = self._build_close_panel()
            self.target_weights = self.params.signal_generator.generate_target_weights(close_panel)

        dt = self.datas[0].datetime.date(0)
        ts = pd.Timestamp(dt)

        if self.start_ts is not None and ts < self.start_ts:
            return

        raw_weights = None
        if self.target_weights is not None and ts in self.target_weights.index:
            raw_weights = self.target_weights.loc[ts]

        holding_codes = [
            data._name for data in self.datas
            if self.getposition(data).size > 0
        ]

        target_display = ''
        if raw_weights is not None:
            nonzero = raw_weights.dropna()
            nonzero = nonzero[nonzero > 0]
            if not nonzero.empty:
                target_display = ';'.join(f"{k}:{v:.2f}" for k, v in nonzero.items())

        self.records.append({
            'date': dt,
            'cash': self.broker.getcash(),
            'value': self.broker.getvalue(),
            'position': len(holding_codes),
            'target': target_display
        })

        if raw_weights is None:
            return

        target_weights = raw_weights.dropna()
        target_weights = target_weights[target_weights > 0]
        if target_weights.empty:
            return

        total_weight = float(target_weights.sum())
        if total_weight <= 0:
            return
        target_weights = target_weights / total_weight

        scaled = {
            code: float(weight) * max(0.0, min(1.0, float(self.params.target_percent))) *
                  (1.0 - max(0.0, min(0.05, float(self.params.cost_buffer))))
            for code, weight in target_weights.items()
            if code in self.data_by_name
        }

        keys = set(scaled.keys()) | set(self.last_target_weights.keys())
        changed = any(abs(float(scaled.get(k, 0.0)) - float(self.last_target_weights.get(k, 0.0))) > 1e-6 for k in keys)
        if not changed:
            return

        use_sell_first_same_bar = bool(getattr(self.params.signal_generator, 'sell_first_same_bar', False))

        needs_reduce = []
        for data in self.datas:
            curr_pct = self._current_position_percent(data)
            tgt_pct = float(scaled.get(data._name, 0.0))
            if curr_pct > tgt_pct + 1e-4:
                needs_reduce.append((data, tgt_pct))

        if needs_reduce and not use_sell_first_same_bar:
            for data, tgt_pct in needs_reduce:
                order = self.order_target_percent(data=data, target=tgt_pct)
                if order is not None:
                    self.pending_orders.append(order)
            return

        if use_sell_first_same_bar and needs_reduce:
            for data, tgt_pct in needs_reduce:
                order = self.order_target_percent(data=data, target=tgt_pct)
                if order is not None:
                    self.pending_orders.append(order)

        reduced_codes = {data._name for data, _ in needs_reduce}
        for data in self.datas:
            if use_sell_first_same_bar and data._name in reduced_codes:
                continue
            target_pct = float(scaled.get(data._name, 0.0))
            order = self.order_target_percent(data=data, target=target_pct)
            if order is not None:
                self.pending_orders.append(order)

        self.last_target_weights = scaled

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
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(
                f"Order {order.getstatusname()}: "
                f"symbol={order.data._name}, size={order.created.size}, "
                f"cash={self.broker.getcash():.2f}, value={self.broker.getvalue():.2f}"
            )
