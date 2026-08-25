from datetime import datetime

from core.models import Opportunity
from config.settings import (
    MILLIGOLD_BUY_FEE,
    MILLIGOLD_SELL_FEE,
    WALLGOLD_BUY_FEE,
    WALLGOLD_SELL_FEE
)


class OpportunityFinder:


    def find(self, scan_result, amount):

        quotes = scan_result["quotes"]

        buy_quotes = [
            q for q in quotes
            if q.side == "buy"
        ]

        sell_quotes = [
            q for q in quotes
            if q.side == "sell"
        ]


        if not buy_quotes or not sell_quotes:
            return None


        best_buy = min(
            buy_quotes,
            key=lambda x: x.price
        )


        best_sell = max(
            sell_quotes,
            key=lambda x: x.price
        )


        if best_buy.platform == best_sell.platform:
            return None


        gross_profit = (
            best_sell.price - best_buy.price
        ) * amount


        return Opportunity(

            buy_platform=best_buy.platform,

            sell_platform=best_sell.platform,

            symbol=best_buy.symbol,

            amount=amount,

            buy_price=best_buy.price,

            sell_price=best_sell.price,

            gross_profit=gross_profit,

            buy_fee=0,

            sell_fee=0,

            net_profit=gross_profit,

            timestamp=datetime.now()
        )
