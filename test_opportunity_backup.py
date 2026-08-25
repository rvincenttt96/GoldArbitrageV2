from core.registry import ExchangeRegistry
from services.scanner import MarketScanner
from services.opportunity_finder import OpportunityFinder

from adapters.wallgold.client import WallGoldClient
from adapters.goldika.client import GoldikaClient


wallgold = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5e0qXd8zLC5PYE9425d863"
)


goldika = GoldikaClient(
    "9362798093",
    "Rv6047484"
)

goldika.login()


registry = ExchangeRegistry()

registry.add(wallgold)
registry.add(goldika)


scanner = MarketScanner(registry)

scan = scanner.scan()


finder = OpportunityFinder()

result = finder.find(
    scan,
    0.5
)


print(result)
