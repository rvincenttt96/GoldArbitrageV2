class Executor:


    def __init__(self, risk_manager):

        self.risk_manager = risk_manager



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


        buy_order = buy_exchange.buy(
            opportunity.amount
        )


        sell_order = sell_exchange.sell(
            opportunity.amount
        )


        return {
            "status": "completed",
            "buy_order": buy_order,
            "sell_order": sell_order
        }
