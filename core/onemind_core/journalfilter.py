# SPDX-License-Identifier: Apache-2.0
"""Redaction for the whole-system journal (P-07).

The app-log filter (monitoring/redact.py) handles tokens, passwords, PEM blocks, e-mail and IP addresses.
The system journal also carries things an app log rarely does: WireGuard and age keys, NATS seeds, SSH key
fingerprints a person may not want pasted into a chat, and MAC addresses. This adds those rules on top of
the same stateful `Redactor`, so a private key printed over many lines stays hidden and line counts stay
true (a line is replaced, never dropped). Like the base filter it is a safety net, not a guarantee.
"""

from __future__ import annotations

import ipaddress
import re

from .monitoring.redact import MAX_LINE, R, Redactor

_EXTRA: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bAGE-SECRET-KEY-1[A-Z0-9]{20,}"), R),
    # A NATS seed (S + account/user/operator type letter + 54 base32 characters).
    (re.compile(r"\bS[ACNOPUX][A-Z2-7]{54}\b"), R),
    # A WireGuard or other 32-byte base64 key: 43 base64 characters and one '='.
    (re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43}=(?![A-Za-z0-9+/=])"), R),
    # Not `\b` at the end: a fingerprint may end in '+' or '/', which is not a word character.
    (re.compile(r"\bSHA256:[A-Za-z0-9+/]{43}(?![A-Za-z0-9+/])"), "SHA256:" + R),
    (re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"), "[mac]"),
]

# An IPv6 candidate: groups of hex and colons (so "::" and "2001:db8::44" both fit), an optional IPv4 tail
# ("::ffff:192.0.2.1") and an optional zone ("fe80::1%eth0"). A candidate is only masked when `ipaddress`
# agrees it is an address, so a clock such as 10:00:01 or a MAC address is left to its own rule.
_V6 = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}(?:[0-9A-Fa-f]{1,4}|(?:\d{1,3}\.){3}\d{1,3})?(?:%[\w.-]+)?(?![\w:])")


def _mask_ipv6(text: str) -> str:
    def repl(m: re.Match) -> str:
        try:
            ipaddress.IPv6Address(m.group(0))
        except ValueError:
            return m.group(0)
        return "[ip]"

    return _V6.sub(repl, text)


class JournalRedactor(Redactor):
    """Redactor plus the journal rules; `line()` is the only entry point."""

    def line(self, text: str) -> str:
        # IPv6 first, so an IPv4-mapped address is masked whole rather than as "::ffff:[ip]".
        out = super().line(_mask_ipv6(text[:MAX_LINE]))
        if out == R:
            return out
        for pattern, repl in _EXTRA:
            out = pattern.sub(repl, out)
        return out
