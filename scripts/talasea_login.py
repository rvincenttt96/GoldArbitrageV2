#!/usr/bin/env python3
"""Two-step Talasea login, split so a human can supply the SMS code.

    python3 -m scripts.talasea_login --request
    python3 -m scripts.talasea_login --verify 17472
    python3 -m scripts.talasea_login --status

Two things about this API cost a code each to discover, so they are written down
rather than left to be rediscovered:

* The phone field is `phoneNumber`. The site's bundles use `telephone`, but that
  is a display prop; sending it gets "شماره وارد شده صحیح نیست".
* The code field is `otp`, not `code`. Sending `code` gets "کد وارد شده اشتباه
  است", which reads like a wrong code rather than a wrong field name.

Verifying returns a bearer token, despite the site itself running on cookies.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.talasea.ir/api"
SITE = "https://talasea.ir"
SESSION_FILE = Path("~/goldarb/talasea_session.json").expanduser()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": SITE,
    "Referer": f"{SITE}/login",
}

PHONE_FIELD = "phoneNumber"
CODE_FIELD = "otp"

HTTP_ERROR = 400


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _post(session: requests.Session, path: str, body: dict) -> tuple[int, dict]:
    response = session.post(f"{BASE}{path}", json=body, timeout=(5, 25))
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {"_raw": response.text[:300]}


def request_code(mobile: str) -> dict:
    status, body = _post(_session(), "/auth/sentOTP", {PHONE_FIELD: mobile})
    if status >= HTTP_ERROR:
        raise SystemExit(f"sentOTP failed: HTTP {status} {body}")
    _save({"phone": mobile, "requested_at": time.time()})
    return body


def verify(mobile: str, code: str) -> dict:
    session = _session()
    status, body = _post(
        session, "/auth/verifyOTP", {PHONE_FIELD: mobile, CODE_FIELD: str(code)}
    )
    if status >= HTTP_ERROR:
        raise SystemExit(f"verifyOTP failed: HTTP {status} {body}")

    token = body.get("accessToken") or body.get("token")
    if not token:
        raise SystemExit(f"verifyOTP returned no token: {body}")

    _save({
        "phone": mobile,
        "access_token": token,
        "cookies": session.cookies.get_dict(),
        "verified_at": time.time(),
    })
    return {k: v for k, v in body.items() if k != "accessToken"} | {"accessToken": "<saved>"}


def token_expiry(token: str) -> float | None:
    """Read `exp` from the JWT without verifying it.

    We are deciding when to re-login, not authenticating the token, so the
    signature is the server's business.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return None


def whoami() -> dict:
    state = _load()
    token = state.get("access_token")
    if not token:
        raise SystemExit("no stored session; run --request then --verify")

    session = _session()
    session.headers["Authorization"] = f"Bearer {token}"
    response = session.get(f"{BASE}/account/getUserData", timeout=(5, 25))

    expiry = token_expiry(token)
    out: dict = {"http": response.status_code}
    if expiry:
        out["token_expires_in_hours"] = round((expiry - time.time()) / 3600, 1)
    try:
        out["user"] = response.json()
    except ValueError:
        out["body"] = response.text[:300]
    return out


def _load() -> dict:
    return json.loads(SESSION_FILE.read_text()) if SESSION_FILE.exists() else {}


def _save(state: dict) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(state, indent=2))
    SESSION_FILE.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mobile", default="09362798093")
    parser.add_argument("--request", action="store_true")
    parser.add_argument("--verify", metavar="CODE")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.request:
        print(json.dumps(request_code(args.mobile), ensure_ascii=False, indent=2))
    elif args.verify:
        print(json.dumps(verify(args.mobile, args.verify), ensure_ascii=False, indent=2))
    elif args.status:
        print(json.dumps(whoami(), ensure_ascii=False, indent=2)[:1500])
    else:
        parser.error("pick one of --request, --verify, --status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
