"""Talasea (talasea.ir) adapter.

Reverse engineered from the site's bundles and confirmed against the live API.

Three things here cost an SMS code each to establish and are written down so
they are not rediscovered:

* Login takes a password, so no SMS is needed at all. The OTP path exists but
  the password path is what this adapter uses.
* The token goes in ``Authorization`` **without** a ``Bearer`` prefix. With the
  prefix the API answers 401, which reads like a bad token rather than a badly
  framed one.
* The token is bound to the IP that requested it and lasts seven days.

Units: ``/market/getGoldPrice`` reports toman per milligram, so a gram price is
that number times 1000. ``/order/createOrder`` wants ``volume`` in milligrams
and ``price`` as the raw per-milligram figure, unconverted.

Its fee is 1% per side against 0.5% at WallGold and MelliGold, so a round trip
costs 2% and few routes will clear it.
"""

from __future__ import annotations

import base64
import json
import time
from decimal import Decimal
from pathlib import Path

import requests

from adapters.base import AdapterError, GoldAdapter, OrderResult, UncertainExecutionError
from core.models import Quote, utcnow
from core.platform import MG_PER_GRAM

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_SESSION_FILE = Path("~/goldarb/talasea_session.json").expanduser()

#: Tokens last a week. Renewing this far ahead keeps a slow request from being
#: sent with one that dies in flight.
RENEW_MARGIN_SECONDS = 6 * 3600


