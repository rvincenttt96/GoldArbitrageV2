from core.registry import ExchangeRegistry
from services.scanner import MarketScanner

from adapters.wallgold.client import WallGoldClient
from adapters.goldika.client import GoldikaClient


wallgold = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"
)

goldika = GoldikaClient(
    "9362798093",
    "Rv6047484"
)

goldika.login()

registry = ExchangeRegistry()
registry.add(wallgold)
registry.add(goldika)

scan = MarketScanner(registry).scan()

for q in scan["quotes"]:
    print(q.platform, q.side, q.price)
