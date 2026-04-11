"""Backtrader strategy for multi-asset ETF rotation signals."""

import backtrader as bt
import pandas as pd


class RotationBacktestStrategy(bt.Strategy):
    """Execute single-target ETF rotation generated from a signal generator."""

    params = (
        ('signal_generator', None),
        ('target_percent', 0.98),
        ('cost_buffer', 0.003),
        ('start_date', None),
    )

    def __init__(self):
        # Store active orders to avoid submitting duplicated rebalance orders on the same bar.
        self.pending_orders = []
        # Filled order records used by report generation.
        self.trades = []
        # Daily account snapshots used by visual/report module.
        self.records = []
        # One-of-N target mode: per date -> selected symbol.
        self.target_series = None
        # Fast symbol->data lookup for order placement.
        self.data_by_name = {data._name: data for data in self.datas}
        self.start_ts = pd.Timestamp(self.params.start_date) if self.params.start_date is not None else None
        self.last_processed_ts = None

    def _build_close_panel(self) -> pd.DataFrame:
        # Build aligned close matrix required by signal generators.
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

    def _run_on_bar(self):
        # Wait until all previous orders are settled before issuing new rebalance orders.
        if self._has_pending_order():
            return

        if self.target_series is None:
            # Signal is generated once from full history, then indexed by current date.
            close_panel = self._build_close_panel()
            self.target_series = self.params.signal_generator.generate_targets(close_panel)

        dt = self.datetime.date(0)
        ts = pd.Timestamp(dt)

        if self.start_ts is not None and ts < self.start_ts:
            return

        # Skip processing if the current timestamp has already been processed.
        if self.last_processed_ts is not None and ts == self.last_processed_ts:
            return
        self.last_processed_ts = ts

        target_code = self.target_series.get(ts, None) if self.target_series is not None else None
        cash_dates = getattr(self.params.signal_generator, 'cash_dates', set())
        force_cash = ts in cash_dates if cash_dates is not None else False

        holding_codes = [
            data._name for data in self.datas
            if self.getposition(data).size > 0
        ]

        target_display = target_code if target_code is not None else ''

        self.records.append({
            'date': dt,
            'cash': self.broker.getcash(),
            'value': self.broker.getvalue(),
            'position': len(holding_codes),
            'target': target_display
        })

        if target_code is None or target_code not in self.data_by_name:
            if force_cash or (isinstance(target_code, str) and target_code == '__CASH__'):
                for data in self.datas:
                    if len(data) == 0:
                        continue
                    pos = self.getposition(data)
                    if pos.size > 0:
                        order = self.order_target_size(data=data, target=0)
                        if order is not None:
                            self.pending_orders.append(order)
            return

        # Close non-target positions.
        submitted_sell = False
        planned_sell_value = 0.0
        for data in self.datas:
            if len(data) == 0:
                continue
            pos = self.getposition(data)
            if pos.size > 0 and data._name != target_code:
                planned_sell_value += float(pos.size) * float(data.close[0])
                order = self.order_target_size(data=data, target=0)
                if order is not None:
                    self.pending_orders.append(order)
                    submitted_sell = True

        buy_target_code = target_code
        if buy_target_code not in self.data_by_name:
            return

        target_data = self.data_by_name[buy_target_code]
        target_pos = self.getposition(target_data)
        if target_pos.size <= 0:
            # Use available cash to open target position with a small reserve for fees/slippage.
            target_percent = max(0.0, min(1.0, float(self.params.target_percent)))
            cost_buffer = max(0.0, min(0.05, float(self.params.cost_buffer)))
            available_cash = float(self.broker.getcash())
            if submitted_sell:
                cash_pool = available_cash + planned_sell_value
                target_value = cash_pool * target_percent * (1.0 - cost_buffer)
            else:
                target_value = available_cash * target_percent * (1.0 - cost_buffer)
            if target_value <= 0:
                return
            order = self.order_target_value(data=target_data, target=target_value)
            if order is not None:
                self.pending_orders.append(order)

    # The following methods are Backtrader lifecycle hooks and order notifications.
    def prenext(self):
        self._run_on_bar()

    def nextstart(self):
        self._run_on_bar()

    def next(self):
        self._run_on_bar()

    def notify_order(self, order):
        # Ignore transient states; keep waiting for final status.
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order in self.pending_orders:
            self.pending_orders.remove(order)

        if order.status == order.Completed:
            size = float(order.executed.size)
            action = 'BUY' if size > 0 else 'SELL'
            # Persist a compact trade log for reporting.
            self.trades.append({
                'date': self.datetime.date(0).isoformat(),
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
