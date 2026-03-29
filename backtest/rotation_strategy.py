"""Backtrader strategy for multi-asset ETF rotation signals."""

import backtrader as bt
import pandas as pd


class RotationBacktestStrategy(bt.Strategy):
    """Execute target-ETF rotation generated from a multi-asset signal generator."""

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
        # Weight mode: per date -> weight vector.
        self.target_weights = None
        self.use_weight_targets = False
        # Last submitted weights, used to skip no-op rebalances.
        self.last_target_weights = {}
        # Fast symbol->data lookup for order placement.
        self.data_by_name = {data._name: data for data in self.datas}
        self.start_ts = pd.Timestamp(self.params.start_date) if self.params.start_date is not None else None
        # Optional two-stage single-target rebalance: sell first, buy with refreshed cash.
        self.deferred_target_code = None

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
        # Wait until all previous orders are settled before issuing new rebalance orders.
        if self._has_pending_order():
            return

        if self.target_series is None and self.target_weights is None:
            # Signal is generated once from full history, then indexed by current date.
            close_panel = self._build_close_panel()
            if hasattr(self.params.signal_generator, 'generate_target_weights'):
                self.target_weights = self.params.signal_generator.generate_target_weights(close_panel)
                self.use_weight_targets = True
            else:
                self.target_series = self.params.signal_generator.generate_targets(close_panel)

        dt = self.datas[0].datetime.date(0)
        ts = pd.Timestamp(dt)

        if self.start_ts is not None and ts < self.start_ts:
            return

        target_code = self.target_series.get(ts, None) if self.target_series is not None else None
        cash_dates = getattr(self.params.signal_generator, 'cash_dates', set())
        force_cash = ts in cash_dates if cash_dates is not None else False
        use_sell_then_buy = bool(getattr(self.params.signal_generator, 'sell_then_buy_recalc_cash', False))
        use_sell_first_same_bar = bool(getattr(self.params.signal_generator, 'sell_first_same_bar', False))

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

            # Keep only positive finite target weights and normalize to 1.
            target_weights = raw_weights.dropna()
            target_weights = target_weights[target_weights > 0]
            if target_weights.empty:
                return

            total_weight = float(target_weights.sum())
            if total_weight <= 0:
                return
            target_weights = target_weights / total_weight

            # Apply deployment ratio (target_percent) and reserve cost buffer.
            scaled = {
                code: float(weight) * max(0.0, min(1.0, float(self.params.target_percent))) *
                      (1.0 - max(0.0, min(0.05, float(self.params.cost_buffer))))
                for code, weight in target_weights.items()
                if code in self.data_by_name
            }

            # Skip placing orders when effective allocation did not change.
            keys = set(scaled.keys()) | set(self.last_target_weights.keys())
            changed = any(abs(float(scaled.get(k, 0.0)) - float(self.last_target_weights.get(k, 0.0))) > 1e-6 for k in keys)
            if not changed:
                return

            # Stage 1: reduce overweight positions first to release cash.
            needs_reduce = []
            for data in self.datas:
                curr_pct = self._current_position_percent(data)
                tgt_pct = float(scaled.get(data._name, 0.0))
                if curr_pct > tgt_pct + 1e-4:
                    needs_reduce.append((data, tgt_pct))

            if needs_reduce:
                for data, tgt_pct in needs_reduce:
                    order = self.order_target_percent(data=data, target=tgt_pct)
                    if order is not None:
                        self.pending_orders.append(order)
                return

            # Rebalance all instruments to target percentages (including zero weight positions).
            for data in self.datas:
                target_pct = float(scaled.get(data._name, 0.0))
                order = self.order_target_percent(data=data, target=target_pct)
                if order is not None:
                    self.pending_orders.append(order)

            self.last_target_weights = scaled
            return

        if target_code is None or target_code not in self.data_by_name:
            self.deferred_target_code = None
            if force_cash or (isinstance(target_code, str) and target_code == '__CASH__'):
                for data in self.datas:
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
            pos = self.getposition(data)
            if pos.size > 0 and data._name != target_code:
                planned_sell_value += float(pos.size) * float(data.close[0])
                order = self.order_target_size(data=data, target=0)
                if order is not None:
                    self.pending_orders.append(order)
                    submitted_sell = True

        if submitted_sell and use_sell_then_buy:
            self.deferred_target_code = target_code
            return

        buy_target_code = self.deferred_target_code if self.deferred_target_code is not None else target_code
        if buy_target_code not in self.data_by_name:
            self.deferred_target_code = None
            return

        target_data = self.data_by_name[buy_target_code]
        target_pos = self.getposition(target_data)
        if target_pos.size <= 0:
            # Use available cash to open target position with a small reserve for fees/slippage.
            target_percent = max(0.0, min(1.0, float(self.params.target_percent)))
            cost_buffer = max(0.0, min(0.05, float(self.params.cost_buffer)))
            available_cash = float(self.broker.getcash())
            if use_sell_first_same_bar and submitted_sell:
                cash_pool = available_cash + planned_sell_value
                target_value = cash_pool * target_percent * (1.0 - cost_buffer)
            else:
                target_value = available_cash * target_percent * (1.0 - cost_buffer)
            if target_value <= 0:
                return
            order = self.order_target_value(data=target_data, target=target_value)
            if order is not None:
                self.pending_orders.append(order)
                self.deferred_target_code = None
        else:
            self.deferred_target_code = None

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
