# SPDX-License-Identifier: Apache-2.0
"""onemind-secrets: enter app secrets from a terminal on the hub (until the dashboard form is wired).

    onemind-secrets show hermes-agent
    onemind-secrets approve <action-id> hermes-agent-credentials/OPENROUTER_API_KEY
    onemind-secrets change hermes-agent --set hermes-agent-credentials/OPENROUTER_API_KEY

Values are read without echo from the terminal (or one per line from a pipe), sealed to the
box's key here, and sent only in sealed form, exactly as the dashboard form does. The owner
token comes from ONEMIND_TOKEN or --token-file, never from the command line (the process list
would show it). The hub is ONEMIND_HUB, default http://127.0.0.1:8080 (loopback on the hub).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from .crypto import seal_values

Http = Callable[[str, str, str, dict | None], tuple[int, dict]]


class CliError(Exception):
    pass


def urllib_http(method: str, url: str, token: str, body: dict | None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (the owner's own hub URL)
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {"error": "http", "message": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        raise CliError(f"cannot reach the hub: {e.reason}") from None


def _values(refs: list[str], stdin: TextIO, ask: Callable[[str], str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for ref in refs:
        name, sep, key = ref.partition("/")
        if not sep or not name or not key:
            raise CliError(f"{ref!r} is not <secret>/<key>")
        value = ask(f"{ref} (input hidden): ") if stdin.isatty() else stdin.readline().rstrip("\r\n")
        if not value:
            raise CliError(f"no value for {ref}")
        out.setdefault(name, {})[key] = value
    return out


def main(argv: list[str] | None = None, *, http: Http = urllib_http, stdin: TextIO = sys.stdin,
         stdout: TextIO = sys.stdout, ask: Callable[[str], str] = getpass.getpass,
         env: dict[str, str] | None = None) -> int:
    env = dict(os.environ) if env is None else env
    p = argparse.ArgumentParser(prog="onemind-secrets", description=__doc__.split("\n")[0])
    p.add_argument("--hub", default=env.get("ONEMIND_HUB", "http://127.0.0.1:8080"))
    p.add_argument("--token-file", type=Path, help="file holding the owner token (else $ONEMIND_TOKEN)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="declared secrets and which are set (never values)")
    s.add_argument("app")
    a = sub.add_parser("approve", help="approve an app.install, entering secrets with it")
    a.add_argument("action_id")
    a.add_argument("refs", nargs="*", metavar="SECRET/KEY")
    c = sub.add_parser("change", help="file an app.configure with new, rotated or cleared values")
    c.add_argument("app")
    c.add_argument("--set", dest="sets", action="append", default=[], metavar="SECRET/KEY")
    c.add_argument("--generate", action="append", default=[], metavar="SECRET/KEY")
    c.add_argument("--clear", action="append", default=[], metavar="SECRET/KEY")
    c.add_argument("--reason")
    args = p.parse_args(argv)
    try:
        token = (args.token_file.read_text().strip() if args.token_file else env.get("ONEMIND_TOKEN", "")).strip()
        if not token:
            raise CliError("set ONEMIND_TOKEN or pass --token-file with the owner token")
        hub = args.hub.rstrip("/")

        def call(method: str, path: str, body: dict | None = None) -> dict:
            status, doc = http(method, hub + path, token, body)
            if status >= 400:
                raise CliError(f"{doc.get('error', status)}: {doc.get('message', '')}")
            return doc

        def sealed_body(app_id: str, refs: list[str]) -> dict | None:
            if not refs:
                return None
            return seal_values(call("GET", "/v1/secrets/public-key"), app_id, _values(refs, stdin, ask))

        if args.cmd == "show":
            out = call("GET", f"/v1/apps/{args.app}/secrets")
        elif args.cmd == "approve":
            action = call("GET", f"/v1/actions/{args.action_id}")
            sealed = sealed_body(action["params"]["app_id"], args.refs)
            out = call("POST", f"/v1/actions/{args.action_id}/approve", {"sealed": sealed} if sealed else None)
        else:
            body = {"generate": args.generate, "clear": args.clear,
                    **({"reason": args.reason} if args.reason else {})}
            sealed = sealed_body(args.app, args.sets)
            if sealed:
                body["sealed"] = sealed
            out = call("POST", f"/v1/apps/{args.app}/secrets", body)
            stdout.write(f"filed {out['id']}; approve it with: onemind-secrets approve {out['id']}\n")
        stdout.write(json.dumps(out, indent=2) + "\n")
        return 0
    except (CliError, OSError) as exc:
        sys.stderr.write(f"onemind-secrets: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
