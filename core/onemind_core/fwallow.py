# SPDX-License-Identifier: Apache-2.0
"""Firewall allow rules with automatic revert (P-09 part 2): the gateway's half.

Opening a port is the `firewall.allow` action: an owner or an agent asks (`POST /v1/network/firewall/allow`),
only an owner approves, and only with a passkey (D-027/D-028: exposing the box is a security change). After the
approval the host service (`onemindd host serve`, internal/firewall/allow.go) writes one `accept` line into
the OneMind table, in the home-network list or the mesh list and nowhere else: the scope has two values,
`lan` and `mesh`, and the internet is not one of them. The rule starts out *pending*: the host removes it again
after `ttl_seconds` unless the owner confirms it (`POST .../allow/{id}/confirm`), and a pending rule never
survives a restart of the host service or a reboot. Taking a rule away is owner only and needs no approval
(taking exposure away, like stopping a share).

The host service is trusted but not blindly (H-06): `hostfw.py` checks its rule list again before anyone sees
it, and this module re-checks the answer to the one call it makes.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .executors import ExecResult
from .jsonbody import JsonBody
from .storage import StorageClient, StorageTimeout, StorageUnavailable

ACTION = "firewall.allow"
RULE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
SCOPE_WORDS = {"lan": "devices on your home network (LAN)", "mesh": "other machines on your OneMind mesh"}


class AllowParams(JsonBody):
    """What the owner approves: one port, one protocol, one audience. Nothing wider can be said."""

    model_config = ConfigDict(extra="forbid")
    proto: Literal["tcp", "udp"]
    port: int = Field(ge=1, le=65535)
    scope: Literal["lan", "mesh"] = Field(description="lan: devices on the home network; mesh: your other OneMind machines. Never the internet.")


class AllowRequest(AllowParams):
    """POST /v1/network/firewall/allow."""

    reason: str | None = Field(default=None, max_length=500, description="Why, shown to the owner on the approval card.")
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


def phrase(proto: str, port: int, scope: str) -> str:
    return f"{proto.upper()} port {port} for {SCOPE_WORDS.get(scope, scope)}"


class HostAllowClient:
    """The host service's allow calls over its Unix socket (internal/host/firewall_allow.go)."""

    def __init__(self, path, timeout_s: float):
        self.api = StorageClient(path, timeout_s)

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        """(status, answer). Raises HostAllowError when the host cannot be reached."""
        try:
            status, doc = self.api.call(method, path, body)
        except StorageUnavailable:
            raise HostAllowError("host_unavailable", "the host service is not reachable from the gateway") from None
        except StorageTimeout:
            raise HostAllowError("host_timeout", "the host service did not answer in time; check the firewall view before trying again") from None
        return status, doc if isinstance(doc, dict) else {}


class HostAllowError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason, self.message = reason, message


def host_problem(status: int, doc: dict) -> tuple[str, str]:
    """(reason, message) from a host refusal, with only a short, known-shape reason let through."""
    reason = doc.get("reason")
    reason = reason if isinstance(reason, str) and re.fullmatch(r"[a-z_]{1,40}", reason) else f"http_{status}"
    msg = doc.get("message")
    msg = msg[:300] if isinstance(msg, str) and msg and "\x00" not in msg else f"the host service answered {status}"
    return reason, msg


def run_allow(client: HostAllowClient, action_id: str, params: dict, ttl_seconds: int | None = None) -> ExecResult:
    """After the owner's passkey approval: ask the host to open the port as a pending rule."""
    body = {"id": action_id, "proto": params.get("proto"), "port": params.get("port"), "scope": params.get("scope")}
    try:
        status, doc = client.call("POST", "/v1/firewall/allow", body)
    except HostAllowError as exc:
        return ExecResult("failed", exc.message, steps=[{"step": "host", "result": exc.reason}])
    if status != 200 or doc.get("state") not in ("pending", "confirmed") or doc.get("id") != action_id:
        reason, msg = host_problem(status, doc)
        return ExecResult("failed", f"The host did not open the port: {msg}", steps=[{"step": "host", "result": reason}])
    what = phrase(str(params["proto"]), int(params["port"]), str(params["scope"]))
    if doc.get("state") == "confirmed":
        return ExecResult("succeeded", f"{what} is open.", steps=[{"step": "host", "result": "confirmed"}])
    return ExecResult("succeeded", f"{what} is open for now. It closes again by itself unless you confirm it on the Network screen.",
                      steps=[{"step": "host", "result": "pending"}])
