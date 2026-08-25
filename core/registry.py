class ExchangeRegistry:


    def __init__(self):

        self.exchanges = []


    def add(self, exchange):

        self.exchanges.append(exchange)


    def all(self):

        return self.exchanges
