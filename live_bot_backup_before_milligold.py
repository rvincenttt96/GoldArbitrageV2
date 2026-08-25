import time
from datetime import datetime, timezone

from core.registry import ExchangeRegistry
from services.scanner import MarketScanner
from services.opportunity_finder import OpportunityFinder
from services.executor import Executor
from services.risk_manager import RiskManager
from services.telegram import send_market_report

from adapters.wallgold.client import WallGoldClient
from adapters.goldika.client import GoldikaClient

from core.models import Portfolio

import requests

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


scanner = MarketScanner(registry)
finder = OpportunityFinder()

executor = Executor(
    RiskManager()
)


wallgold_portfolio = Portfolio(
    platform="wallgold",
    actual_cash=10000000,
    actual_gold=0,
    allowed_cash=10000000,
    allowed_gold=0,
    updated_at=datetime.now(timezone.utc)
)


goldika_portfolio = Portfolio(
    platform="goldika",
    actual_cash=10000000,
    actual_gold=0.45,
    allowed_cash=10000000,
    allowed_gold=0.45,
    updated_at=datetime.now(timezone.utc)
)


last_report_time = 0


while True:

    try:

        scan = scanner.scan()

        if time.time() - last_report_time >= 1800:
            send_market_report(scan)
            last_report_time = time.time()


        opportunity = finder.find(
            scan,
            0.5
        )


        print(datetime.now(), opportunity)


        if opportunity:

            print("EXECUTING REAL TRADE")

            result = executor.execute(
                opportunity,
                wallgold if opportunity.buy_platform == "wallgold" else goldika,
                wallgold if opportunity.sell_platform == "wallgold" else goldika,
                wallgold_portfolio,
                goldika_portfolio
            )

            print(result)


    except Exception as e:

        print("ERROR:", e)


    time.sleep(5)








