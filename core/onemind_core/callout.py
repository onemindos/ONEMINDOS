# SPDX-License-Identifier: Apache-2.0
"""The NATS auth callout: NATS asks the gateway who may connect (D-029, the hybrid; design N9).

In plain words: when a program the hub's NATS does not know connects (today: an AI agent), nats-server
does not decide itself. It sends the gateway a signed question on `$SYS.REQ.USER.AUTH` (in account
AUTH, where only this responder signs in): "this client, with this key and this signed nonce, wants
in". The gateway answers with a signed "no", or with a short-lived user JWT that places the client in
account AGENTS with exactly the allow lists the gateway gives that agent (natsconf.AgentUser.allow).

- **The gateway decides; NATS enforces.** Only a registered agent key (agents_nats, the owner adds or
  removes it) whose holder signed the server's nonce gets in, and never while "Stop everything" for
  agents is on (agent_stop, D-029 "Stop everything also cuts AI agents off the bus"). Removing a key
  refuses the next connect without a reload, and the JWT expires after `ttl_s`, so a live connection
  is cut by then at the latest and must ask again.
- **Fail closed.** No answer within nats-server's timeout means no connection. So with the gateway
  down, no agent gets in, while the pinned list (natsconf.CalloutAccount: hub services, machines,
  this responder) never waits for the gateway: machines keep reconnecting.
- **Nothing on NATS approves anything.** An admitted agent can talk and ask; a person still approves.
- Every answer is an audit line (`nats.callout`): who, which key, allowed or why not.

Not yet: request encryption with an xkey. nats-server supports it, but its NaCl box is not in
`cryptography`, and the core adds no new dependency in this step. The request carries the client's
public key and a one-time nonce signature, no password; it never leaves the hub's loopback NATS, and
only the responder's user can subscribe in AUTH. Turning xkey on is a follow-up (needs PyNaCl).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import natsjwt
from .natsconf import AGENT_RESPONSES, AGENTS_ACCOUNT, AgentUser, CalloutAccount

log = logging.getLogger("onemind.callout")

AUTH_SUBJECT = "$SYS.REQ.USER.AUTH"
DEFAULT_TTL_S = 600
RETRY_S = 5.0
ISSUER_FILE = "callout-issuer.nk"     # account seed: signs the answers (one key per purpose, D-029)
SERVICE_FILE = "callout-service.nk"   # user seed: the responder's own sign-in, in account AUTH


@dataclass(frozen=True)
class CalloutKeys:
    issuer: Ed25519PrivateKey
    service_seed: Path

    @property
    def account(self) -> CalloutAccount:
        svc = natsjwt.decode_seed(self.service_seed.read_text(encoding="ascii"), natsjwt.PREFIX_USER)
        return CalloutAccount(natsjwt.public_key(self.issuer, natsjwt.PREFIX_ACCOUNT),
                              natsjwt.public_key(svc, natsjwt.PREFIX_USER))


def load_keys(directory: Path) -> CalloutKeys:
    """The issuer and responder keys in the gateway's custodian directory, made on first use (0600)."""
    issuer = natsjwt.load_or_create_seed(directory / ISSUER_FILE, natsjwt.PREFIX_ACCOUNT)
    natsjwt.load_or_create_seed(directory / SERVICE_FILE, natsjwt.PREFIX_USER)
    return CalloutKeys(issuer, directory / SERVICE_FILE)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str            # "" when allowed
    agent: str | None      # agent:<token> when the key is a registered agent's
    nkey: str | None
    response: str          # the signed authorization response JWT


