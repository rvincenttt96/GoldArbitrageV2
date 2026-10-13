"""Goldika (api.goldika.ir) adapter.

The only venue here that publishes a genuine bid and ask. Its round trip costs
about 4.7% though, so it rarely enters a profitable route.

Two things were settled on 2026-09-01 with real orders, and the original code had
both wrong:

* **Both sides take whole milligrams.** Order 1829431 sent ``amount: 5`` and
  received 5 mg. The old code sent grams on buy and centigrams on sell, so a
  half-gram buy would have asked for 0.5 mg and a half-gram sell for 50 mg.
  Fractional amounts are refused outright with "مقدار طلا معتبر نیست".
* **There is no commission.** Buying 5 mg cost 1,110,762 rial against a quote of
  222,152,564 rial/gram, and selling 5 mg returned 1,084,420 against 216,884,124
  - both exact to the rial. The 1.2% the old config charged was double-counting;
  the whole cost is the 2.37% spread that the two-sided quote already shows.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import requests

from adapters.base import AdapterError, GoldAdapter, OrderResult, UncertainExecutionError
from core.models import Quote
from core.platform import MG_PER_GRAM


class GoldikaClient(GoldAdapter):
    name = "goldika"

    BASE_URL = "https://api.goldika.ir"
    SYMBOL = "GLD_18C_750TMN"

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-PLATFORM": "web",
            "X-VERSION": "2.4.13",
            "Origin": "https://goldika.ir",
            "Referer": "https://goldika.ir/",
        })

    def login(self) -> None:
        response = self.session.post(
            f"{self.BASE_URL}/api/auth/user/login/password",
            json={"username": self.username, "password": self.password},
            timeout=(5, 20),
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AdapterError(
                f"Goldika login: non-JSON reply, HTTP {response.status_code}"
            ) from exc

        if "token" not in payload:
            # Deliberately does not echo the body: the original code printed the
            # whole login response, which carries the credentials back.
            raise AdapterError(
                f"Goldika login failed, HTTP {response.status_code}, "
                f"status {payload.get('status')!r}"
            )
        self.session.headers["Authorization"] = "Bearer " + payload["token"]

    def get_quote(self, side: str) -> Quote:
        response = self.session.get(f"{self.BASE_URL}/api/public/price", timeout=(5, 12))
        price = response.json()["data"]["price"]

        # Quoted in rial. `buy` is the ask, `sell` the bid.
        raw = price["buy"] if side == "buy" else price["sell"]
        return Quote(
            platform=self.name,
            symbol=self.SYMBOL,
            side=side,
            price_tmn_per_gram=Decimal(raw) / 10,
            price_id=str(price["id"]),
            timestamp=datetime.fromisoformat(price["createdAt"].replace("Z", "+00:00")),
        )

    def get_inventory(self) -> tuple[Decimal, int]:
        response = self.session.get(
            f"{self.BASE_URL}/api/v1/balances/get", timeout=(5, 15)
        )
        payload = response.json()
        if not response.ok or "data" not in payload:
            raise AdapterError(f"Goldika balance refused: HTTP {response.status_code}")

        data = payload["data"]
        return (
            Decimal(data["rial"]["total"]["spendable"]) / 10,
            int(data["gold"]["total"]["spendable"]),
        )

    def _order(self, side: str, amount_mg: int) -> OrderResult:
        quote = self.get_quote(side)

        body = {
            "action": side,
            # Whole milligrams on both sides. A fraction is refused.
            "amount": int(amount_mg),
            "discount_ids": [],
            "discountIds": [],
            "priceId": int(quote.price_id),
        }
        if side == "sell":
            body["total"] = int(quote.price_tmn_per_gram * amount_mg / MG_PER_GRAM)

        try:
            response = self.session.post(
                f"{self.BASE_URL}/api/v1/exchanges/{side}", json=body, timeout=(5, 25)
            )
        except requests.RequestException as exc:
            raise UncertainExecutionError(
                f"Goldika {side} network state is uncertain: {exc!r}"
            ) from exc

        payload = response.json()
        data = payload.get("data")
        order_id = data.get("id") if isinstance(data, dict) else None
        if not response.ok or order_id is None:
            # An unrecognised shape is a failure. Assuming otherwise means
            # believing we traded when we did not.
            raise AdapterError(f"Goldika {side} not confirmed: {payload}")

        # up_amount is the gold leg on a buy and the rial leg on a sell, so the
        # filled weight is read from whichever side carries egold.
        filled_mg = amount_mg
        if data.get("up_unit") == "egold":
            filled_mg = int(data["up_amount"])
        elif data.get("down_unit") == "egold":
            filled_mg = abs(int(data["down_amount"]))

        return OrderResult(
            platform=self.name,
            order_id=str(order_id),
            side=side,
            amount_mg=filled_mg,
            filled_price=Decimal(str(data.get("named_price", 0))) / 10 or None,
            raw=payload,
        )

    def buy(self, amount_mg: int) -> OrderResult:
        return self._order("buy", amount_mg)

    def sell(self, amount_mg: int) -> OrderResult:
        return self._order("sell", amount_mg)
