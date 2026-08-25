from adapters.wallgold.client import WallGoldClient


API_KEY = "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"


client = WallGoldClient(API_KEY)


buy_price = client.get_price("buy")

sell_price = client.get_price("sell")


print("BUY:")
print(buy_price)


print("SELL:")
print(sell_price)
