from adapters.wallgold.client import WallGoldClient
from core.registry import ExchangeRegistry
from services.scanner import MarketScanner


API_KEY = "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"


wallgold = WallGoldClient(API_KEY)


registry = ExchangeRegistry()

registry.add(wallgold)


scanner = MarketScanner(registry)


result = scanner.scan()


print("SCAN TIME:")
print(result["timestamp"])


print()
print("QUOTES:")

for q in result["quotes"]:
    print(q)
