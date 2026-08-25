import requests


class MilliGoldClient:

    BASE_URL = "https://milli.gold"

    def __init__(self, username, password):

        self.username = username
        self.password = password

        self.session = requests.Session()

        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Channel": "MILLI",
            "X-Platform": "PWA",
            "X-Client-Version": "1.0.0",
            "X-Release-Version": "827b1711"
        })


    def login(self):

        response = self.session.post(
            f"{self.BASE_URL}/api/v1/public/user/v2/login",
            json={
                "username": self.username,
                "password": self.password
            }
        )

        data = response.json()

        print("MILLI LOGIN STATUS:", response.status_code)
        print("MILLI LOGIN RESPONSE:", data)

        if data.get("code") != 0:
            raise Exception(
                f"Milli login failed: {data}"
            )

        return data

    def get_price(self, side):

        response = requests.get(
            f"{self.BASE_URL}/api/v1/public/milli-price/external",
            headers={
                "Accept": "application/json"
            }
        )

        data = response.json()

        print("MILLI PRICE RESPONSE:", data)

        if "data" not in data:
            raise Exception(
                f"Milli price error: {data}"
            )

        result = data["data"]

        price = result.get("price18")

        return {
            "platform": "miligold",
            "symbol": "GLD_18C_750TMN",
            "side": side,
            "price": int(price)
        }

