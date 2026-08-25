from pathlib import Path


# =========================================================
# 1) Rewrite OpportunityFinder
# =========================================================

finder = r'''from datetime import datetime

from core.models import Opportunity

from config.settings import (
    MILLIGOLD_BUY_FEE,
    MILLIGOLD_SELL_FEE,
    WALLGOLD_BUY_FEE,
    WALLGOLD_SELL_FEE,
    GOLDIKA_BUY_FEE,
    GOLDIKA_SELL_FEE,
    GOLDIKA_BUY_ENABLED,
    MIN_NET_PROFIT,
    MIN_TRADE_AMOUNT,
    MAX_TRADE_AMOUNT,
)


class OpportunityFinder:

    def get_buy_fee(
        self,
        platform,
        amount,
        price
    ):

        value = amount * price

        if platform == "miligold":

            milli_amount = int(
                round(amount * 1000)
            )

            commission_milli = int(
                milli_amount
                *
                MILLIGOLD_BUY_FEE
            )

            return (
                commission_milli
                /
                1000
                *
                price
            )

        if platform == "wallgold":
            return value * WALLGOLD_BUY_FEE

        if platform == "goldika":
            return value * GOLDIKA_BUY_FEE

        raise Exception(
            f"Unknown buy fee platform: {platform}"
        )


    def get_sell_fee(
        self,
        platform,
        amount,
        price
    ):

        value = amount * price

        if platform == "miligold":

            milli_amount = int(
                round(amount * 1000)
            )

            commission_milli = int(
                milli_amount
                *
                MILLIGOLD_SELL_FEE
            )

            return (
                commission_milli
                /
                1000
                *
                price
            )

        if platform == "wallgold":

            billable_amount = max(
                amount,
                0.4
            )

            return (
                billable_amount
                *
                price
                *
                WALLGOLD_SELL_FEE
            )

        if platform == "goldika":
            return value * GOLDIKA_SELL_FEE

        raise Exception(
            f"Unknown sell fee platform: {platform}"
        )


    def _build_opportunity(
        self,
        buy_quote,
        sell_quote,
        amount
    ):

        buy_value = (
            buy_quote.price
            *
            amount
        )

        sell_value = (
            sell_quote.price
            *
            amount
        )

        buy_fee = self.get_buy_fee(
            buy_quote.platform,
            amount,
            buy_quote.price
        )

        sell_fee = self.get_sell_fee(
            sell_quote.platform,
            amount,
            sell_quote.price
        )

        gross_profit = (
            sell_value
            -
            buy_value
        )

        net_profit = (
            sell_value
            -
            sell_fee
            -
            buy_value
            -
            buy_fee
        )

        return Opportunity(
            buy_platform=buy_quote.platform,
            sell_platform=sell_quote.platform,
            symbol=buy_quote.symbol,
            amount=amount,
            buy_price=buy_quote.price,
            sell_price=sell_quote.price,
            gross_profit=gross_profit,
            buy_fee=buy_fee,
            sell_fee=sell_fee,
            net_profit=net_profit,
            timestamp=datetime.now()
        )


    def _candidate_amounts(
        self,
        buy_platform,
        sell_platform,
        maximum
    ):

        # Goldika sell payload works on 0.01g units.
        # Use the same conservative granularity whenever
        # Goldika participates in the route.
        if (
            buy_platform == "goldika"
            or
            sell_platform == "goldika"
        ):
            step_milli = 10
        else:
            step_milli = 1

        min_milli = int(
            round(
                MIN_TRADE_AMOUNT
                *
                1000
            )
        )

        max_milli = int(
            maximum
            *
            1000
            +
            1e-9
        )

        # Align maximum to exchange granularity.
        max_milli = (
            max_milli
            //
            step_milli
            *
            step_milli
        )

        if max_milli < min_milli:
            return

        for milli in range(
            max_milli,
            min_milli - 1,
            -step_milli
        ):
            yield milli / 1000


    def _inventory_ok(
        self,
        opportunity,
        portfolios
    ):

        buy_portfolio = portfolios.get(
            opportunity.buy_platform
        )

        sell_portfolio = portfolios.get(
            opportunity.sell_platform
        )

        if buy_portfolio is None:
            return False

        if sell_portfolio is None:
            return False

        required_cash = (
            opportunity.buy_price
            *
            opportunity.amount
            +
            opportunity.buy_fee
        )

        available_cash = (
            buy_portfolio.available_cash()
        )

        available_gold = (
            sell_portfolio.available_gold()
        )

        if (
            available_cash
            +
            1e-9
            <
            required_cash
        ):
            return False

        if (
            available_gold
            +
            1e-9
            <
            opportunity.amount
        ):
            return False

        return True


    def find(
        self,
        scan_result,
        amount=MAX_TRADE_AMOUNT,
        portfolios=None
    ):

        requested_amount = min(
            float(amount),
            MAX_TRADE_AMOUNT
        )

        if (
            requested_amount
            <
            MIN_TRADE_AMOUNT
        ):
            return None

        quotes = scan_result["quotes"]

        buy_quotes = []
        sell_quotes = []

        for quote in quotes:

            if quote.side == "buy":

                if (
                    quote.platform == "goldika"
                    and
                    not GOLDIKA_BUY_ENABLED
                ):
                    continue

                buy_quotes.append(
                    quote
                )

            elif quote.side == "sell":

                sell_quotes.append(
                    quote
                )

        if (
            not buy_quotes
            or
            not sell_quotes
        ):
            return None

        opportunities = []

        for buy_quote in buy_quotes:

            for sell_quote in sell_quotes:

                if (
                    buy_quote.platform
                    ==
                    sell_quote.platform
                ):
                    continue

                maximum = requested_amount

                if portfolios is not None:

                    buy_portfolio = portfolios.get(
                        buy_quote.platform
                    )

                    sell_portfolio = portfolios.get(
                        sell_quote.platform
                    )

                    if (
                        buy_portfolio is None
                        or
                        sell_portfolio is None
                    ):
                        continue

                    # Hard upper bound from seller inventory.
                    maximum = min(
                        maximum,
                        sell_portfolio.available_gold()
                    )

                    # Rough cash bound before exact fee calculation.
                    if buy_quote.price <= 0:
                        continue

                    maximum = min(
                        maximum,
                        buy_portfolio.available_cash()
                        /
                        buy_quote.price
                    )

                for candidate_amount in (
                    self._candidate_amounts(
                        buy_quote.platform,
                        sell_quote.platform,
                        maximum
                    )
                ):

                    opportunity = (
                        self._build_opportunity(
                            buy_quote,
                            sell_quote,
                            candidate_amount
                        )
                    )

                    # Do not call something an arbitrage opportunity
                    # unless it meets our minimum net-profit rule.
                    if (
                        opportunity.net_profit
                        <
                        MIN_NET_PROFIT
                    ):
                        continue

                    if (
                        portfolios is not None
                        and
                        not self._inventory_ok(
                            opportunity,
                            portfolios
                        )
                    ):
                        continue

                    opportunities.append(
                        opportunity
                    )

        if not opportunities:
            return None

        return max(
            opportunities,
            key=lambda x: x.net_profit
        )
'''

