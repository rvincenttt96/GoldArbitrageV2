from adapters.wallgold.client import WallGoldClient


API_KEY = "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"


client = WallGoldClient(API_KEY)


balances = client.get_balance()


for b in balances:
    print(b)