def answer(request: str, issuer: Ed25519PrivateKey, agents: dict[str, AgentUser], stopped: bool,
           now: float, ttl_s: int = DEFAULT_TTL_S) -> Decision:
    """The gateway's answer to one authorization request (a server-signed JWT). Raises JwtError when
    the request itself does not verify: then nothing is answered and nats-server refuses on timeout."""
    claims = natsjwt.decode(request, natsjwt.PREFIX_SERVER)
    req = claims.get("nats") or {}
    server_id = (req.get("server_id") or {}).get("id")
    user_nkey = req.get("user_nkey")
    if req.get("type") != "authorization_request" or server_id != claims.get("iss"):
        raise natsjwt.JwtError("not an authorization request from this server")
    natsjwt.decode_public(str(user_nkey), natsjwt.PREFIX_USER)
    opts, info = req.get("connect_opts") or {}, req.get("client_info") or {}
    nkey = opts.get("nkey") or None
    agent = agents.get(nkey) if nkey else None
    if stopped:
        reason = "agents are stopped (Stop everything is on)"
    elif agent is None:
        reason = "unknown key: no registered agent signs in with it"
    elif not natsjwt.verify_nonce(nkey, str(info.get("nonce") or ""), str(opts.get("sig") or "")):
        reason = "the nonce signature does not verify with the key"
    else:
        reason = ""
    body: dict = {"type": "authorization_response", "version": 2}
    if reason:
        body["error"] = reason
    else:
        pub, sub = agent.allow()
        n, ttl = AGENT_RESPONSES
        user = {"sub": user_nkey, "aud": AGENTS_ACCOUNT, "name": agent.principal_id, "exp": int(now) + int(ttl_s),
                "nats": {"pub": {"allow": pub}, "sub": {"allow": sub},
                         "resp": {"max": n, "ttl": _duration_ns(ttl)},
                         "subs": -1, "data": -1, "payload": -1, "type": "user", "version": 2}}
        body["jwt"] = natsjwt.encode(user, issuer, natsjwt.PREFIX_ACCOUNT, now)
    response = natsjwt.encode({"sub": user_nkey, "aud": server_id, "nats": body}, issuer, natsjwt.PREFIX_ACCOUNT, now)
    return Decision(not reason, reason, agent.principal_id if agent else None, nkey, response)


def _duration_ns(text: str) -> int:
    units = {"s": 10**9, "m": 60 * 10**9, "h": 3600 * 10**9}
    return int(text[:-1]) * units[text[-1]]


class CalloutResponder:
    """Answers `$SYS.REQ.USER.AUTH` on the hub's NATS, as the AUTH account's one user. Runs in the
    background and keeps reconnecting; while it is not connected, unknown clients are refused."""

    def __init__(self, url: str, keys: CalloutKeys, agents: Callable[[], list[AgentUser]],
                 stopped: Callable[[], bool], audit=None, clock: Callable[[], float] | None = None,
                 ttl_s: int = DEFAULT_TTL_S):
        import time

        self.url, self.keys, self.agents, self.stopped = url, keys, agents, stopped
        self.audit, self.clock, self.ttl_s = audit, clock or time.time, ttl_s
        self.nc = None
        self.answered = 0

    def handle(self, data: bytes) -> bytes | None:
        try:
            d = answer(data.decode("ascii", "replace"), self.keys.issuer,
                       {a.nkey: a for a in self.agents()}, bool(self.stopped()), self.clock(), self.ttl_s)
        except natsjwt.JwtError as exc:
            log.warning("auth callout: a request that does not verify was ignored (%s)", exc)
            return None
        self.answered += 1
        if self.audit is not None:
            self.audit.append("nats.callout", {"kind": "service", "id": "nats"}, None,
                              {"decision": "allowed" if d.allowed else "denied", "agent": d.agent,
                               "nkey": d.nkey, "reason": d.reason or None})
        return d.response.encode()

    async def run(self) -> None:
        from .bus import SeedClient

        while True:
            try:
                nc = SeedClient()
                await nc.connect(self.url, nkeys_seed=str(self.keys.service_seed), connect_timeout=2,
                                 allow_reconnect=True, max_reconnect_attempts=-1, reconnect_time_wait=2,
                                 name="onemind-gateway-callout")

                async def on_request(msg) -> None:
                    out = self.handle(msg.data)
                    if out is not None and msg.reply:
                        await nc.publish(msg.reply, out)

                await nc.subscribe(AUTH_SUBJECT, cb=on_request)
                self.nc = nc
                log.info("auth callout responder connected")
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if self.nc is not None:
                    with contextlib.suppress(Exception):
                        await self.nc.close()
                raise
            except Exception as exc:  # NATS down: unknown clients are refused meanwhile (fail closed)
                log.warning("auth callout responder not connected (%s); retrying", exc.__class__.__name__)
                await asyncio.sleep(RETRY_S)
