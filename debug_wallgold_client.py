from adapters.wallgold.client import WallGoldClient

c = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5e0qXd8zLC5PYE9425d863"
)

print(c.session.headers)

print(c.get_price("buy"))
