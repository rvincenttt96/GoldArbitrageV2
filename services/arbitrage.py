from datetime import datetime

from core.models import Opportunity
from config.settings import (
    MIN_NET_PROFIT,
    SAFETY_MARGIN
)


class ArbitrageEngine:


    def __init__(self, fee_engine):

        self.fee_engine = fee_engine



    def evaluate(
        self,
        buy_quote,
        sell_quote,
        amount
    ):

        buy_value = (
            buy_quote.price * amount
        )

        sell_value = (
            sell_quote.price * amount
        )


        gross_profit = (
            sell_value - buy_value
        )


        buy_fee = self.fee_engine.calculate_fee(
            buy_quote.platform,
            "buy",
            buy_value
        )


        sell_fee = self.fee_engine.calculate_fee(
            sell_quote.platform,
            "sell",
            sell_value
        )


        net_profit = (
            gross_profit
            - buy_fee
            - sell_fee
            - SAFETY_MARGIN
        )


        if net_profit < MIN_NET_PROFIT:
            return None


        return Opportunity(
            buy_platform=buy_quote.platform,
            sell_platform=sell_quote.platform,
            symbol=buy_quote.symbol,
            amount=amount,
            buy_price=buy_quote.price,
            sell_price=sell_quote.price,
            gross_profit=gross_profit,
            buy_fee=buy_fee,
            sell_fee=sell_fee,
            net_profit=net_profit,
            timestamp=datetime.utcnow()
        )
