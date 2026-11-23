#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install the Offline Knowledge bundle (REC-NOMAD-01) through the OneMind gateway.

It files `app.install`, then `app.configure` for the chosen profile's settings, in order,
and waits for each owner-approved action to finish before the next (Library Chat needs Kiwix and Ollama
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
import math
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
FAILED = {"failed", "cancelled", "denied", "expired", "refused", "outcome_unknown"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the owner's bearer token to a redirected URL.


def call(gw: str, token: str, method: str, path: str, body: dict | None = None, ctx=None) -> tuple[int, dict | list]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(gw + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "User-Agent": "onemind-bundle-install"})
    try:
        with urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), NoRedirect()).open(req, timeout=30) as r:  # noqa: S310 (owner-given URL)
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


def catalog_problem(app: dict | None) -> str | None:
    if app is None:
        return "missing from the gateway catalogue"
    if app.get("tier") == "blocked":
        return "tier blocked; see the app README for the gate's reason"
    if app.get("status") not in {"installed", "not_installed", "failed", "unknown"}:
        return f"status {app.get('status')!r}; resolve the app state first"
    scan = app.get("scan")
    if not isinstance(scan, dict) or scan.get("result") != "pass":
        return "missing or failed security scan"
    try:
        scanned = datetime.fromisoformat(scan["scanned_at"].replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - scanned
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return "invalid security scan timestamp"
    if not -timedelta(minutes=5) <= age <= timedelta(days=7):
        return "security scan is stale or dated in the future"
    return None


def request_action(gw: str, token: str, action_type: str, params: dict, wait_hours: float, ctx) -> bool:
    """Request and observe one action; owner approval stays in the dashboard or phone."""
    expires = (datetime.now(timezone.utc) + timedelta(hours=wait_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    code, action = call(gw, token, "POST", "/v1/actions", {
        "type": action_type, "params": params, "expires_at": expires,
        "idempotency_key": f"bundle-offline-knowledge-{uuid.uuid4()}"}, ctx)
    if code not in (200, 201, 202) or not isinstance(action, dict) or not action.get("id"):
        why = action.get("message", f"HTTP {code}") if isinstance(action, dict) else f"HTTP {code}"
        print(f"{params['app_id']}: {action_type} not requested ({why}).")
        return False
    action_id = action["id"]
    print(f"{params['app_id']}: {action_type} requested as {action_id}. Approve it on the dashboard or phone.")
    deadline = time.monotonic() + wait_hours * 3600
    state = action.get("state", "")
    while state not in DONE | FAILED and time.monotonic() < deadline:
        time.sleep(min(10, max(0, deadline - time.monotonic())))
        try:
            code, observed = call(gw, token, "GET", f"/v1/actions/{action_id}", None, ctx)
        except (urllib.error.URLError, TimeoutError):
            continue
        if code == 200 and isinstance(observed, dict) and observed.get("id") == action_id:
            state = observed.get("state", state)
        elif code in (401, 403, 404):
            print(f"{params['app_id']}: cannot observe {action_id} (HTTP {code}).")
            return False
    print(f"{params['app_id']}: {state if state in DONE | FAILED else 'timed out; action may still be pending'}")
    return state in DONE


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gateway", required=True, help="gateway base URL, for example https://onemind.local:8443")
    ap.add_argument("--profile", default="starter")
    ap.add_argument("--skip", action="append", default=[], help="app id to leave out (repeatable)")
    ap.add_argument("--cafile", help="CA certificate of the box, if the gateway uses its own CA")
    ap.add_argument("--wait-hours", type=float, default=24, help="how long to wait for each approval")
    ap.add_argument("--dry-run", action="store_true", help="print the requests, file nothing")
    args = ap.parse_args(argv)
    if not math.isfinite(args.wait_hours) or not 0 < args.wait_hours <= 168:
        ap.error("--wait-hours must be greater than zero and at most 168")

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

    try:
        code, rows = call(gw, token, "GET", "/v1/apps", ctx=ctx)
        if code != 200 or not isinstance(rows, list):
            raise ValueError(f"cannot read gateway catalogue (HTTP {code})")
        catalog = {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"Preflight failed: {e}", file=sys.stderr)
        return 2
    eligible = []
    for app_id, settings, optional in steps:
        problem = catalog_problem(catalog.get(app_id))
        if problem:
            print(f"{app_id}: {'optional app skipped' if optional else 'cannot install'} ({problem}).")
            if not optional:
                return 1
        else:
            eligible.append((app_id, settings, optional))

    status = 0
    for app_id, settings, optional in eligible:
        try:
            succeeded = catalog[app_id].get("status") == "installed"
            if not succeeded:
                succeeded = request_action(gw, token, "app.install", {"app_id": app_id}, args.wait_hours, ctx)
            if succeeded and settings:
                succeeded = request_action(gw, token, "app.configure", {
                    "app_id": app_id, "settings": settings}, args.wait_hours, ctx)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"{app_id}: gateway request failed ({e}).", file=sys.stderr)
            succeeded = False
        if not succeeded:
            if not optional:
                status = 1
                break
            print(f"{app_id}: optional app skipped; required apps will continue.")
    if status == 0:
        model = prof.get("model")
        print("\nNext steps (README, First run): pull the model in Ollama"
              + (f" ({model})" if model else "") + " and add a map of your area to Offline Maps.")
    return status


if __name__ == "__main__":
    sys.exit(main())
