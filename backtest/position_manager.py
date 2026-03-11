"""Position management module providing sizing rules."""


class FixedSize:
    """Position manager that uses a fixed number of shares/contracts each trade."""

    def __init__(self, size: int):
        self.size = size

    def size(self, broker, data) -> int:
        """Return the fixed number of units to trade."""
        return self.size


class PercentRisk:
    """Position manager that risks a fixed percent of portfolio value per trade.

    This example simply allocates percent of total value (long-only).
    """

    def __init__(self, percent: float):
        assert 0 < percent <= 1, "percent must be between 0 and 1"
        self.percent = percent

    def size(self, broker, data) -> int:
        cash = broker.getcash()
        price = data.close[0]
        alloc_cash = cash * self.percent
        return int(alloc_cash // price)


class RiskManager:
    """Risk management module for stop-loss, take-profit, and max drawdown controls."""

    def __init__(self, stop_loss_percent: float = None, take_profit_percent: float = None, max_drawdown_percent: float = None):
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent
        self.max_drawdown_percent = max_drawdown_percent
        self.initial_value = None
        self.peak_value = None

    def check_stop_loss(self, current_value: float, entry_price: float) -> bool:
        """Check if stop-loss condition is met."""
        if self.stop_loss_percent and entry_price:
            return current_value <= entry_price * (1 - self.stop_loss_percent)
        return False

    def check_take_profit(self, current_value: float, entry_price: float) -> bool:
        """Check if take-profit condition is met."""
        if self.take_profit_percent and entry_price:
            return current_value >= entry_price * (1 + self.take_profit_percent)
        return False

    def check_max_drawdown(self, current_value: float) -> bool:
        """Check if max drawdown condition is met."""
        if self.max_drawdown_percent is None:
            return False

        if self.initial_value is None:
            self.initial_value = current_value
            self.peak_value = current_value

        if current_value > self.peak_value:
            self.peak_value = current_value

        drawdown = (self.peak_value - current_value) / self.peak_value
        return drawdown >= self.max_drawdown_percent

    def should_exit_position(self, current_value: float, entry_price: float, portfolio_value: float) -> bool:
        """Check if any risk management condition requires position exit."""
        return (self.check_stop_loss(current_value, entry_price) or
                self.check_take_profit(current_value, entry_price) or
                self.check_max_drawdown(portfolio_value))
