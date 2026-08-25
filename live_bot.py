import time
import json
import sys
from datetime import datetime, timezone

# Safe Unicode output on Windows / PowerShell / Tee-Object.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="backslashreplace"
    )

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        errors="backslashreplace"
    )


from core.registry import ExchangeRegistry
from services.scanner import MarketScanner
from services.opportunity_finder import OpportunityFinder
from services.executor import Executor
from services.risk_manager import RiskManager
from config.settings import MAX_TRADE_AMOUNT
from services.telegram import (
    send_market_report,
    send_trade_signal,
    send_trade_result,
)

from adapters.wallgold.client import WallGoldClient
from adapters.goldika.client import GoldikaClient
from adapters.miligold.client import MilliGoldClient

from core.models import Portfolio


wallgold = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"
)


goldika = GoldikaClient(
    "9362798093",
    "Rv6047484"
)

goldika.login()


miligold = MilliGoldClient(
    "+989362798093",
    "Rv6047484",
    "2020182000336301"
)

miligold.login()


registry = ExchangeRegistry()

registry.add(wallgold)
registry.add(goldika)
registry.add(miligold)


scanner = MarketScanner(registry)

finder = OpportunityFinder()


executor = Executor(
    RiskManager()
)



def load_wallgold_portfolio():

    balances = wallgold.get_balance()

    cash = 0
    gold = 0

    for b in balances:

        if b.currency == "TMN":
            cash = b.amount - b.locked_amount

        if b.currency == "GLD_18C_750":
            gold = b.amount - b.locked_amount


    return Portfolio(
        platform="wallgold",
        actual_cash=cash,
        actual_gold=gold,
        allowed_cash=cash,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )



def load_miligold_portfolio():

    gold_data = miligold.get_balance()
    rial_data = miligold.get_rial_balance()

    milli = gold_data["data"]["availableMilliBalance"]
    rial = rial_data["data"]["availableRialBalance"] / 10

    gold = milli / 1000


    return Portfolio(
        platform="miligold",
        actual_cash=rial,
        actual_gold=gold,
        allowed_cash=rial,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )



def load_goldika_portfolio():

    data = goldika.get_balance()

    rial = data["data"]["rial"]["total"]["spendable"]
    gold_milli = data["data"]["gold"]["total"]["spendable"]

    cash = rial / 10
    gold = gold_milli / 1000

    return Portfolio(
        platform="goldika",
        actual_cash=cash,
        actual_gold=gold,
        allowed_cash=cash,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )



last_report_time = 0
last_trade_time = 0
trading_halted = False



while True:

    try:

        wallgold_portfolio = load_wallgold_portfolio()
        miligold_portfolio = load_miligold_portfolio()
        goldika_portfolio = load_goldika_portfolio()

        portfolios = {
            "wallgold": wallgold_portfolio,
            "goldika": goldika_portfolio,
            "miligold": miligold_portfolio
        }
        scan = scanner.scan()



        if time.time() - last_report_time >= 1800:

            last_report_time = time.time()

            try:

                send_market_report(scan)

            except Exception as e:

                print(
                    "TELEGRAM REPORT ERROR:",
                    repr(e)
                )



        opportunity = finder.find(
            scan,
            MAX_TRADE_AMOUNT,
            portfolios
        )


        print(datetime.now(), opportunity)



        if (
            opportunity
            and not trading_halted
            and time.time() - last_trade_time >= 30
        ):
            last_trade_time = time.time()

            print("EXECUTING REAL TRADE")

            try:

                send_trade_signal(
                    opportunity
                )

            except Exception as e:

                print(
                    "TELEGRAM SIGNAL ERROR:",
                    repr(e)
                )


            exchanges = {
                "wallgold": wallgold,
                "goldika": goldika,
                "miligold": miligold
            }


            portfolios = {
                "wallgold": wallgold_portfolio,
                "goldika": goldika_portfolio,
                "miligold": miligold_portfolio
            }



            buy_exchange = exchanges[
                opportunity.buy_platform
            ]


            sell_exchange = exchanges[
                opportunity.sell_platform
            ]



            buy_portfolio = portfolios[
                opportunity.buy_platform
            ]


            sell_portfolio = portfolios[
                opportunity.sell_platform
            ]



            print(
                "BUY PORTFOLIO:",
                buy_portfolio
            )

            print(
                "SELL PORTFOLIO:",
                sell_portfolio
            )



            result = executor.execute(
                opportunity,
                buy_exchange,
                sell_exchange,
                buy_portfolio,
                sell_portfolio
            )


            result_status = result.get("status")

            # Emergency state is updated BEFORE logging.
            if result_status in {
                "partial_execution",
                "execution_uncertain"
            }:
                trading_halted = True
                print(
                    "CRITICAL: EXECUTION UNCERTAIN/PARTIAL "
                    "- TRADING HALTED"
                )

            print(
                json.dumps(
                    result,
                    ensure_ascii=True,
                    default=str
                )
            )
            try:

                send_trade_result(
                    opportunity,
                    result
                )

            except Exception as e:

                print(
                    "TELEGRAM TRADE ERROR:",
                    repr(e)
                )


            if result_status == "completed":

                last_trade_time = time.time()


            elif result.get("status") in {
                "partial_execution",
                "execution_uncertain"
            }:

                trading_halted = True

                print(
                    "CRITICAL: EXECUTION UNCERTAIN/PARTIAL - TRADING HALTED"
                )



    except Exception as e:

        print("ERROR:", e)



    time.sleep(5)
