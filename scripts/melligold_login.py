#!/usr/bin/env python3
"""Two-step MelliGold login, split so a human can supply the SMS code.

MelliGold sends a one-time code to the account's phone on every fresh login, so
the login cannot be fully automated. It can, however, be made rare: verifying
returns a refresh token that mints new access tokens without another code. This
script does the two halves separately and persists the result, so the SMS step
happens once rather than on every restart.

    python3 scripts/melligold_login.py --request
    python3 scripts/melligold_login.py --verify 123456
    python3 scripts/melligold_login.py --status

Deliberately never retries a failed --request: repeatedly asking for codes is
the fastest way to get an account rate-limited or locked.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://melligold.com"
SESSION_FILE = Path("~/goldarb/melligold_session.json").expanduser()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa-IR,fa;q=0.9",
    "Content-Type": "application/json",
    "Origin": BASE,
    "Referer": f"{BASE}/pwa/account",
}


def make_session() -> requests.Session:
    """A session that has already cleared the CDN's bot challenge.

    melligold.com sits behind ArvanCloud, which answers a cold client with a 307
    cookie challenge. Loading the app page first banks that cookie so the API
    calls that follow are answered rather than bounced.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    session.get(f"{BASE}/pwa/account", timeout=(5, 20))
    return session


def request_code(mobile: str) -> dict:
    session = make_session()
    response = session.post(
        f"{BASE}/api/v1/authentication/login-register/",
        json={"mobile": mobile},
        headers=HEADERS,
        timeout=(5, 20),
    )
    payload = _json(response)
    if not response.ok:
        raise SystemExit(f"login-register failed: HTTP {response.status_code} {payload}")

    # login-register hands back a memo that verify has to echo. Losing it means
    # burning the code and asking for another one.
    memo = (payload.get("data") or {}).get("memo")
    if not memo:
        raise SystemExit(f"login-register returned no memo: {payload}")

    # The CDN cookies are part of what makes the follow-up verify work, so they
    # are carried forward rather than starting a fresh session for step two.
    _save({
        "mobile": mobile,
        "memo": memo,
        "cookies": session.cookies.get_dict(),
        "requested_at": time.time(),
    })
    return payload


def verify(code: str) -> dict:
    state = _load()
    mobile, memo = state.get("mobile"), state.get("memo")
    if not mobile or not memo:
        raise SystemExit("no pending login; run --request first")

    session = make_session()
    for name, value in state.get("cookies", {}).items():
        session.cookies.set(name, value)

    response = session.post(
        f"{BASE}/api/v1/authentication/verify/",
        json={
            "code": str(code),
            "mobile": mobile,
            "utm": "-",
            "referral_code": "-",
            "memo": memo,
        },
        headers=HEADERS,
        timeout=(5, 20),
    )
    payload = _json(response)
    if not response.ok:
        raise SystemExit(f"verify failed: HTTP {response.status_code} {payload}")

    data = payload.get("data", payload)
    access, refresh = data.get("access"), data.get("refresh")
    if not access or not refresh:
        raise SystemExit(f"verify returned no tokens: {payload}")

    _save({
        "mobile": mobile,
        "memo": memo,
        "access": access,
        "refresh": refresh,
        "cookies": session.cookies.get_dict(),
        "verified_at": time.time(),
    })
    return payload


def refresh_access() -> dict:
    state = _load()
    if not state.get("refresh"):
        raise SystemExit("no refresh token stored; run --request then --verify")

    session = make_session()
    for name, value in state.get("cookies", {}).items():
        session.cookies.set(name, value)

    response = session.post(
        f"{BASE}/api/v1/authentication/refresh/",
        json={"refresh": state["refresh"]},
        headers=HEADERS,
        timeout=(5, 20),
    )
    payload = _json(response)
    if not response.ok:
        raise SystemExit(f"refresh failed: HTTP {response.status_code} {payload}")

    data = payload.get("data", payload)
    if data.get("access"):
        state["access"] = data["access"]
        state["refresh"] = data.get("refresh", state["refresh"])
        state["refreshed_at"] = time.time()
        _save(state)
    return payload


def _json(response: requests.Response) -> dict:
    try:
        return response.json()
    except ValueError:
        return {"_raw": response.text[:400]}


def _load() -> dict:
    if not SESSION_FILE.exists():
        return {}
    return json.loads(SESSION_FILE.read_text())


def _save(state: dict) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(state, indent=2))
    SESSION_FILE.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mobile", default="09362798093")
    parser.add_argument("--request", action="store_true")
    parser.add_argument("--verify", metavar="CODE")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.request:
        print(json.dumps(request_code(args.mobile), ensure_ascii=False, indent=2))
    elif args.verify:
        print(json.dumps(verify(args.verify), ensure_ascii=False, indent=2))
    elif args.refresh:
        print(json.dumps(refresh_access(), ensure_ascii=False, indent=2))
    elif args.status:
        state = _load()
        print(json.dumps(
            {k: (f"<{len(v)} chars>" if k in {"access", "refresh"} else v)
             for k, v in state.items() if k != "cookies"},
            ensure_ascii=False, indent=2,
        ))
    else:
        parser.error("pick one of --request, --verify, --refresh, --status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
