"""Custom broker with sell-first execution ordering on each bar."""

from __future__ import annotations

from backtrader.brokers import bbroker
from backtrader.order import Order


class SellFirstBackBroker(bbroker.BackBroker):
    """BackBroker variant that processes sell orders before buy orders."""

    def _process_pending_order(self, order):
        if order.expire():
            self.notify(order)
            self._ococheck(order)
            self._bracketize(order, cancel=True)
            return

        if not order.active():
            self.pending.append(order)
            return

        self._try_exec(order)
        if order.alive():
            self.pending.append(order)
        elif order.status == Order.Completed:
            self._bracketize(order)

    def next(self):
        while self._toactivate:
            self._toactivate.popleft().activate()

        if self.p.checksubmit:
            self.check_submitted()

        credit = 0.0
        for data, pos in self.positions.items():
            if pos:
                comminfo = self.getcommissioninfo(data)
                dt0 = data.datetime.datetime()
                dcredit = comminfo.get_credit_interest(data, pos, dt0)
                self.d_credit[data] += dcredit
                credit += dcredit
                pos.datetime = dt0

        self.cash -= credit

        self._process_order_history()

        self.pending.append(None)
        pending_orders = []
        while True:
            order = self.pending.popleft()
            if order is None:
                break
            pending_orders.append(order)

        sell_orders = [o for o in pending_orders if not o.isbuy()]
        buy_orders = [o for o in pending_orders if o.isbuy()]

        for order in sell_orders:
            self._process_pending_order(order)

        for order in buy_orders:
            self._process_pending_order(order)

        for data, pos in self.positions.items():
            if pos:
                comminfo = self.getcommissioninfo(data)
                self.cash += comminfo.cashadjust(pos.size,
                                                 pos.adjbase,
                                                 data.close[0])
                pos.adjbase = data.close[0]

        self._get_value()
