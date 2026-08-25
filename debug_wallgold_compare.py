from adapters.wallgold.client import WallGoldClient

c = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5e0qXd8zLC5PYE9425d863"
)

r = c.session.get(
    f"{c.BASE_URL}/api/v1/account/price",
    params={
        "symbol": c.SYMBOL,
        "side": "buy"
    }
)

print("SYMBOL:", c.SYMBOL)
print("URL:", r.request.url)
print("HEADERS:", r.request.headers)
print("STATUS:", r.status_code)
print("TEXT:", r.text)
