from datetime import datetime


class MarketScanner:


    def __init__(self, registry):

        self.registry = registry


    def scan(self):

        quotes = []


        for exchange in self.registry.all():

            buy_quote = exchange.get_price("buy")

            sell_quote = exchange.get_price("sell")


            quotes.append(buy_quote)
            quotes.append(sell_quote)


        return {
            "timestamp": datetime.utcnow(),
            "quotes": quotes
        }
