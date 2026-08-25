from adapters.wallgold.client import WallGoldClient


client = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"
)


order = client.sell(0.007)

print(order)
