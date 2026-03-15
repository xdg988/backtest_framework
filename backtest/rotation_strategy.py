"""Backtrader strategy for multi-asset ETF rotation signals."""

import backtrader as bt
import pandas as pd


class RotationBacktestStrategy(bt.Strategy):
    """Execute target-ETF rotation generated from a multi-asset signal generator."""

    params = (
        ('signal_generator', None),
        ('target_percent', 0.98),
        ('cost_buffer', 0.003),
    )

    def __init__(self):
        self.pending_orders = []
        self.trades = []
        self.records = []
        self.target_series = None
        self.target_weights = None
        self.use_weight_targets = False
        self.last_target_weights = {}
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

        if self.target_series is None and self.target_weights is None:
            close_panel = self._build_close_panel()
            if hasattr(self.params.signal_generator, 'generate_target_weights'):
                self.target_weights = self.params.signal_generator.generate_target_weights(close_panel)
                self.use_weight_targets = True
            else:
                self.target_series = self.params.signal_generator.generate_targets(close_panel)

        dt = self.datas[0].datetime.date(0)
        ts = pd.Timestamp(dt)
        target_code = self.target_series.get(ts, None) if self.target_series is not None else None

        raw_weights = None
        if self.use_weight_targets and self.target_weights is not None and ts in self.target_weights.index:
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
        elif target_code is not None:
            target_display = target_code

        self.records.append({
            'date': dt,
            'cash': self.broker.getcash(),
            'value': self.broker.getvalue(),
            'position': len(holding_codes),
            'target': target_display
        })

        if self.use_weight_targets:
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

            for data in self.datas:
                target_pct = float(scaled.get(data._name, 0.0))
                order = self.order_target_percent(data=data, target=target_pct)
                if order is not None:
                    self.pending_orders.append(order)

            self.last_target_weights = scaled
            return

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
            target_percent = max(0.0, min(1.0, float(self.params.target_percent)))
            cost_buffer = max(0.0, min(0.05, float(self.params.cost_buffer)))
            available_cash = float(self.broker.getcash())
            target_value = available_cash * target_percent * (1.0 - cost_buffer)
            if target_value <= 0:
                return
            order = self.order_target_value(data=target_data, target=target_value)
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
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(
                f"Order {order.getstatusname()}: "
                f"symbol={order.data._name}, size={order.created.size}, "
                f"cash={self.broker.getcash():.2f}, value={self.broker.getvalue():.2f}"
            )
