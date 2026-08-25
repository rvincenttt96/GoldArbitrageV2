from adapters.wallgold.client import WallGoldClient


API_KEY = "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"


client = WallGoldClient(API_KEY)


quote = client.get_price("buy")


print(quote)

print()
print("PRICE:", quote.price)
print("TTL:", quote.ttl)
print("EXPIRES:", quote.expires_at)
