#!/usr/bin/env python3
"""Announces a deployment to the Telegram channel.

Run at the end of every deploy. Without it, a code change and a quiet channel
look identical to a code change that never reached the server, which is exactly
the confusion that let a retired bot keep running for five days.

    python3 -m scripts.notify_deploy --commit <sha> --subject "..." \
        --services goldarb-recorder goldarb-paper
"""

from __future__ import annotations

import argparse
import html
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from services.telegram import send_message

TEHRAN = timezone(timedelta(hours=3, minutes=30))


def _run(*command: str) -> str:
    try:
        return subprocess.run(  # noqa: S603
            command, check=True, capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def service_states(names: list[str]) -> list[tuple[str, str]]:
    return [(n, _run("systemctl", "is-active", n) or "unknown") for n in names]


def format_message(
    commit: str,
    subject: str,
    services: list[tuple[str, str]],
    files_changed: str = "",
) -> str:
    when = datetime.now(TEHRAN).strftime("%Y-%m-%d %H:%M")
    parts = [
        "<b>DEPLOYED</b>",
        f"<i>{html.escape(when)} Tehran</i>",
        "",
    ]
    if commit:
        parts.append(f"Commit <code>{html.escape(commit[:8])}</code>")
    if subject:
        parts.append(f"<i>{html.escape(subject)}</i>")
    if files_changed:
        parts.append(f"<code>{html.escape(files_changed)}</code>")

    if services:
        parts.append("")
        parts.append("<b>Services</b>")
        for name, state in services:
            # A tick is not enough here: a service that failed to come back is
            # the whole reason this message exists.
            mark = "ok" if state == "active" else state.upper()
            parts.append(f"  {html.escape(name)}: <code>{mark}</code>")

    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--files-changed", default="")
    parser.add_argument("--services", nargs="*", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    text = format_message(
        args.commit, args.subject, service_states(args.services), args.files_changed
    )

    if args.dry_run:
        print(text)
        return 0

    send_message(text)
    print("deploy notice sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