Path(
    "./services/opportunity_finder.py"
).write_text(
    finder,
    encoding="utf-8"
)


# =========================================================
# 2) Rewrite RiskManager
# =========================================================

risk = r'''from config.settings import (
    MIN_NET_PROFIT,
    MAX_TRADE_AMOUNT,
    MIN_TRADE_AMOUNT
)


class RiskManager:

    def check(
        self,
        opportunity,
        buy_portfolio,
        sell_portfolio
    ):

        if opportunity is None:
            return False

        if (
            opportunity.net_profit
            <
            MIN_NET_PROFIT
        ):
            return False

        if (
            opportunity.amount
            <
            MIN_TRADE_AMOUNT
        ):
            return False

        if (
            opportunity.amount
            >
            MAX_TRADE_AMOUNT
        ):
            return False

        # Cash requirement must include the buy fee.
        required_cash = (
            opportunity.buy_price
            *
            opportunity.amount
            +
            opportunity.buy_fee
        )

        if (
            buy_portfolio.available_cash()
            +
            1e-9
            <
            required_cash
        ):
            return False

        if (
            sell_portfolio.available_gold()
            +
            1e-9
            <
            opportunity.amount
        ):
            return False

        return True
'''

Path(
    "./services/risk_manager.py"
).write_text(
    risk,
    encoding="utf-8"
)


# =========================================================
# 3) Patch live_bot.py
# =========================================================

p = Path("./live_bot.py")
s = p.read_text(
    encoding="utf-8-sig"
)

# Add MAX_TRADE_AMOUNT import if absent.
if (
    "from config.settings import MAX_TRADE_AMOUNT"
    not in s
):
    marker = (
        "from services.risk_manager "
        "import RiskManager\n"
    )

    if marker not in s:
        raise Exception(
            "RiskManager import marker not found"
        )

    s = s.replace(
        marker,
        marker
        +
        "from config.settings "
        "import MAX_TRADE_AMOUNT\n",
        1
    )


old = '''        goldika_portfolio = load_goldika_portfolio()
        scan = scanner.scan()
'''

new = '''        goldika_portfolio = load_goldika_portfolio()

        portfolios = {
            "wallgold": wallgold_portfolio,
            "goldika": goldika_portfolio,
            "miligold": miligold_portfolio
        }

        scan = scanner.scan()
'''

if old not in s:
    raise Exception(
        "Portfolio/scan block not found"
    )

s = s.replace(
    old,
    new,
    1
)


old = '''        opportunity = finder.find(scan, 0.5)
'''

new = '''        opportunity = finder.find(
            scan,
            MAX_TRADE_AMOUNT,
            portfolios
        )
'''

if old not in s:
    raise Exception(
        "finder.find call not found"
    )

s = s.replace(
    old,
    new,
    1
)

p.write_text(
    s,
    encoding="utf-8"
)

print(
    "INVENTORY-AWARE OPPORTUNITY FINDER APPLIED"
)
print(
    "RISK MANAGER NOW INCLUDES BUY FEE"
)
print(
    "LIVE BOT NOW PASSES LIVE PORTFOLIOS TO FINDER"
)
