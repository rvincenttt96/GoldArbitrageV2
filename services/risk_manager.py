from config.settings import (
    MIN_NET_PROFIT,
    MAX_TRADE_AMOUNT,
    MIN_TRADE_AMOUNT
)


class RiskManager:

    def check(
        self,
        opportunity,
        buy_portfolio,
        sell_portfolio
    ):

        if opportunity is None:
            return False

        if (
            opportunity.net_profit
            <
            MIN_NET_PROFIT
        ):
            return False

        if (
            opportunity.amount
            <
            MIN_TRADE_AMOUNT
        ):
            return False

        if (
            opportunity.amount
            >
            MAX_TRADE_AMOUNT
        ):
            return False

        # Cash requirement must include the buy fee.
        required_cash = (
            opportunity.buy_price
            *
            opportunity.amount
            +
            opportunity.buy_fee
        )

        if (
            buy_portfolio.available_cash()
            +
            1e-9
            <
            required_cash
        ):
            return False

        if (
            sell_portfolio.available_gold()
            +
            1e-9
            <
            opportunity.amount
        ):
            return False

        return True
