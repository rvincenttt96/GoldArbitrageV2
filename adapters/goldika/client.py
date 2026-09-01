"""Goldika (api.goldika.ir) adapter.

The only venue here that publishes a genuine bid and ask. Its round trip costs
about 4.7% though, so it rarely enters a profitable route.

**Buying is refused by this adapter.** The original code sent grams on the buy
payload and centigrams on the sell payload, and which one the API actually wants
was never established. If the buy side expects centigrams, `buy(500)` would
purchase five milligrams rather than half a gram. Until one small real order
settles it, `buy` raises instead of guessing.
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

    def buy(self, amount_mg: int) -> OrderResult:
        raise AdapterError(
            "Goldika buy is disabled: the amount unit on the buy payload has "
            "never been confirmed. Settle it with one small real order first."
        )

    def sell(self, amount_mg: int) -> OrderResult:
        quote = self.get_quote("sell")

        # The sell payload is denominated in centigrams, which is why Goldika
        # orders move in 10 mg steps.
        centigrams, remainder = divmod(amount_mg, 10)
        if remainder:
            raise AdapterError(f"Goldika sell needs a multiple of 10mg, got {amount_mg}")

        try:
            response = self.session.post(
                f"{self.BASE_URL}/api/v1/exchanges/sell",
                json={
                    "action": "sell",
                    "amount": centigrams,
                    "discount_ids": [],
                    "discountIds": [],
                    "priceId": int(quote.price_id),
                    "total": int(quote.price_tmn_per_gram * amount_mg / MG_PER_GRAM),
                },
                timeout=(5, 25),
            )
        except requests.RequestException as exc:
            raise UncertainExecutionError(
                f"Goldika sell network state is uncertain: {exc!r}"
            ) from exc

        payload = response.json()
        data = payload.get("data")
        order_id = data.get("id") if isinstance(data, dict) else None
        if not response.ok or order_id is None:
            # An unrecognised shape is a failure. Assuming otherwise means
            # believing we sold gold that we still hold.
            raise AdapterError(f"Goldika sell not confirmed: {payload}")

        return OrderResult(
            platform=self.name,
            order_id=str(order_id),
            side="sell",
            amount_mg=amount_mg,
            filled_price=quote.price_tmn_per_gram,
            raw=payload,
        )
