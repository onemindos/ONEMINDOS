# SPDX-License-Identifier: Apache-2.0
"""Redact app log lines before they leave the box's API (contract §12.15 logs).

Apps print secrets by accident: tokens in request logs, passwords in config dumps, private keys
in stack traces. Logs are shown to owners, adults and (with a grant) agents, so every line is
passed through `Redactor` first. It replaces, never drops, so line counts stay true:

- `Authorization: Bearer|Basic <x>`, `key=value` / `"key": "value"` pairs whose key names a
  secret (password, token, secret, api_key, ...), URL credentials (`scheme://user:pass@`);
- JWTs, OneMind tokens (`om_pat_…`), AWS access key ids, PEM private-key blocks (stateful,
  across lines);
- e-mail addresses and IPv4 addresses (personal data the owner may not want an agent to read).

It is a safety net, not a guarantee: an app that logs a secret under an innocent name is not
caught. Each line is also cut to 4096 characters.
"""

from __future__ import annotations

import re

MAX_LINE = 4096
R = "[redacted]"

_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\b(authorization\s*[:=]\s*(?:bearer|basic|token)\s+)[^\s\"',;]+"), r"\1" + R),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1" + R),
    (re.compile(
        r"(?i)([\"']?\b[\w.-]*(?:passw(?:or)?d|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key"
        r"|private[_-]?key|client[_-]?secret|credential|session[_-]?id|cookie)[\w.-]*[\"']?\s*[:=]\s*[\"']?)"
        r"[^\s\"',;&}]+"), r"\1" + R),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@"), r"\1" + R + "@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}"), R),
    (re.compile(r"\bom_(?:pat|agt|plg|nod|aut)_[A-Za-z0-9_-]{8,}"), R),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), R),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[ip]"),
]
_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_PEM_END = re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")


class Redactor:
    def __init__(self):
        self._in_pem = False

    def line(self, text: str) -> str:
        text = text[:MAX_LINE]
        if self._in_pem:
            if _PEM_END.search(text):
                self._in_pem = False
            return R
        if _PEM_BEGIN.search(text):
            self._in_pem = not _PEM_END.search(text)
            return _PEM_BEGIN.split(text, 1)[0] + R
        for rx, repl in _RULES:
            text = rx.sub(repl, text)
        return text


def redact_lines(lines: list[str]) -> list[str]:
    r = Redactor()
    return [r.line(x) for x in lines]
