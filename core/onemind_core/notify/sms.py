# SPDX-License-Identifier: Apache-2.0
"""SMS alerts through a provider-neutral adapter (issue #869; NOTIFICATIONS.md §6).

The `sms` channel kind sends one short text through an *adapter*: an object with
`send(to, text) -> Receipt`. Adapters register by name in `ADAPTERS`. The one built here,
`https`, POSTs to the provider URL the owner typed, as JSON or form fields, with a bearer token
or basic auth. There is no provider SDK and no provider name in the code: a provider is picked
by its URL and its field names, so a new one needs config, not code.

Rules kept here, so no caller can break them:
- the text is only "OneMind: [severity] title" and a short link hint, never the body (no
  secrets, file names or camera frames);
- the credential is the channel secret, sealed at rest by SecretBox; it is never part of the
  config, a log line, the audit text or an API answer, and provider replies are never echoed;
- every request goes through `channels.http_exchange`: no redirects, no proxies, the peer
  address checked after connect.
The daily cap and the per-hour limit are counted in the gateway (service.py), never trusted to
a provider, so a loop cannot run up a bill.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode, urlsplit

from .catalogue import SEVERITIES
from .channels import OPAQUE_TITLE, DeliveryError, http_exchange

E164 = re.compile(r"^\+[1-9]\d{6,14}$")
SENDER = re.compile(r"^(?:\+[1-9]\d{6,14}|[A-Za-z0-9][A-Za-z0-9 ]{0,10})$")   # number or alphanumeric id
FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,39}$")
RECEIPT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
DEFAULT_FIELDS = {"to": "to", "from": "from", "text": "text"}
DAILY_CAP = 20          # texts per channel per 24 h (issue #869)
MAX_DAILY_CAP = 500
PER_HOUR = 5            # then held, and sent as one summary (like every channel's hourly limit)
MAX_PER_HOUR = 60
MAX_TEXT = 320          # two SMS segments at most
HINT = "Open OneMind for details."


@dataclass(frozen=True)
class Receipt:
    """What the provider said: its HTTP status and its message id (when it gave a plain one)."""
    status: int
    provider_id: str | None

    def as_json(self) -> dict:
        return {"status": self.status, "provider_id": self.provider_id}


class SmsAdapter(Protocol):
    def send(self, to: str, text: str) -> Receipt: ...


AdapterFactory = Callable[..., SmsAdapter]   # (config, secret, *, timeout, lan_ok) -> SmsAdapter
ADAPTERS: dict[str, AdapterFactory] = {}


def register(name: str) -> Callable[[AdapterFactory], AdapterFactory]:
    def deco(factory: AdapterFactory) -> AdapterFactory:
        ADAPTERS[name] = factory
        return factory
    return deco


def validate_config(config: dict) -> dict:
    """Normalised `sms` channel config, or ValueError. The credential is the channel secret, never here."""
    def text(key: str, limit: int, required: bool = True) -> str | None:
        v = config.get(key)
        if v is None and not required:
            return None
        if not isinstance(v, str) or not v.strip() or len(v) > limit or any(c in v for c in "\r\n\t"):
            raise ValueError(f"config.{key} must be a non-empty string")
        return v.strip()

    def number(key: str, default: int, top: int) -> int:
        v = config.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= top:
            raise ValueError(f"config.{key} must be a whole number from 1 to {top}")
        return v

    def choice(key: str, options: tuple[str, ...], default: str) -> str:
        v = config.get(key, default)
        if v not in options:
            raise ValueError(f"config.{key} must be one of {', '.join(options)}")
        return v

    url = text("url", 500)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("config.url must be an https URL without credentials")
    to = text("to", 16)
    if not E164.match(to):
        raise ValueError("config.to must be a phone number in international form, like +15550100123")
    out: dict = {
        "url": url, "to": to,
        "adapter": choice("adapter", tuple(ADAPTERS), "https"),
        "format": choice("format", ("json", "form"), "json"),
        "auth": choice("auth", ("bearer", "basic", "none"), "bearer"),
        "daily_cap": number("daily_cap", DAILY_CAP, MAX_DAILY_CAP),
        "per_hour": number("per_hour", PER_HOUR, MAX_PER_HOUR),
        "min_severity": choice("min_severity", SEVERITIES, "warning"),
    }
    sender = text("from", 16, required=False)
    if sender is not None:
        if not SENDER.match(sender):
            raise ValueError("config.from must be a phone number or a sender name of up to 11 letters and digits")
        out["from"] = sender
    if out["auth"] == "basic":
        out["username"] = text("username", 254)
    fields = config.get("fields")
    if fields is not None:
        if (not isinstance(fields, dict) or set(fields) - set(DEFAULT_FIELDS)
                or not all(isinstance(v, str) and FIELD.match(v) for v in fields.values())):
            raise ValueError("config.fields maps to, from and text to the provider's field names")
        out["fields"] = dict(fields)
    return out


def text_for(level: str, msg) -> str:
    """The SMS text: the title and a link hint only, whatever the alert's body says."""
    if level == "opaque":
        return OPAQUE_TITLE
    hint = msg.link if level == "full" and msg.link and len(msg.link) <= 160 else HINT
    head = f"OneMind: [{msg.severity}] " + " ".join(msg.title.split())
    room = MAX_TEXT - len(hint) - 3
    if len(head) > room:
        head = head[:room - 1].rstrip() + "…"
    return f"{head} - {hint}"


def _receipt_id(raw: bytes) -> str | None:
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    for key in ("id", "sid", "message_id", "messageId"):
        v = doc.get(key)
        if isinstance(v, (str, int)) and not isinstance(v, bool) and RECEIPT_ID.match(str(v)):
            return str(v)
    return None


@register("https")
class HttpsAdapter:
    """POST the text to the owner's provider URL; the channel secret is the bearer token or password."""

    def __init__(self, config: dict, secret: str | None, *, timeout: float, lan_ok: bool):
        self.cfg, self.secret, self.timeout, self.lan_ok = config, secret, timeout, lan_ok

    def send(self, to: str, text: str) -> Receipt:
        names = {**DEFAULT_FIELDS, **self.cfg.get("fields", {})}
        doc = {names["to"]: to, names["text"]: text}
        if self.cfg.get("from"):
            doc[names["from"]] = self.cfg["from"]
        if self.cfg.get("format") == "form":
            body, ctype = urlencode(doc).encode(), "application/x-www-form-urlencoded"
        else:
            body, ctype = json.dumps(doc, ensure_ascii=False).encode(), "application/json"
        headers = {"Content-Type": ctype, "Accept": "application/json"}
        auth = self.cfg.get("auth", "bearer")
        if auth == "bearer" and self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        elif auth == "basic" and self.secret:
            pair = f"{self.cfg['username']}:{self.secret}".encode()
            headers["Authorization"] = "Basic " + base64.b64encode(pair).decode()
        status, raw = http_exchange(self.cfg["url"], body, headers, self.timeout, self.lan_ok)
        return Receipt(status, _receipt_id(raw))


def send(config: dict, secret: str | None, level: str, msg, *, timeout: float, lan_ok: bool) -> Receipt:
    factory = ADAPTERS.get(config.get("adapter", "https"))
    if factory is None:
        raise DeliveryError("unknown sms adapter")
    return factory(config, secret, timeout=timeout, lan_ok=lan_ok).send(config["to"], text_for(level, msg))
