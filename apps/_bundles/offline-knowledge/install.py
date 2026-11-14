#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install the Offline Knowledge bundle (REC-NOMAD-01) through the OneMind gateway.

It files one `app.install` request per app of bundle.json, in order, with the chosen profile's
settings, and waits for each to finish before the next (Library Chat needs Kiwix and Ollama
installed first: contract §12.22 `dependency_missing`). It never approves anything: the owner
approves each request on the dashboard or phone, as for any install (contract §3, §12.1).

  export ONEMIND_TOKEN=...        # the owner's token; never passed on the command line
  python3 -I apps/_bundles/offline-knowledge/install.py --gateway https://onemind.local:8443 \\
      --profile greenhouse-offgrid [--skip kolibri] [--dry-run]

Standard library only. Exit codes: 0 every required app installed, 1 one failed or was
denied, 2 usage or connection problem.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BUNDLE = Path(__file__).with_name("bundle.json")
DONE = {"succeeded"}
FAILED = {"failed", "cancelled", "denied", "expired", "refused"}


def call(gw: str, token: str, method: str, path: str, body: dict | None = None, ctx=None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(gw + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "User-Agent": "onemind-bundle-install"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:  # noqa: S310 (owner-given URL)
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def plan(bundle: dict, profile: str, skip: set[str]) -> list[tuple[str, dict, bool]]:
    if profile not in bundle["profiles"]:
        raise SystemExit(f"unknown profile {profile!r}; choose one of: {', '.join(bundle['profiles'])}")
    settings = bundle["profiles"][profile].get("settings", {})
    return [(a["id"], dict(settings.get(a["id"], {})), bool(a.get("optional")))
            for a in bundle["apps"] if a["id"] not in skip]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gateway", required=True, help="gateway base URL, for example https://onemind.local:8443")
    ap.add_argument("--profile", default="starter")
    ap.add_argument("--skip", action="append", default=[], help="app id to leave out (repeatable)")
    ap.add_argument("--cafile", help="CA certificate of the box, if the gateway uses its own CA")
    ap.add_argument("--wait-hours", type=float, default=24, help="how long to wait for each approval")
    ap.add_argument("--dry-run", action="store_true", help="print the requests, file nothing")
    args = ap.parse_args(argv)

    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    steps = plan(bundle, args.profile, set(args.skip))
    prof = bundle["profiles"][args.profile]
    print(f"{bundle['name']}, profile '{prof['name']}' ({prof['fits']}; about {prof['download_gb']} GB to download)")
    for app_id, settings, optional in steps:
        print(f"  - {app_id}{' (optional)' if optional else ''}: {json.dumps(settings) if settings else 'default settings'}")
    if args.dry_run:
        return 0
    token = os.environ.get("ONEMIND_TOKEN", "")
    if not token:
        print("Set ONEMIND_TOKEN to the owner's token first.", file=sys.stderr)
        return 2
    if not args.gateway.startswith("https://"):
        print("The gateway URL must start with https:// (the token must not travel in clear text).", file=sys.stderr)
        return 2
    ctx = ssl.create_default_context(cafile=args.cafile) if args.cafile else None
    gw = args.gateway.rstrip("/")

    status = 0
    for app_id, settings, optional in steps:
        expires = (datetime.now(timezone.utc) + timedelta(hours=args.wait_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {"app_id": app_id, **({"settings": settings} if settings else {})}
        try:
            code, action = call(gw, token, "POST", "/v1/actions", {
                "type": "app.install", "params": params, "expires_at": expires,
                "idempotency_key": f"bundle-offline-knowledge-{app_id}-{uuid.uuid4()}",
                "reason": f"Offline Knowledge bundle, profile {args.profile}"}, ctx)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"cannot reach the gateway: {e}", file=sys.stderr)
            return 2
        if code not in (200, 201, 202) or "id" not in action:
            why = action.get("message") or action.get("reason") or action.get("code") or f"HTTP {code}"
            print(f"{app_id}: not requested ({why}).")
            if not optional:
                status = 1
                break
            continue
        print(f"{app_id}: requested as action {action['id']}. Approve it on the dashboard or phone.")
        deadline = time.monotonic() + args.wait_hours * 3600
        state = action.get("state", "")
        while state not in DONE | FAILED and time.monotonic() < deadline:
            time.sleep(10)
            try:
                _, action = call(gw, token, "GET", f"/v1/actions/{action['id']}", None, ctx)
            except (urllib.error.URLError, TimeoutError):
                continue
            state = action.get("state", state)
        print(f"{app_id}: {state or 'no answer'}")
        if state not in DONE and not optional:
            status = 1
            break
    if status == 0:
        model = prof.get("model")
        print("\nNext steps (README, First run): pull the model in Ollama"
              + (f" ({model})" if model else "") + " and add a map of your area to Offline Maps.")
    return status


if __name__ == "__main__":
    sys.exit(main())
