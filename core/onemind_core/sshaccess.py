# SPDX-License-Identifier: Apache-2.0
"""The owner's SSH access: the keys that may log in, and the on/off switch (P-06, D-027/D-028).

SSH is the everyday shell of the box and the way in when the web UI is down, so changing it is a security change:

- Every change is an *owner action* through the approval queue: `ssh.key.add`, `ssh.key.remove` and `ssh.toggle`.
  An owner (or the `onemind` CLI with an owner token) only *requests*; nothing reaches the box until an owner
  approves. An AI agent may not even request one: giving someone a shell is a human call.
- Adding a key, and switching SSH on, need step-up: once passkeys are active the approval must carry a passkey
  assertion (routers/ssh.py, the guard). Removing a key and switching SSH off take exposure away and need none.
- The gateway never sees a private key and never writes a key file. It checks the public key (a plain key, a
  known type, a sane size), shows its fingerprint on the approval card, and hands the line to the host service
  (`onemindd host serve`, internal/ownerssh), which has the box's one writer, `onemind-owner`.
- Keys live in the owner's home on /data and the switch is a flag file on /data, so both survive a reboot and an
  A/B update. The list shown here is read from the box, so a key added on the console shows up too.

Rules on the box (not settable from here): public key only, user `admin` only, no password login, port 22 reachable
from the LAN and the mesh (and the internet on a cloud box), and at most 6 new connections a minute per address (nftables).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .actions import FeatureAction
from .context import Gateway
from .errors import ApiError
from .executors import ExecResult
from .sections import config_section
from .storage import StorageClient, StorageTimeout, StorageUnavailable

log = logging.getLogger("onemind.ssh")
KEY_ADD, KEY_REMOVE, TOGGLE = "ssh.key.add", "ssh.key.remove", "ssh.toggle"
TYPES = (KEY_ADD, KEY_REMOVE, TOGGLE)
MAX_KEYS = 20
MAX_KEY_BYTES = 8192
MIN_RSA_BITS = 2048
REACH = ["lan", "mesh"]
REACH_CLOUD = ["lan", "mesh", "internet"]   # a cloud board: its firewall lets 22 in from any address (rate-limited)
RATE_LIMIT = "6 new connections a minute per address"
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.@+:-]{0,59}$")
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
             "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")
UNAVAILABLE = ("ssh_unavailable", "This box cannot manage SSH yet: the host service is not reachable.")


@config_section("ssh")
@dataclass(frozen=True)
class SshSettings:
    host_socket: Path = Path("/run/onemind/host.sock")   # ONEMIND_SSH_HOST_SOCKET
    host_timeout_s: float = 90.0                         # ONEMIND_SSH_HOST_TIMEOUT_S (a change waits for the box)

    def validate(self) -> None:
        if not self.host_socket.is_absolute():
            raise ValueError("ONEMIND_SSH_HOST_SOCKET must be an absolute path")
        if not 1 <= self.host_timeout_s <= 300:
            raise ValueError("ONEMIND_SSH_HOST_TIMEOUT_S must be between 1 and 300")


class SshHostError(Exception):
    """The host refused or could not do it: a stable `reason` and a sentence for the owner."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason, self.message = reason, message


class SshHost(Protocol):
    def state(self) -> dict:
        """{available, reason, message, enabled, running, internet, keys: [{fingerprint, type, bits, comment}]}.
        `internet` is true on a cloud board, whose firewall lets port 22 in from any address."""

    def add_key(self, line: str) -> None: ...
    def remove_key(self, fingerprint: str) -> None: ...
    def set_enabled(self, on: bool) -> None: ...


