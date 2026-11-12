# SPDX-License-Identifier: Apache-2.0
"""Channel senders and content levels (contract §12.14; docs/architecture/NOTIFICATIONS.md §6).

Kinds built here:
- `unifiedpush` (alias `ntfy`): POST to an ntfy topic URL or any UnifiedPush endpoint, with
  ntfy's Title/Priority/Tags/Click headers and an optional access token (the channel secret).
- `webhook`: POST a JSON envelope; with a secret, signed like inbound hooks (AUTOMATION.md §3.6):
  `X-OneMind-Timestamp` and `X-OneMind-Signature: sha256=<HMAC(secret, timestamp + "." + body)>`.
- `email`: SMTP with STARTTLS (default) or implicit TLS; plain SMTP only to a loopback relay.
- push devices (`/v1/push/registrations`, platform `webpush` or `unifiedpush`): RFC 8291
  encrypted, VAPID-signed. The payload is only `{notification_id, box_id}`: the device fetches
  the text from the box (D-005), so the push service learns nothing but size and timing.

Content levels are enforced here, in the sender, so no routing mistake can leak a body:
`opaque` = "OneMind: new notification" only; `title` = title and severity; `full` = title, body, link.
Nothing here logs a secret, an endpoint or a message body.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import smtplib
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.parse import urlsplit

from . import crypto
from .crypto import Vapid

CHANNEL_KINDS = ("unifiedpush", "webhook", "email")
KIND_ALIASES = {"ntfy": "unifiedpush"}
LEVELS = ("opaque", "title", "full")
DEFAULT_LEVEL = {"unifiedpush": "title", "webhook": "full", "email": "title"}
DEVICE_PLATFORMS = ("webpush", "unifiedpush")
OPAQUE_TITLE = "OneMind: new notification"
PRIORITY = {"info": "3", "warning": "4", "critical": "5"}
MAX_RESPONSE = 64 * 1024


class DeliveryError(Exception):
    """A send failed. The message is short and safe to store (no secrets, no bodies)."""


@dataclass(frozen=True)
class Message:
    id: str
    severity: str
    topic: str
    title: str
    body: str
    link: str | None
    created_at: str
    box_id: str
    count: int = 1          # > 1 for a summary of held items


def render(level: str, msg: Message) -> tuple[str, str, str | None]:
    """(title, body, link) as this content level allows."""
    if level == "opaque":
        return OPAQUE_TITLE, "", None
    title = f"[{msg.severity}] {msg.title}"
    if level == "title":
        return title, "", None
    return title, msg.body, msg.link


# ---- outbound address checks (a channel is a way out of the box) ---------------------------

def _addresses(host: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        raise DeliveryError(f"cannot resolve host ({exc.__class__.__name__})") from None
    return [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]


def check_host(host: str | None, lan_ok: bool) -> None:
    """Refuse link-local (cloud metadata), multicast and unspecified addresses always; private and
    loopback addresses unless the channel was added by an owner (`lan_ok`)."""
    if not host:
        raise DeliveryError("no host")
    for addr in _addresses(host):
        if addr.is_link_local or addr.is_multicast or addr.is_unspecified or addr.is_reserved:
            raise DeliveryError("destination address is not allowed")
        if not lan_ok and (addr.is_private or addr.is_loopback):
            raise DeliveryError("destination is on the local network; only an owner may add such a channel")


def check_url(url: str, lan_ok: bool) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise DeliveryError("URL must be http:// or https://")
    if parts.username or parts.password:
        raise DeliveryError("credentials in the URL are not allowed; use the channel secret")
    if not lan_ok and parts.scheme != "https":
        raise DeliveryError("only an owner may add a plain http:// destination")
    check_host(parts.hostname, lan_ok)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a redirect could point inside the box
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_post(url: str, body: bytes, headers: dict[str, str], timeout: float, lan_ok: bool) -> int:
    check_url(url, lan_ok)
    req = urllib.request.Request(url, data=body, method="POST", headers={"User-Agent": "onemind-notify/1", **headers})
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            resp.read(MAX_RESPONSE)
            return resp.status
    except urllib.error.HTTPError as exc:
        raise DeliveryError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise DeliveryError(f"connection failed ({reason.__class__.__name__})") from None


# ---- channel kinds -----------------------------------------------------------------------

def validate_config(kind: str, config: object) -> dict:
    """Normalised config for a channel kind, or ValueError. Secrets are never part of config."""
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    def s(key: str, required: bool = True, limit: int = 500) -> str | None:
        v = config.get(key)
        if v is None and not required:
            return None
        if not isinstance(v, str) or not v.strip() or len(v) > limit:
            raise ValueError(f"config.{key} must be a non-empty string")
        return v.strip()
    if kind in ("unifiedpush", "webhook"):
        url = s("url")
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise ValueError("config.url must be an http(s) URL without credentials")
        return {"url": url}
    if kind == "email":
        security = config.get("security", "starttls")
        if security not in ("starttls", "tls", "none"):
            raise ValueError("config.security must be starttls, tls or none")
        port = config.get("port", 465 if security == "tls" else 587)
        if not isinstance(port, int) or not 0 < port < 65536:
            raise ValueError("config.port must be a TCP port")
        out = {"host": s("host", limit=253), "port": port, "security": security,
               "from": s("from", limit=254), "to": s("to", limit=254)}
        user = s("username", required=False, limit=254)
        if user:
            out["username"] = user
        for key in ("from", "to"):
            if "@" not in out[key] or "\n" in out[key] or "\r" in out[key]:
                raise ValueError(f"config.{key} must be an address")
        return out
    raise ValueError(f"kind must be one of {CHANNEL_KINDS} (or ntfy)")


def send_channel(kind: str, config: dict, secret: str | None, level: str, msg: Message,
                 *, timeout: float, lan_ok: bool, now_s: int) -> None:
    if kind == "unifiedpush":
        _send_ntfy(config, secret, level, msg, timeout, lan_ok)
    elif kind == "webhook":
        _send_webhook(config, secret, level, msg, timeout, lan_ok, now_s)
    elif kind == "email":
        _send_email(config, secret, level, msg, timeout, lan_ok)
    else:
        raise DeliveryError(f"unsupported channel kind {kind}")


def _latin1(text: str) -> str:
    # HTTP header values are latin-1; ntfy also accepts RFC 2047, but plain replacement is enough.
    return text.encode("latin-1", "replace").decode("latin-1").replace("\r", " ").replace("\n", " ")[:250]


def _send_ntfy(config: dict, secret: str | None, level: str, msg: Message, timeout: float, lan_ok: bool) -> None:
    title, body, link = render(level, msg)
    headers = {"Title": _latin1(title), "Priority": PRIORITY.get(msg.severity, "3"),
               "Tags": f"onemind,{msg.severity}", "Content-Type": "text/plain; charset=utf-8"}
    if link:
        headers["Click"] = _latin1(link)
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    text = body or title
    if msg.count > 1 and level != "opaque":
        text = f"{msg.count} notifications. {text}"
    http_post(config["url"], text.encode("utf-8"), headers, timeout, lan_ok)


def webhook_signature(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def _send_webhook(config: dict, secret: str | None, level: str, msg: Message, timeout: float,
                  lan_ok: bool, now_s: int) -> None:
    title, body, link = render(level, msg)
    doc = {"schema": "onemind.notification/v1", "id": msg.id, "box_id": msg.box_id,
           "severity": msg.severity if level != "opaque" else None,
           "topic": msg.topic if level != "opaque" else None,
           "title": title, "created_at": msg.created_at, "count": msg.count}
    if level == "full":
        doc.update(body=body, link=link)
    raw = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        ts = str(now_s)
        headers["X-OneMind-Timestamp"] = ts
        headers["X-OneMind-Signature"] = webhook_signature(secret, ts, raw)
    http_post(config["url"], raw, headers, timeout, lan_ok)


def _send_email(config: dict, secret: str | None, level: str, msg: Message, timeout: float, lan_ok: bool) -> None:
    host, port, security = config["host"], config["port"], config["security"]
    check_host(host, lan_ok)
    if security == "none" and not all(a.is_loopback for a in _addresses(host)):
        raise DeliveryError("plain SMTP is allowed only to a relay on this machine")
    title, body, link = render(level, msg)
    em = EmailMessage()
    em["Subject"] = title.replace("\n", " ")[:200]
    em["From"] = config["from"]
    em["To"] = config["to"]
    text = body or title
    if link:
        text += f"\n\n{link}"
    if msg.count > 1:
        text = f"{msg.count} notifications while you were away.\n\n{text}"
    em.set_content(text + "\n\n-- \nSent by your OneMind box. Change this in Settings > Notifications.\n")
    ctx = ssl.create_default_context()
    try:
        if security == "tls":
            client = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx)
        else:
            client = smtplib.SMTP(host, port, timeout=timeout)
        with client:
            client.ehlo()
            if security == "starttls":
                client.starttls(context=ctx)
                client.ehlo()
            if config.get("username") and secret:
                client.login(config["username"], secret)
            client.send_message(em)
    except smtplib.SMTPResponseException as exc:
        raise DeliveryError(f"SMTP {exc.smtp_code}") from None
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise DeliveryError(f"SMTP failed ({exc.__class__.__name__})") from None


# ---- push devices ------------------------------------------------------------------------

def validate_device(platform: str, endpoint: object, keys: object) -> tuple[str, dict | None]:
    if platform == "apns":
        raise ValueError("apns needs the iOS relay (CORE-NOTIFY-4), which is not built yet")
    if platform not in DEVICE_PLATFORMS:
        raise ValueError(f"platform must be one of {DEVICE_PLATFORMS}")
    if not isinstance(endpoint, str) or len(endpoint) > 2000:
        raise ValueError("endpoint must be a URL")
    parts = urlsplit(endpoint)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("endpoint must be an http(s) URL without credentials")
    if keys is None:
        if platform == "webpush":
            raise ValueError("webpush needs keys {p256dh, auth}")
        return endpoint, None
    if not isinstance(keys, dict) or not isinstance(keys.get("p256dh"), str) or not isinstance(keys.get("auth"), str):
        raise ValueError("keys must be {p256dh, auth} (base64url)")
    try:
        crypto.encrypt_aes128gcm(b"{}", keys["p256dh"], keys["auth"])
    except (ValueError, TypeError):
        raise ValueError("keys are not a valid P-256 subscription") from None
    return endpoint, {"p256dh": keys["p256dh"], "auth": keys["auth"]}


def push_payload(msg: Message) -> bytes:
    return json.dumps({"notification_id": msg.id, "box_id": msg.box_id}, separators=(",", ":")).encode()


def send_push(endpoint: str, keys: dict | None, vapid: Vapid, subject: str, msg: Message,
              *, timeout: float, lan_ok: bool, now_s: int) -> None:
    payload = push_payload(msg)
    headers = {"TTL": "86400", "Urgency": "high" if msg.severity == "critical" else "normal"}
    if keys is None:  # UnifiedPush distributor without Web Push keys: still ids only
        headers["Content-Type"] = "application/json"
        http_post(endpoint, payload, headers, timeout, lan_ok)
        return
    body = crypto.encrypt_aes128gcm(payload, keys["p256dh"], keys["auth"])
    headers.update({"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                    "Authorization": vapid.authorization(endpoint, subject, now_s)})
    http_post(endpoint, body, headers, timeout, lan_ok)
