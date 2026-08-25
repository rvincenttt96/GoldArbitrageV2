from adapters.wallgold.client import WallGoldClient

client = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5e0qXd8zLC5PYE9425d863"
)

print(client.session.headers)

print(client.get_price("buy"))
