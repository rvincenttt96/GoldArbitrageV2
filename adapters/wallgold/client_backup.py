import requests
from datetime import datetime

from core.exchange import Exchange
from core.models import Balance, Quote


class WallGoldClient(Exchange):

    BASE_URL = "https://api.wallgold.ir"
    SYMBOL = "GLD_18C_750TMN"


    def __init__(self, api_key):

        self.session = requests.Session()

        self.session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}"
        })


    def get_markets(self):

        response = self.session.get(
            f"{self.BASE_URL}/api/v1/markets"
        )

        return response.json()


    def get_balance(self):

        response = self.session.get(
            f"{self.BASE_URL}/api/v1/account/balances"
        )

        data = response.json()

        balances = []

        for item in data["result"]:

            balances.append(
                Balance(
                    platform="wallgold",
                    currency=item["currency"],
                    amount=float(item["amount"]),
                    locked_amount=float(item["locked_amount"])
                )
            )

        return balances


    def get_price(self, side):

        response = self.session.get(
            f"{self.BASE_URL}/api/v1/account/price",
            params={
                "symbol": self.SYMBOL,
                "side": side
            }
        )

        data = response.json()

        if data.get("success") is not True:
            raise Exception(
                f"WallGold price error: {data}"
            )

        result = data["result"]

        return Quote(
            platform="wallgold",
            symbol=self.SYMBOL,
            side=side,
            price=int(result["price"]),
            expires_at=datetime.fromisoformat(
                result["priceExpiresAt"].replace("Z", "+00:00")
            ),
            ttl=float(result["ttl"]),
            timestamp=datetime.fromisoformat(
                result["currentTime"].replace("Z", "+00:00")
            )
        )


    def buy(self, amount):
        raise NotImplementedError


    def sell(self, amount):
        raise NotImplementedError


    def get_order(self, order_id):
        raise NotImplementedError
