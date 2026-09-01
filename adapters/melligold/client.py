"""MelliGold (melligold.com) adapter.

Prices and balances work. Order placement is still unwired.

What the live API established:

* ``GET /api/v1/exchange/buy-sell-price/?symbol=XAU18`` is public and needs no
  session at all, so prices can be recorded without ever logging in.
* ``price_buy`` and ``price_sell`` come back identical. Like MilliGold, WallGold
  and Talasea, this venue publishes one reference price and carries its spread
  in the commission, so it must not claim ``two_sided_quote``.
* Login is two-step and sends an SMS code, but ``/authentication/refresh/``
  returns a *new* refresh token each time with a fresh seven-day window. A
  process that refreshes more often than weekly therefore needs the SMS step
  exactly once. See ``scripts/melligold_login.py``.
* The site sits behind ArvanCloud, which bounces a cold client with a 307 cookie
  challenge. Loading the app page once banks the cookie.

Still unknown: the exact commission. ``/api/v1/exchange/price-calculator/``
answers 500 to every parameter combination tried so far, so the 0.5% in
``platforms.toml`` remains a published figure rather than a measured one, and
the venue stays ``verified = false`` until an invoice confirms it.
"""

from __future__ import annotations

import base64
import json
import time
from decimal import Decimal
from pathlib import Path

import requests

from adapters.base import AdapterError, GoldAdapter, OrderResult
from core.models import Quote, utcnow
from core.platform import MG_PER_GRAM

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_SESSION_FILE = Path("~/goldarb/melligold_session.json").expanduser()

#: Access tokens live two hours. Refreshing this far ahead of expiry keeps a
#: slow request from being sent with a token that dies in flight.
REFRESH_MARGIN_SECONDS = 600


class MelliGoldClient(GoldAdapter):
    name = "melligold"

    BASE_URL = "https://melligold.com"
    SYMBOL = "XAU18"

    def __init__(self, session_file: Path | str | None = None):
        self.session_file = Path(session_file or DEFAULT_SESSION_FILE).expanduser()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self._state: dict = {}
        self._access_expires_at: float = 0.0
        self._challenge_cleared = False

    # -- session ----------------------------------------------------------

    def _clear_challenge(self) -> None:
        if self._challenge_cleared:
            return
        self.session.get(f"{self.BASE_URL}/pwa/account", timeout=(5, 20))
        self._challenge_cleared = True

    def _load_state(self) -> dict:
        if not self.session_file.exists():
            raise AdapterError(
                f"no MelliGold session at {self.session_file}; "
                "run scripts/melligold_login.py --request then --verify"
            )
        return json.loads(self.session_file.read_text())

    def _save_state(self) -> None:
        self.session_file.write_text(json.dumps(self._state, indent=2))
        self.session_file.chmod(0o600)

    @staticmethod
    def _token_expiry(token: str) -> float:
        """Read `exp` out of a JWT without verifying it.

        We are not authenticating the token, only deciding when to renew it, so
        the signature is the server's business rather than ours.
        """
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])

    def login(self) -> None:
        """Adopt the stored session, renewing the access token if it is stale.

        Never triggers an SMS. Obtaining a code is a human step and belongs in
        the login script; doing it here would let a restart loop spray codes at
        the account and get it locked.
        """
        self._clear_challenge()
        self._state = self._load_state()

        if not self._state.get("refresh"):
            raise AdapterError("stored MelliGold session has no refresh token")

        for name, value in self._state.get("cookies", {}).items():
            self.session.cookies.set(name, value)

        access = self._state.get("access")
        if access:
            self._access_expires_at = self._token_expiry(access)
        if not access or self._access_expires_at - time.time() < REFRESH_MARGIN_SECONDS:
            self._refresh()

    def _refresh(self) -> None:
        response = self.session.post(
            f"{self.BASE_URL}/api/v1/authentication/refresh/",
            json={"refresh": self._state["refresh"]},
            headers=self._headers(authenticated=False),
            timeout=(5, 20),
        )
        if not response.ok:
            raise AdapterError(
                f"MelliGold refresh failed: HTTP {response.status_code} "
                f"{response.text[:200]}"
            )
        data = response.json().get("data", {})
        if not data.get("access"):
            raise AdapterError(f"MelliGold refresh returned no access token: {data}")

        self._state["access"] = data["access"]
        # The endpoint rotates the refresh token as well, and the replacement
        # carries a new seven-day window. Storing it is what keeps the SMS step
        # from ever coming round again.
        self._state["refresh"] = data.get("refresh", self._state["refresh"])
        self._state["cookies"] = self.session.cookies.get_dict()
        self._access_expires_at = self._token_expiry(self._state["access"])
        self._save_state()

    def _headers(self, authenticated: bool = True) -> dict:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/pwa/account",
        }
        if authenticated:
            if self._access_expires_at - time.time() < REFRESH_MARGIN_SECONDS:
                self._refresh()
            headers["Authorization"] = f"Bearer {self._state['access']}"
        return headers

    def _get(self, path: str, **params) -> dict:
        self._clear_challenge()
        response = self.session.get(
            f"{self.BASE_URL}{path}",
            headers=self._headers(),
            params=params or None,
            timeout=(5, 20),
        )
        if not response.ok:
            raise AdapterError(
                f"MelliGold {path}: HTTP {response.status_code} {response.text[:200]}"
            )
        return response.json()

    # -- market data ------------------------------------------------------

    def get_quote(self, side: str) -> Quote:
        """Current price. Public, so this works with no session at all."""
        self._clear_challenge()
        response = self.session.get(
            f"{self.BASE_URL}/api/v1/exchange/buy-sell-price/",
            params={"symbol": self.SYMBOL},
            headers={
                "Accept": "application/json",
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/pwa/account",
            },
            timeout=(5, 12),
        )
        if not response.ok:
            raise AdapterError(
                f"MelliGold price: HTTP {response.status_code} {response.text[:200]}"
            )

        data = response.json()["data"]
        key = "price_buy" if side == "buy" else "price_sell"
        return Quote(
            platform=self.name,
            symbol=self.SYMBOL,
            side=side,
            price_tmn_per_gram=Decimal(str(data[key])),
            timestamp=utcnow(),
        )

    def minimum_order_mg(self, side: str) -> int:
        """Smallest tradable size, read from the venue rather than assumed.

        The price response carries `lower_amounts`, and buy and sell floors
        differ: one milligram to buy, ten to sell.
        """
        data = self._get("/api/v1/exchange/buy-sell-price/", symbol=self.SYMBOL)["data"]
        key = "buy_gold" if side == "buy" else "sell_gold"
        return round(float(data["lower_amounts"][key]) * MG_PER_GRAM)

    def get_inventory(self) -> tuple[Decimal, int]:
        balances = self._get("/api/v1/wallet/balance/")["data"]
        cash = Decimal(0)
        gold_mg = 0
        for entry in balances:
            amount = Decimal(str(entry["balance"]))
            if entry["wallet_type"] == "IRT":
                cash = amount
            elif entry["wallet_type"] == self.SYMBOL:
                gold_mg = int(amount * MG_PER_GRAM)
        return cash, gold_mg

    # -- trading ----------------------------------------------------------

    def buy(self, amount_mg: int) -> OrderResult:
        raise NotImplementedError(
            "MelliGold order placement is not wired up: /api/v1/currency/buy/ "
            "has not been observed against a funded account."
        )

    def sell(self, amount_mg: int) -> OrderResult:
        raise NotImplementedError(
            "MelliGold order placement is not wired up: /api/v1/currency/sell/ "
            "has not been observed against a funded account."
        )
