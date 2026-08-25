import time
import requests

from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.models import Quote


class MilliGoldClient:

    BASE_URL = "https://milli.gold"

    CONNECT_TIMEOUT = 5
    READ_TIMEOUT = 15
    LOGIN_ATTEMPTS = 3


    def __init__(
        self,
        username,
        password,
        wallet_address
    ):

        self.username = username
        self.password = password
        self.wallet_address = wallet_address

        self.session = requests.Session()

        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "X-Channel": "MILLI",
            "X-Platform": "PWA",
            "X-Client-Version": "1.0.0",
            "X-Release-Version": "827b1711",
            "Origin": "https://milli.gold",
            "Referer": "https://milli.gold/app/trade/buy"
        })

        # Retry ONLY safe GET requests.
        # Trade POST requests are never automatically retried.
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.75,
            status_forcelist=(
                429,
                500,
                502,
                503,
                504
            ),
            allowed_methods=frozenset({
                "GET"
            }),
            raise_on_status=False
        )

        adapter = HTTPAdapter(
            max_retries=retry
        )

        self.session.mount(
            "https://",
            adapter
        )


    def _timeout(self):

        return (
            self.CONNECT_TIMEOUT,
            self.READ_TIMEOUT
        )


    def _json_response(
        self,
        response,
        label
    ):

        try:
            data = response.json()

        except Exception:

            raise Exception(
                f"{label} invalid JSON: "
                f"HTTP {response.status_code} "
                f"{response.text[:500]}"
            )


        if not response.ok:

            raise Exception(
                f"{label} HTTP error: "
                f"{response.status_code} "
                f"{data}"
            )


        return data


    def login(self):

        last_error = None

        for attempt in range(
            1,
            self.LOGIN_ATTEMPTS + 1
        ):

            try:

                r = self.session.post(
                    f"{self.BASE_URL}/api/v1/public/user/v2/login",
                    json={
                        "username": self.username,
                        "password": self.password
                    },
                    timeout=self._timeout()
                )

                data = self._json_response(
                    r,
                    "Milli login"
                )

                csrf = r.headers.get(
                    "x-csrf-token"
                )

                if csrf:

                    self.session.headers.update({
                        "x-csrf-token": csrf
                    })


                if data.get("code") != 0:

                    raise Exception(
                        f"Milli login failed: {data}"
                    )


                return data


            except requests.RequestException as e:

                last_error = e

                if attempt < self.LOGIN_ATTEMPTS:

                    time.sleep(attempt)


        raise Exception(
            f"Milli login network failure "
            f"after {self.LOGIN_ATTEMPTS} attempts: "
            f"{repr(last_error)}"
        )


    def _get_raw_price(self):

        r = self.session.get(
            f"{self.BASE_URL}/api/v1/public/milli-price/detail",
            timeout=self._timeout()
        )

        data = self._json_response(
            r,
            "Milli price"
        )

        if (
            data.get("code") != 0
            or
            "data" not in data
        ):
            raise Exception(
                f"Milli price failed: {data}"
            )


        return int(
            data["data"]["price18"]
        )


    def get_price(
        self,
        side="buy"
    ):

        raw_price = self._get_raw_price()

        price_per_gram_tmn = (
            raw_price * 100
        )


        return Quote(
            platform="miligold",
            symbol="GLD_18C_750TMN",
            side=side.lower(),
            price=price_per_gram_tmn,
            price_id=0,
            expires_at=datetime.now(),
            ttl=0,
            timestamp=datetime.now()
        )


    def get_balance(self):

        r = self.session.get(
            f"{self.BASE_URL}/api/v1/wallet/milli/{self.wallet_address}/available-balance",
            timeout=self._timeout()
        )

        data = self._json_response(
            r,
            "Milli gold balance"
        )

        if (
            data.get("code") != 0
            or
            "data" not in data
        ):
            raise Exception(
                f"Milli gold balance failed: {data}"
            )


        return data


    def get_rial_balance(self):

        r = self.session.get(
            f"{self.BASE_URL}/api/v1/wallet/rial/available-balance",
            timeout=self._timeout()
        )

        data = self._json_response(
            r,
            "Milli rial balance"
        )

        if (
            data.get("code") != 0
            or
            "data" not in data
        ):
            raise Exception(
                f"Milli rial balance failed: {data}"
            )


        return data


    def get_commission(
        self,
        milli_amount,
        raw_price,
        order_type
    ):

        r = self.session.get(
            f"{self.BASE_URL}/api/v1/trade/commission",
            params={
                "isBuyOrder": (
                    "true"
                    if order_type == "BUY"
                    else "false"
                ),
                "amountType": "MILLI",
                "amount": milli_amount,
                "milliWalletAddress": self.wallet_address,
                "milliPrice": raw_price
            },
            timeout=self._timeout()
        )

        data = self._json_response(
            r,
            "Milli commission"
        )

        if (
            data.get("code") != 0
            or
            "data" not in data
        ):
            raise Exception(
                f"Milli commission failed: {data}"
            )


        return data["data"][
            "calculatedCommission"
        ]


    def init_trade_request(
        self,
        amount,
        order_type
    ):

        amount_grams = float(
            amount
        )

        milli_amount = int(
            round(
                amount_grams * 1000
            )
        )


        if milli_amount < 1:

            raise Exception(
                f"Milli amount too small: "
                f"{milli_amount}"
            )


        if (
            order_type == "SELL"
            and
            milli_amount < 2
        ):

            raise Exception(
                f"Milli SELL amount too small: "
                f"{milli_amount}"
            )


        raw_price = self._get_raw_price()

        commission = self.get_commission(
            milli_amount,
            raw_price,
            order_type
        )


        # IMPORTANT:
        # No automatic retry for this POST.
        try:

            r = self.session.post(
                f"{self.BASE_URL}/api/v1/init-trade-request",
                json={
                    "milliWalletAddress": self.wallet_address,
                    "milliAmount": milli_amount,
                    "milliPrice": raw_price,
                    "calculatedCommission": commission,
                    "orderType": order_type
                },
                timeout=self._timeout()
            )

        except requests.RequestException as e:

            raise RuntimeError(
                "Milli init trade network state "
                "is uncertain: "
                f"{repr(e)}"
            )


        data = self._json_response(
            r,
            "Milli init trade"
        )


        if (
            data.get("code") != 0
            or
            "data" not in data
        ):

            raise Exception(
                f"Milli init trade failed: {data}"
            )


        return data


    def confirm_trade(
        self,
        invoice_uuid
    ):

        # IMPORTANT:
        # No automatic retry for this POST.
        try:

            r = self.session.post(
                f"{self.BASE_URL}/api/v1/confirm-trade-request/{invoice_uuid}",
                timeout=self._timeout()
            )

        except requests.RequestException as e:

            raise RuntimeError(
                "Milli confirm trade network state "
                "is uncertain: "
                f"{repr(e)}"
            )


        data = self._json_response(
            r,
            "Milli confirm trade"
        )


        if (
            data.get("code") != 0
            or
            "data" not in data
        ):

            raise Exception(
                f"Milli confirm trade failed: {data}"
            )


        return data


    def buy(
        self,
        amount
    ):

        invoice = self.init_trade_request(
            amount,
            "BUY"
        )

        return self.confirm_trade(
            invoice["data"]["invoiceUuid"]
        )


    def sell(
        self,
        amount
    ):

        invoice = self.init_trade_request(
            amount,
            "SELL"
        )

        return self.confirm_trade(
            invoice["data"]["invoiceUuid"]
        )
