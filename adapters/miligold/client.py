"""MilliGold (milli.gold) adapter.

Currently disabled in platforms.toml: its quote sits about 2.5% below every
other venue around the clock, which reads as an off-market reference rather than
a price that can be traded at size.

Two things make it worth keeping if that is ever settled:

* Commission is billed in whole milligrams of gold, truncated, with a floor of
  one. Measured against /api/v1/trade/commission: 100 mg costs 1 mg (1.0%),
  500 mg costs 2 mg (0.4%), 1000 mg costs 5 mg (0.5%).
* Ordering is two-phase. `reserve` returns an invoice valid for 30 seconds and
  `confirm` commits it, making this the only venue here that can give a
  cancellable price lock: reserve first, price the other leg, and confirm only
  once the irreversible side has filled.
"""

from __future__ import annotations

import time
from decimal import Decimal

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from adapters.base import (
    AdapterError,
    GoldAdapter,
    OrderResult,
    Reservation,
    UncertainExecutionError,
)
from core.models import Quote, utcnow
from core.platform import MG_PER_GRAM


class MilliGoldClient(GoldAdapter):
    name = "miligold"

    BASE_URL = "https://milli.gold"
    SYMBOL = "GLD_18C_750TMN"
    LOGIN_ATTEMPTS = 3

    #: The venue refuses sells below two milligrams.
    MIN_SELL_MG = 2

    def __init__(self, username: str, password: str, wallet_address: str):
        self.username = username
        self.password = password
        self.wallet_address = wallet_address

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "X-Channel": "MILLI",
            "X-Platform": "PWA",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/app/trade/buy",
        })

        # Retries are mounted for GET only. A retried trade POST is how one
        # order silently becomes two.
        self.session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=2, connect=2, read=2, status=2, backoff_factor=0.75,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}), raise_on_status=False,
        )))

    def _json(self, response: requests.Response, what: str) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise AdapterError(
                f"Milli {what}: non-JSON reply, HTTP {response.status_code}"
            ) from exc
        if not response.ok or payload.get("code") != 0:
            raise AdapterError(f"Milli {what} refused: {payload}")
        return payload

    def login(self) -> None:
        last: Exception | None = None
        for attempt in range(1, self.LOGIN_ATTEMPTS + 1):
            try:
                response = self.session.post(
                    f"{self.BASE_URL}/api/v1/public/user/v2/login",
                    json={"username": self.username, "password": self.password},
                    timeout=(5, 15),
                )
                self._json(response, "login")
                csrf = response.headers.get("x-csrf-token")
                if csrf:
                    self.session.headers["x-csrf-token"] = csrf
                return
            except requests.RequestException as exc:
                last = exc
                if attempt < self.LOGIN_ATTEMPTS:
                    time.sleep(attempt)
        raise AdapterError(
            f"Milli login failed after {self.LOGIN_ATTEMPTS} tries: {last!r}"
        )

    def _raw_price(self) -> int:
        payload = self._json(
            self.session.get(
                f"{self.BASE_URL}/api/v1/public/milli-price/detail", timeout=(5, 12)
            ),
            "price",
        )
        return int(payload["data"]["price18"])

    def get_quote(self, side: str) -> Quote:
        # price18 is rial per milligram, so x100 gives toman per gram. One
        # reference price for both sides; the spread lives in the commission.
        return Quote(
            platform=self.name,
            symbol=self.SYMBOL,
            side=side,
            price_tmn_per_gram=Decimal(self._raw_price() * 100),
            timestamp=utcnow(),
        )

    def commission_mg(self, amount_mg: int, side: str) -> int:
        """What the venue itself says it will charge, in milligrams of gold."""
        payload = self._json(
            self.session.get(
                f"{self.BASE_URL}/api/v1/trade/commission",
                params={
                    "isBuyOrder": "true" if side == "buy" else "false",
                    "amountType": "MILLI",
                    "amount": amount_mg,
                    "milliWalletAddress": self.wallet_address,
                    "milliPrice": self._raw_price(),
                },
                timeout=(5, 15),
            ),
            "commission",
        )
        return int(payload["data"]["calculatedCommission"])

    def get_inventory(self) -> tuple[Decimal, int]:
        gold = self._json(
            self.session.get(
                f"{self.BASE_URL}/api/v1/wallet/milli/{self.wallet_address}"
                "/available-balance",
                timeout=(5, 15),
            ),
            "gold balance",
        )
        rial = self._json(
            self.session.get(
                f"{self.BASE_URL}/api/v1/wallet/rial/available-balance", timeout=(5, 15)
            ),
            "rial balance",
        )
        return (
            Decimal(rial["data"]["availableRialBalance"]) / 10,
            int(gold["data"]["availableMilliBalance"]),
        )

    def reserve(self, side: str, amount_mg: int) -> Reservation:
        """Lock a price for 30 seconds without committing to it."""
        if amount_mg < 1 or (side == "sell" and amount_mg < self.MIN_SELL_MG):
            raise AdapterError(f"Milli {side} of {amount_mg}mg is below the minimum")

        raw_price = self._raw_price()
        commission = self.commission_mg(amount_mg, side)

        try:
            response = self.session.post(
                f"{self.BASE_URL}/api/v1/init-trade-request",
                json={
                    "milliWalletAddress": self.wallet_address,
                    "milliAmount": amount_mg,
                    "milliPrice": raw_price,
                    "calculatedCommission": commission,
                    "orderType": "BUY" if side == "buy" else "SELL",
                },
                timeout=(5, 15),
            )
        except requests.RequestException as exc:
            raise UncertainExecutionError(
                f"Milli reserve network state is uncertain: {exc!r}"
            ) from exc

        payload = self._json(response, "init trade")
        data = payload["data"]
        return Reservation(
            platform=self.name,
            reservation_id=data["invoiceUuid"],
            side=side,
            amount_mg=amount_mg,
            price_tmn_per_gram=Decimal(raw_price * 100),
            fee_tmn=Decimal(commission) * Decimal(raw_price * 100) / MG_PER_GRAM,
            valid_for_seconds=float(data.get("timeValidityInSeconds", 30)),
            raw=payload,
        )

    def confirm(self, reservation: Reservation) -> OrderResult:
        try:
            response = self.session.post(
                f"{self.BASE_URL}/api/v1/confirm-trade-request/"
                f"{reservation.reservation_id}",
                timeout=(5, 15),
            )
        except requests.RequestException as exc:
            raise UncertainExecutionError(
                f"Milli confirm network state is uncertain: {exc!r}"
            ) from exc

        payload = self._json(response, "confirm trade")
        return OrderResult(
            platform=self.name,
            order_id=str(payload["data"].get("invoiceUuid", reservation.reservation_id)),
            side=reservation.side,
            amount_mg=reservation.amount_mg,
            filled_price=reservation.price_tmn_per_gram,
            fee_tmn=reservation.fee_tmn,
            raw=payload,
        )

    def buy(self, amount_mg: int) -> OrderResult:
        return self.confirm(self.reserve("buy", amount_mg))

    def sell(self, amount_mg: int) -> OrderResult:
        return self.confirm(self.reserve("sell", amount_mg))
