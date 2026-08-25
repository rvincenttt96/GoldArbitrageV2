from adapters.wallgold.client import WallGoldClient


API_KEY = "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"


client = WallGoldClient(API_KEY)


response = client.session.get(
    f"{client.BASE_URL}/api/v1/account/price",
    params={
        "symbol": client.SYMBOL,
        "side": "buy"
    }
)


print(response.json())
