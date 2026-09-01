#!/usr/bin/env python3
"""Writes live balances to a JSON file for the paper loop to read.

Kept separate from the scan loop on purpose. Balance calls need authenticated
sessions that expire, and one venue being logged out must not stall a loop whose
job is to watch prices. This runs on its own schedule and writes a file; the
loop reads whatever is there and carries on if it is missing.

    python3 -m scripts.fetch_balances --out ~/goldarb/balances.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

import requests

from adapters.melligold.client import MelliGoldClient

log = logging.getLogger("balances")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
OUT = Path("~/goldarb/balances.json").expanduser()


def wallgold() -> tuple[Decimal, int]:
    key = os.environ["WALLGOLD_API_KEY"]
    response = requests.get(
        "https://api.wallgold.ir/api/v1/account/balances",
        headers={"Accept": "application/json", "Authorization": f"Bearer {key}"},
        timeout=(5, 20),
    )
    response.raise_for_status()

    cash, gold_mg = Decimal(0), 0
    for entry in response.json()["result"]:
        free = Decimal(str(entry["amount"])) - Decimal(str(entry["locked_amount"]))
        if entry["currency"] == "TMN":
            cash = free
        elif entry["currency"] == "GLD_18C_750":
            # Locked gold is excluded: it cannot fund a sell leg, and counting it
            # would produce signals we could not act on.
            gold_mg = int(free * 1000)
    return cash, gold_mg


def miligold() -> tuple[Decimal, int]:
    base = "https://milli.gold"
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "X-Channel": "MILLI", "X-Platform": "PWA",
        "Origin": base, "Referer": f"{base}/app/trade/buy",
    })
    response = session.post(
        f"{base}/api/v1/public/user/v2/login",
        json={"username": os.environ["MILLI_USERNAME"],
              "password": os.environ["MILLI_PASSWORD"]},
        timeout=(5, 20),
    )
    response.raise_for_status()
    csrf = response.headers.get("x-csrf-token")
    if csrf:
        session.headers["x-csrf-token"] = csrf

    wallet = os.environ["MILLI_WALLET"]
    gold = session.get(
        f"{base}/api/v1/wallet/milli/{wallet}/available-balance", timeout=(5, 20)
    ).json()["data"]["availableMilliBalance"]
    rial = session.get(
        f"{base}/api/v1/wallet/rial/available-balance", timeout=(5, 20)
    ).json()["data"]["availableRialBalance"]
    return Decimal(rial) / 10, int(gold)


def melligold() -> tuple[Decimal, int]:
    # Reuses the stored session rather than logging in, so this never triggers
    # an SMS code.
    client = MelliGoldClient()
    client.login()
    return client.get_inventory()


SOURCES = {
    "wallgold": wallgold,
    "miligold": miligold,
    "melligold": melligold,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--only", help="comma-separated subset of venues")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    wanted = set(filter(None, (args.only or "").split(","))) or set(SOURCES)

    # Start from the last file so one venue failing does not erase the others.
    result: dict[str, dict] = {}
    if args.out.exists():
        try:
            result = json.loads(args.out.read_text())
        except ValueError:
            result = {}

    for name, fetch in SOURCES.items():
        if name not in wanted:
            continue
        try:
            cash, gold_mg = fetch()
        except Exception as exc:
            log.warning("%s: %s", name, exc)
            continue
        result[name] = {"cash_tmn": str(cash), "gold_mg": gold_mg}
        log.info("%s: cash %s TMN, gold %s mg", name, f"{cash:,.0f}", gold_mg)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    log.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
