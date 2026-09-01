"""WallGold (api.wallgold.ir) adapter.

The only venue here with a real API key, so no session juggling and no SMS.

Confirmed against live orders:

* ``/api/v1/account/price`` takes a ``side`` parameter and returns the same
  number either way, so this is a single reference price whose spread is carried
  by the 0.5% ``otcFeeCoefficient``. It must not claim ``two_sided_quote``.
* Quotes carry a real ``priceExpiresAt`` and a ``ttl`` of roughly 13 seconds,
  not the 30 that was assumed.
* The 0.4 g minimum billable weight applies to **sells only**. Order history
  shows three 0.1 g buys charged exactly 0.5%, a 0.1 g sell billed as 0.4 g, and
  a 0.007 g sell costing 28.57% of notional.
* Locked gold cannot fund a sell leg, so ``get_inventory`` nets it off.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import requests

from adapters.base import AdapterError, GoldAdapter, OrderResult, UncertainExecutionError
from core.models import Quote
from core.platform import MG_PER_GRAM


class WallGoldClient(GoldAdapter):
    name = "wallgold"

    BASE_URL = "https://api.wallgold.ir"
    SYMBOL = "GLD_18C_750TMN"

    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        })

    def login(self) -> None:
        """No-op. The API key is the session."""

    def _unwrap(self, response: requests.Response, what: str) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise AdapterError(
                f"WallGold {what}: non-JSON reply, HTTP {response.status_code}"
            ) from exc

        # The venue reports failure in the body as well as the status, and the
        # body is the more reliable of the two.
        if payload.get("success") is not True:
            raise AdapterError(f"WallGold {what} refused: {payload}")
        return payload["result"]

    def get_quote(self, side: str) -> Quote:
        response = self.session.get(
            f"{self.BASE_URL}/api/v1/account/price",
            params={"symbol": self.SYMBOL, "side": side},
            timeout=(5, 12),
        )
        result = self._unwrap(response, "price")

        return Quote(
            platform=self.name,
            symbol=self.SYMBOL,
            side=side,
            price_tmn_per_gram=Decimal(str(result["price"])),
            timestamp=datetime.fromisoformat(result["currentTime"].replace("Z", "+00:00")),
            expires_at=datetime.fromisoformat(
                result["priceExpiresAt"].replace("Z", "+00:00")
            ),
        )

    def market_rules(self) -> dict:
        """Size limits and the fee coefficient, as the venue states them.

        Worth reading rather than hardcoding: `otcFeeCoefficient`, `minQty` and
        `minNotional` all live here and the venue can change them.
        """
        response = self.session.get(f"{self.BASE_URL}/api/v1/markets", timeout=(5, 15))
        for market in response.json()["result"]:
            if market["symbol"] == self.SYMBOL:
                return market
        raise AdapterError(f"WallGold has no market {self.SYMBOL}")

    def get_inventory(self) -> tuple[Decimal, int]:
        response = self.session.get(
            f"{self.BASE_URL}/api/v1/account/balances", timeout=(5, 15)
        )
        cash = Decimal(0)
        gold_mg = 0
        for entry in self._unwrap(response, "balances"):
            free = Decimal(str(entry["amount"])) - Decimal(str(entry["locked_amount"]))
            if entry["currency"] == "TMN":
                cash = free
            elif entry["currency"] == "GLD_18C_750":
                gold_mg = int(free * MG_PER_GRAM)
        return cash, gold_mg

    def _order(self, side: str, amount_mg: int) -> OrderResult:
        amount_g = Decimal(amount_mg) / MG_PER_GRAM
        try:
            response = self.session.post(
                f"{self.BASE_URL}/api/v1/account/orders",
                json={"symbol": self.SYMBOL, "side": side, "orderAmount": str(amount_g)},
                timeout=(5, 25),
            )
        except requests.RequestException as exc:
            # The order may have reached the venue. Retrying is how one order
            # silently becomes two.
            raise UncertainExecutionError(
                f"WallGold {side} network state is uncertain: {exc!r}"
            ) from exc

        result = self._unwrap(response, f"{side} order")
        return OrderResult(
            platform=self.name,
            order_id=str(result["orderId"]),
            side=side,
            amount_mg=amount_mg,
            filled_price=Decimal(str(result["price"])),
            fee_tmn=Decimal(str(result.get("otcFee", 0))),
            raw=result,
        )

    def buy(self, amount_mg: int) -> OrderResult:
        return self._order("buy", amount_mg)

    def sell(self, amount_mg: int) -> OrderResult:
        return self._order("sell", amount_mg)

    def get_order(self, order_id: str) -> OrderResult:
        response = self.session.get(
            f"{self.BASE_URL}/api/v1/account/orders/{order_id}", timeout=(5, 15)
        )
        result = self._unwrap(response, "order")
        return OrderResult(
            platform=self.name,
            order_id=str(order_id),
            side=str(result.get("side", "")),
            amount_mg=int(Decimal(str(result.get("amount", 0))) * MG_PER_GRAM),
            filled_price=Decimal(str(result.get("price", 0))),
            fee_tmn=Decimal(str(result.get("otcFee", 0))),
            raw=result,
        )