class HostSshClient:
    """The real SshHost: JSON over the host service's Unix socket (internal/host/ssh.go)."""

    def __init__(self, settings: SshSettings):
        self.api = StorageClient(settings.host_socket, settings.host_timeout_s)

    def _call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        try:
            status, doc = self.api.call(method, path, body)
        except StorageUnavailable:
            raise SshHostError(*UNAVAILABLE) from None
        except StorageTimeout:
            raise SshHostError("host_timeout", "The host service did not answer in time; check the key list before trying again.") from None
        return status, doc if isinstance(doc, dict) else {}

    def state(self) -> dict:
        gone = {"available": False, "enabled": False, "running": False, "internet": False, "keys": []}
        try:
            status, doc = self._call("GET", "/v1/ssh")
        except SshHostError as e:
            return {**gone, "reason": e.reason, "message": e.message}
        if status == 200 and doc.get("available") is True:
            keys = [k for k in doc.get("keys") or [] if isinstance(k, dict) and FINGERPRINT_RE.match(str(k.get("fingerprint")))]
            return {"available": True, "reason": None, "message": None, "enabled": doc.get("enabled") is True,
                    "running": doc.get("running") is True, "internet": doc.get("internet") is True, "keys": keys}
        why = doc.get("unavailable_reason") if status == 200 else None
        return {**gone, "reason": "ssh_unavailable", "message": f"This box cannot manage SSH yet: {why or 'the host service gave no answer.'}"}

    def _ok(self, status: int, doc: dict) -> None:
        if status == 200:
            return
        if status == 409 and isinstance(doc.get("reason"), str):
            raise SshHostError(doc["reason"], str(doc.get("message") or "The host refused."))
        raise SshHostError("host_error", "The host service could not do it; see the box's journal.")

    def add_key(self, line: str) -> None:
        self._ok(*self._call("POST", "/v1/ssh/keys", {"public_key": line}))

    def remove_key(self, fingerprint: str) -> None:
        self._ok(*self._call("POST", "/v1/ssh/keys/remove", {"fingerprint": fingerprint}))

    def set_enabled(self, on: bool) -> None:
        self._ok(*self._call("PUT", "/v1/ssh/enabled", {"enabled": on}))


# ---- the public key -------------------------------------------------------------------------------
@dataclass(frozen=True)
class ParsedKey:
    line: str          # what the box is given: "type base64 comment", one line
    type: str
    fingerprint: str   # SHA256:...
    comment: str
    bits: int | None


def key_id(fingerprint: str) -> str:
    """A URL-safe name for a key in routes: the fingerprint without SHA256:, with + and / made - and _."""
    return fingerprint.removeprefix("SHA256:").replace("+", "-").replace("/", "_")


def _mpint_bits(blob: bytes, at: int) -> tuple[int, int]:
    (n,) = struct.unpack_from(">I", blob, at)
    raw = blob[at + 4: at + 4 + n]
    if len(raw) != n:
        raise ValueError("short key")
    return int.from_bytes(raw, "big").bit_length(), at + 4 + n