class TalaseaClient(GoldAdapter):
    name = "talasea"

    BASE_URL = "https://api.talasea.ir/api"
    SITE_URL = "https://talasea.ir"
    SYMBOL = "GLD_18C_750TMN"

    def __init__(
        self,
        mobile: str | None = None,
        password: str | None = None,
        session_file: Path | str | None = None,
    ):
        self.mobile = mobile
        self.password = password
        self.session_file = Path(session_file or DEFAULT_SESSION_FILE).expanduser()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": self.SITE_URL,
            "Referer": f"{self.SITE_URL}/",
        })
        self._token: str | None = None
        self._expires_at: float = 0.0

    # -- session ----------------------------------------------------------

    @staticmethod
    def _expiry(token: str) -> float:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])

    def login(self) -> None:
        """Adopt a stored token, or fetch a new one with the password.

        Safe to call repeatedly: it only hits the network when the stored token
        is missing or close to expiry.
        """
        if not self._token and self.session_file.exists():
            try:
                stored = json.loads(self.session_file.read_text())
                token = stored.get("access_token")
                if token:
                    self._token = token
                    self._expires_at = self._expiry(token)
            except (OSError, ValueError, KeyError, IndexError):
                self._token = None

        if self._token and self._expires_at - time.time() > RENEW_MARGIN_SECONDS:
            return

        if not self.mobile or not self.password:
            raise AdapterError(
                "Talasea token is missing or stale and no password was supplied"
            )

        response = self.session.post(
            f"{self.BASE_URL}/auth/login-password",
            json={"phoneNumber": self.mobile, "password": self.password},
            timeout=(5, 25),
        )
        if not response.ok:
            raise AdapterError(
                f"Talasea login failed: HTTP {response.status_code} "
                f"{response.text[:200]}"
            )

        token = response.json().get("accessToken")
        if not token:
            raise AdapterError(f"Talasea login returned no token: {response.text[:200]}")

        self._token = token
        self._expires_at = self._expiry(token)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps({
            "phone": self.mobile,
            "access_token": token,
            "verified_at": time.time(),
            "method": "password",
        }, indent=2))
        self.session_file.chmod(0o600)

    def _auth(self) -> dict:
        if not self._token or self._expires_at - time.time() <= RENEW_MARGIN_SECONDS:
            self.login()
        # No "Bearer" prefix. Adding one is answered with 401.
        return {"Authorization": self._token}

    # -- transport --------------------------------------------------------

    def _get(self, path: str, authenticated: bool = True, **params):
        response = self.session.get(
            f"{self.BASE_URL}{path}",
            headers=self._auth() if authenticated else {},
            params=params or None,
            timeout=(5, 15),
        )
        if not response.ok:
            raise AdapterError(
                f"Talasea {path}: HTTP {response.status_code} {response.text[:200]}"
            )
        return response.json()

    # -- market data ------------------------------------------------------

    def _market(self) -> dict:
        return self._get("/market/getGoldPrice", authenticated=False)

    def get_quote(self, side: str) -> Quote:
        data = self._market()

        # One reference price for both sides, so refusing a disabled side is the
        # only way a quote can tell us it is not actionable.
        flag = "disableBuy" if side == "buy" else "disableSell"
        if data.get(flag):
            raise AdapterError(
                f"Talasea has {side} disabled: {data.get(flag + 'Message') or 'no reason given'}"
            )

        return Quote(
            platform=self.name,
            symbol=self.SYMBOL,
            side=side,
            price_tmn_per_gram=Decimal(str(data["price"])) * MG_PER_GRAM,
            timestamp=utcnow(),
        )

    def fee_rate(self, notional_tmn: Decimal) -> Decimal:
        """Fee rate for a trade of this size, read from the venue.

        `feeTable` is a tiered schedule keyed on a `min` threshold. It currently
        holds one flat 1% band, but reading it beats hardcoding a number the
        venue can change without telling us.
        """
        data = self._market()
        rate = Decimal(str(data.get("fee", "0.01")))
        for band in sorted(data.get("feeTable", []), key=lambda b: b.get("min", 0)):
            if notional_tmn >= Decimal(str(band.get("min", 0))):
                rate = Decimal(str(band["fee"]))
        return rate

    def get_inventory(self) -> tuple[Decimal, int]:
        """Spendable cash in toman and spendable gold in milligrams.

        Read from /account/getWallet rather than /account/getBalances: the
        latter returns a list mixing staking and loan entries, while this one
        separates free from blocked, which is the distinction that decides
        whether a leg can actually be funded.
        """
        wallet = self._get("/account/getWallet")

        irt = wallet.get("balancesIrt") or {}
        cash = Decimal(str(irt.get("balance", 0))) - Decimal(str(irt.get("blocked", 0)))

        # availableGoldVolume already nets off whatever is staked or pending.
        gold_mg = int(Decimal(str(wallet.get("availableGoldVolume", 0))))

        return max(cash, Decimal(0)), gold_mg

    # -- trading ----------------------------------------------------------

    def _create_order(self, side: str, amount_mg: int) -> OrderResult:
        data = self._market()
        price_per_mg = data["price"]

        body = {"type": side, "volume": amount_mg, "price": price_per_mg}
        if side == "buy":
            body["hasInsurance"] = False

        try:
            response = self.session.post(
                f"{self.BASE_URL}/order/createOrder",
                headers=self._auth(),
                json=body,
                timeout=(5, 25),
            )
        except requests.RequestException as exc:
            # The order may or may not have reached the venue. Retrying here is
            # how one order silently becomes two.
            raise UncertainExecutionError(
                f"Talasea {side} network state is uncertain: {exc!r}"
            ) from exc

        if not response.ok:
            raise AdapterError(
                f"Talasea {side} rejected: HTTP {response.status_code} "
                f"{response.text[:300]}"
            )

        payload = response.json()
        result = payload.get("data", payload)
        order_id = result.get("id") or result.get("orderId") or result.get("_id")
        if not order_id:
            # An unrecognised shape is a failure, not a success. Guessing the
            # other way means selling gold we never bought.
            raise AdapterError(f"Talasea {side} returned no order id: {payload}")

        return OrderResult(
            platform=self.name,
            order_id=str(order_id),
            side=side,
            amount_mg=amount_mg,
            filled_price=Decimal(str(price_per_mg)) * MG_PER_GRAM,
            raw=payload,
        )

    def buy(self, amount_mg: int) -> OrderResult:
        return self._create_order("buy", amount_mg)

    def sell(self, amount_mg: int) -> OrderResult:
        return self._create_order("sell", amount_mg)

    def get_order(self, order_id: str) -> OrderResult:
        payload = self._get("/order/getOrder", id=order_id)
        result = payload.get("data", payload)
        return OrderResult(
            platform=self.name,
            order_id=str(order_id),
            side=str(result.get("type", "")),
            amount_mg=int(result.get("requestVolume") or result.get("volume") or 0),
            filled_price=(
                Decimal(str(result["requestPrice"])) * MG_PER_GRAM
                if result.get("requestPrice") is not None
                else None
            ),
            raw=payload,
        )
