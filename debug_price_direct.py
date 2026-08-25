from adapters.wallgold.client import WallGoldClient

API_KEY = "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5e0qXd8zLC5PYE9425d863"

client = WallGoldClient(API_KEY)

r = client.session.get(
    f"{client.BASE_URL}/api/v1/account/price",
    params={
        "symbol": "GLD_18C_750TMN",
        "side": "buy"
    }
)

print(r.status_code)
print(r.text)