def parse_public_key(text: str, label: str | None = None) -> ParsedKey:
    """A plain one-line OpenSSH public key, or ApiError 422. Options (command=, from=) are refused: they are not
    a key, and `command=` would run something else at login."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_KEY_BYTES:
        raise ApiError(422, "conflict", "That is not an SSH public key (paste the one line of the .pub file).", reason="invalid_key")
    line = text.strip()
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in line):
        raise ApiError(422, "conflict", "An SSH public key is one line, with no control characters.", reason="invalid_key")
    parts = line.split(None, 2)
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        raise ApiError(422, "conflict", "That is not a plain SSH public key of a supported type "
                       f"({', '.join(t for t in KEY_TYPES if '@' not in t)}, or a security key). Options such as command= are not accepted.",
                       reason="invalid_key")
    kind, b64 = parts[0], parts[1]
    try:
        blob = base64.b64decode(b64, validate=True)
        (n,) = struct.unpack_from(">I", blob, 0)
        if blob[4:4 + n].decode("ascii") != kind:
            raise ValueError("type mismatch")
        bits = None
        if kind == "ssh-rsa":
            _, at = _mpint_bits(blob, 4 + n)          # the exponent
            bits, _ = _mpint_bits(blob, at)           # the modulus
    except (ValueError, struct.error, UnicodeDecodeError):
        raise ApiError(422, "conflict", "That SSH public key does not parse; copy the whole line again.", reason="invalid_key") from None
    if bits is not None and bits < MIN_RSA_BITS:
        raise ApiError(422, "conflict", f"That RSA key is only {bits} bits; use at least {MIN_RSA_BITS}, or better an ed25519 key.",
                       reason="weak_key")
    comment = (label if label is not None else (parts[2] if len(parts) > 2 else "")).strip()
    if label is not None and not LABEL_RE.match(comment):
        raise ApiError(422, "conflict", "A label is 1 to 60 letters, digits, spaces and . _ @ + : -", reason="invalid_label")
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return ParsedKey(f"{kind} {b64}" + (f" {comment}" if comment else ""), kind, fp, comment[:120], bits)


# ---- the service ----------------------------------------------------------------------------------
class SshService:
    def __init__(self, gw: Gateway, host: SshHost | None = None):
        self.gw = gw
        self.host: SshHost = host or HostSshClient(gw.settings.section(SshSettings))

    # reads
    def view(self) -> dict:
        st = self.host.state()
        keys = [{"id": key_id(k["fingerprint"]), "fingerprint": k["fingerprint"], "type": str(k.get("type") or ""),
                 "bits": int(k["bits"]) if isinstance(k.get("bits"), int) else None, "comment": str(k.get("comment") or "")}
                for k in st["keys"]]
        if not st["available"]:
            state = "unavailable"
        elif not st["enabled"]:
            state = "off"
        elif st["running"]:
            state = "on"
        else:
            state = "waiting_for_key" if not keys else "starting"
        return {"service": {"available": st["available"], "reason": st["reason"], "message": st["message"],
                            "state": state, "enabled": st["enabled"], "running": st["running"],
                            "port": 22, "user": "admin", "reach": REACH_CLOUD if st.get("internet") is True else REACH,
                            "password_login": False,
                            "rate_limit": RATE_LIMIT, "max_keys": MAX_KEYS},
                "keys": keys}

    def find(self, key: str) -> dict | None:
        for k in self.view()["keys"]:
            if key in (k["id"], k["fingerprint"]):
                return k
        return None

    # the check made when a request is filed and again at approval
    def refusal(self, action_type: str, params: dict) -> tuple[str, str] | None:
        st = self.host.state()
        if not st["available"]:
            return st["reason"] or "ssh_unavailable", st["message"] or UNAVAILABLE[1]
        have = {k["fingerprint"] for k in st["keys"]}
        if action_type == KEY_ADD:
            if params["fingerprint"] in have:
                return "already_authorised", "That key is already authorised."
            if len(have) >= MAX_KEYS:
                return "too_many_keys", f"This box allows at most {MAX_KEYS} SSH keys; remove one first."
        elif action_type == KEY_REMOVE and params["fingerprint"] not in have:
            return "no_such_key", "That key is not on this box any more."
        return None

    def check_request(self, action_type: str, params: dict) -> None:
        if (r := self.refusal(action_type, params)) is not None:
            raise ApiError(409, "policy_refused", r[1], reason=r[0])

    def _recheck(self, a) -> str | None:
        r = self.refusal(a.type, a.params)
        return r[1] if r else None

    # what runs after an owner approved
    def _run(self, a, finish) -> None:
        p = a.params
        try:
            if a.type == KEY_ADD:
                self.host.add_key(p["public_key"])
                msg, step = f"SSH key {p['fingerprint']} can now log in as admin.", {"step": "authorise key", "fingerprint": p["fingerprint"]}
            elif a.type == KEY_REMOVE:
                self.host.remove_key(p["fingerprint"])
                msg = f"SSH key {p['fingerprint']} was removed; new logins with it are refused."
                step = {"step": "remove key", "fingerprint": p["fingerprint"]}
            else:
                self.host.set_enabled(p["enabled"] is True)
                msg = "SSH is on (it listens once a key exists)." if p["enabled"] else "SSH is off, also after a reboot."
                step = {"step": "switch ssh", "enabled": p["enabled"] is True}
        except SshHostError as e:
            finish(ExecResult("failed", e.message, steps=[{"step": a.type, "result": e.reason}]))
            return
        except Exception as e:  # noqa: BLE001 - an approved action must always end
            log.exception("%s failed", a.type)
            finish(ExecResult("failed", f"The change failed on the gateway ({type(e).__name__}); check the key list.",
                              steps=[{"step": a.type, "result": "internal_error"}]))
            return
        finish(ExecResult("succeeded", msg, steps=[{**step, "result": "done"}]))

    def register(self) -> None:
        # "actuate": the box starts to let someone in, or stops. Never covered by a standing approval. No agent
        # may request it (an empty requesters set: owners only).
        for t in TYPES:
            self.gw.actions.register_type(t, FeatureAction("actuate", self._run, frozenset(), check=self._recheck))
