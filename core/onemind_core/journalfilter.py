# SPDX-License-Identifier: Apache-2.0
"""Redaction for the whole-system journal (P-07).

The app-log filter (monitoring/redact.py) handles tokens, passwords, PEM blocks, e-mail and IP addresses.
The system journal also carries things an app log rarely does: WireGuard and age keys, NATS seeds, SSH key
fingerprints a person may not want pasted into a chat, and MAC addresses. This adds those rules on top of
the same stateful `Redactor`, so a private key printed over many lines stays hidden and line counts stay
true (a line is replaced, never dropped). Like the base filter it is a safety net, not a guarantee.
"""

from __future__ import annotations

import re

from .monitoring.redact import R, Redactor

_EXTRA: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bAGE-SECRET-KEY-1[A-Z0-9]{20,}"), R),
    # A NATS seed (S + account/user/operator type letter + 54 base32 characters).
    (re.compile(r"\bS[ACNOPUX][A-Z2-7]{54}\b"), R),
    # A WireGuard or other 32-byte base64 key: 43 base64 characters and one '='.
    (re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43}=(?![A-Za-z0-9+/=])"), R),
    (re.compile(r"\bSHA256:[A-Za-z0-9+/]{43}\b"), "SHA256:" + R),
    (re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"), "[mac]"),
]


class JournalRedactor(Redactor):
    """Redactor plus the journal rules; `line()` is the only entry point."""

    def line(self, text: str) -> str:
        out = super().line(text)
        if out == R:
            return out
        for pattern, repl in _EXTRA:
            out = pattern.sub(repl, out)
        return out
