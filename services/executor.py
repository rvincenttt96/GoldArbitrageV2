from datetime import datetime

from config.settings import MIN_NET_PROFIT
from core.models import Opportunity
from services.opportunity_finder import OpportunityFinder


class Executor:

    def __init__(self, risk_manager):
        self.risk_manager = risk_manager
        self.fee_model = OpportunityFinder()


    def _response_ok(self, response):

        if response is None:
            return False

        if not isinstance(response, dict):
            return False

        if "success" in response:
            return response.get("success") is True

        if "code" in response:

            if response.get("code") != 0:
                return False

            data = response.get("data")

            if isinstance(data, dict):

                invoice_status = data.get(
                    "invoiceStatus"
                )

                if invoice_status is not None:

                    return str(
                        invoice_status
                    ).upper() in {
                        "DONE",
                        "FINISHED",
                        "SUCCESS",
                        "COMPLETED"
                    }

            return True

        if "status" in response:

            status = str(
                response.get("status")
            ).lower()

            return status in {
                "success",
                "successful",
                "done",
                "finished",
                "completed",
                "ok"
            }

        if response.get("error"):
            return False

        if response.get("errors"):
            return False

        return True


    def _build_current_opportunity(
        self,
        opportunity,
        current_buy_price,
        current_sell_price
    ):

        amount = opportunity.amount

        buy_fee = self.fee_model.get_buy_fee(
            opportunity.buy_platform,
            amount,
            current_buy_price
        )

        sell_fee = self.fee_model.get_sell_fee(
            opportunity.sell_platform,
            amount,
            current_sell_price
        )

        buy_value = (
            current_buy_price
            *
            amount
        )

        sell_value = (
            current_sell_price
            *
            amount
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
            buy_platform=opportunity.buy_platform,
            sell_platform=opportunity.sell_platform,
            symbol=opportunity.symbol,
            amount=amount,
            buy_price=current_buy_price,
            sell_price=current_sell_price,
            gross_profit=gross_profit,
            buy_fee=buy_fee,
            sell_fee=sell_fee,
            net_profit=net_profit,
            timestamp=datetime.now()
        )


    def execute(
        self,
        opportunity,
        buy_exchange,
        sell_exchange,
        buy_portfolio,
        sell_portfolio
    ):

        approved = self.risk_manager.check(
            opportunity,
            buy_portfolio,
            sell_portfolio
        )

        if not approved:

            return {
                "status": "rejected",
                "reason": "risk_check_failed"
            }


        # Preflight: both exchanges must respond
        # immediately before any real order.
        try:

            current_buy_quote = (
                buy_exchange.get_price("buy")
            )

            current_sell_quote = (
                sell_exchange.get_price("sell")
            )

        except Exception as e:

            return {
                "status": "rejected",
                "reason": "preflight_failed",
                "error": repr(e)
            }


        current_opportunity = (
            self._build_current_opportunity(
                opportunity,
                current_buy_quote.price,
                current_sell_quote.price
            )
        )


        if (
            current_opportunity.net_profit
            <
            MIN_NET_PROFIT
        ):

            return {
                "status": "rejected",
                "reason": "price_moved",
                "current_buy_price":
                    current_opportunity.buy_price,
                "current_sell_price":
                    current_opportunity.sell_price,
                "estimated_net_profit":
                    current_opportunity.net_profit,
                "current_buy_fee":
                    current_opportunity.buy_fee,
                "current_sell_fee":
                    current_opportunity.sell_fee
            }


        # Re-run risk checks using fresh prices
        # and freshly calculated fees.
        current_approved = (
            self.risk_manager.check(
                current_opportunity,
                buy_portfolio,
                sell_portfolio
            )
        )

        if not current_approved:

            return {
                "status": "rejected",
                "reason": "current_risk_check_failed",
                "current_buy_price":
                    current_opportunity.buy_price,
                "current_sell_price":
                    current_opportunity.sell_price,
                "estimated_net_profit":
                    current_opportunity.net_profit
            }


        # BUY LEG
        try:

            buy_order = buy_exchange.buy(
                opportunity.amount
            )

        except Exception as e:

            # A POST timeout/network error is ambiguous.
            # Never automatically retry the trade.
            return {
                "status": "execution_uncertain",
                "stage": "buy",
                "halt_required": True,
                "error": repr(e)
            }


        if not self._response_ok(
            buy_order
        ):

            return {
                "status": "failed",
                "stage": "buy",
                "reason": "buy_not_confirmed",
                "buy_order": buy_order
            }


        # SELL LEG
        try:

            sell_order = sell_exchange.sell(
                opportunity.amount
            )

        except Exception as e:

            return {
                "status": "partial_execution",
                "stage": "sell",
                "halt_required": True,
                "buy_order": buy_order,
                "error": repr(e)
            }


        if not self._response_ok(
            sell_order
        ):

            return {
                "status": "partial_execution",
                "stage": "sell",
                "halt_required": True,
                "buy_order": buy_order,
                "sell_order": sell_order,
                "reason": "sell_not_confirmed"
            }


        return {
            "status": "completed",
            "current_buy_price":
                current_opportunity.buy_price,
            "current_sell_price":
                current_opportunity.sell_price,
            "current_buy_fee":
                current_opportunity.buy_fee,
            "current_sell_fee":
                current_opportunity.sell_fee,
            "estimated_net_profit":
                current_opportunity.net_profit,
            "buy_order": buy_order,
            "sell_order": sell_order
        }
