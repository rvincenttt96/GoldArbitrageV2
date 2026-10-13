#!/usr/bin/env python3
"""Run a command on the Iranian VPS over SSH.

Usage:
    python3 scripts/vps.py 'uname -a'
    python3 scripts/vps.py --file local.sh          # copy up and run
    cat cmd.sh | python3 scripts/vps.py --stdin
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import paramiko

HOST = "62.60.198.99"
PORT = 2222
USER = "root"
KEY = Path.home() / ".ssh" / "goldarb_agent"


def connect(attempts: int = 6) -> paramiko.SSHClient:
    """Open a session, retrying through the link's intermittent drops.

    The route into Iran drops connections often enough that a single failed
    dial says nothing about whether the host is up.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                HOST,
                port=PORT,
                username=USER,
                key_filename=str(KEY),
                timeout=20,
                banner_timeout=25,
                auth_timeout=25,
            )
            return client
        except Exception as exc:
            last = exc
            client.close()
            if attempt < attempts:
                print(
                    f"[vps] dial {attempt}/{attempts} failed "
                    f"({type(exc).__name__}), retrying",
                    file=sys.stderr,
                )
                time.sleep(min(2 * attempt, 10))
    raise SystemExit(f"[vps] could not connect after {attempts} attempts: {last!r}")


def run(client: paramiko.SSHClient, command: str, timeout: int = 300) -> int:
    _, stdout, stderr = client.exec_command(command, timeout=timeout, get_pty=False)
    for line in stdout:
        sys.stdout.write(line)
    err = stderr.read().decode(errors="replace")
    if err.strip():
        sys.stderr.write(err)
    return stdout.channel.recv_exit_status()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?")
    parser.add_argument("--file", help="upload this local script and run it")
    parser.add_argument("--stdin", action="store_true", help="read script from stdin")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    client = connect()
    try:
        if args.file or args.stdin:
            body = (
                Path(args.file).read_text(encoding="utf-8")
                if args.file
                else sys.stdin.read()
            )
            remote = "/tmp/_vps_task.sh"
            sftp = client.open_sftp()
            with sftp.file(remote, "w") as handle:
                handle.write(body)
            sftp.close()
            return run(client, f"bash {remote}", args.timeout)

        if not args.command:
            parser.error("give a command, --file, or --stdin")
        return run(client, args.command, args.timeout)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
