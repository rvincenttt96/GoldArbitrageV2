from adapters.wallgold.client import WallGoldClient

c = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"
)

print("SESSION HEADERS")
print(c.session.headers)

print("AUTH HEADER")
print(c.session.headers.get("Authorization"))

r = c.session.get(
    f"{c.BASE_URL}/api/v1/account/price",
    params={
        "symbol": "GLD_18C_750TMN",
        "side": "buy"
    }
)

print(r.status_code)
print(r.text)
