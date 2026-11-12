# SPDX-License-Identifier: Apache-2.0
"""App logs (contract §12.22 and §12.15, PD-08): a bounded, redacted tail per container.

Bounds: at most 2000 lines per request (default 200), 1 MiB of body, 4 KiB per line, and a
kubectl timeout. Every line passes through `redact()`, which masks the credential shapes apps
commonly print. Redaction is a safety net, not a guarantee: an app that logs its own secrets in
an unknown shape still leaks them, which is why logs are for people with role owner or adult
only, and every read is audited.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .kube import Kube, KubeError

DEFAULT_TAIL = 200
MAX_TAIL = 2000
MAX_BYTES = 1024 * 1024
MAX_LINE = 4096
MAX_PODS_JSON = 4 * 1024 * 1024
COMPONENT_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
POD_RE = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
_KEY_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_KEY_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY-----")
REDACTED = "[redacted]"

# (name, pattern, replacement). Order matters: whole-token shapes before key=value pairs.
_RULES: list[tuple[str, re.Pattern, str]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(-----END [A-Z0-9 ]*PRIVATE KEY-----|$)"),
     REDACTED),
    ("bearer", re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    ("basic-auth", re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{8,}"), "Basic " + REDACTED),
    ("onemind-token", re.compile(r"\bom_(pat|agt|plg|nod|aut)_[A-Za-z0-9_-]{8,}"), REDACTED),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"), REDACTED),
    ("github", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"), REDACTED),
    ("gitlab", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), REDACTED),
    ("slack", re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{10,}"), REDACTED),
    ("aws-key-id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), REDACTED),
    ("stripe", re.compile(r"\b[rs]k_(live|test)_[A-Za-z0-9]{16,}"), REDACTED),
    ("openai-like", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), REDACTED),
    ("url-userinfo", re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+):[^\s@/]+@"), r"\1:" + REDACTED + "@"),
    ("key-value", re.compile(
        r"(?i)\b([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|"
        r"private[_-]?key|client[_-]?secret|auth|credential|session)[A-Za-z0-9_.-]*)"
        r"(\"?\s*[:=]\s*\"?)(?!(?i:bearer|basic)\b)(?!\[redacted\])([^\s\"',;&}]{3,})"
    ), r"\1\2" + REDACTED),
]


def redact(line: str) -> tuple[str, int]:
    """The line with known credential shapes replaced, and how many replacements were made."""
    total = 0
    for _, pattern, repl in _RULES:
        line, n = pattern.subn(repl, line)
        total += n
    return line, total


class Redactor:
    """Line redaction plus one piece of state: inside a PEM private key block every line is masked
    until its END line (a key printed over several log lines must not leak line by line)."""

    def __init__(self) -> None:
        self._in_key: set[str] = set()

    def __call__(self, label: str, line: str) -> tuple[str, int]:
        if label in self._in_key:
            if _KEY_END.search(line):
                self._in_key.discard(label)
            return REDACTED, 1
        if _KEY_BEGIN.search(line) and not _KEY_END.search(line):
            self._in_key.add(label)
        return redact(line)


def clip(line: str) -> str:
    return line if len(line) <= MAX_LINE else line[:MAX_LINE] + " …[cut]"


@dataclass
class LogResult:
    lines: list[str]
    redactions: int
    truncated: bool
    containers: list[str]

    def text(self) -> str:
        return "".join(line + "\n" for line in self.lines)


class LogSource(Protocol):
    name: str

    def read(self, namespace: str, component: str | None, tail: int, since: datetime | None) -> list[tuple[str, str]]:
        """[(pod/container label, raw line)] oldest first per container."""


class NoopLogSource:
    """The noop executor runs nothing, so there is nothing to read."""

    name = "noop"

    def read(self, namespace, component, tail, since):
        return []


class KubectlLogSource:
    name = "kubernetes"

    def __init__(self, kube: Kube):
        self.kube = kube

    def containers(self, namespace: str) -> list[tuple[str, str]]:
        out = self.kube.run(["get", "pods", "-n", namespace, "-o", "json"])
        if len(out) > MAX_PODS_JSON:
            raise KubeError("pod list too large")
        pairs = []
        for pod in (json.loads(out or "{}").get("items") or [])[:50]:
            name = (pod.get("metadata") or {}).get("name")
            if not isinstance(name, str) or not POD_RE.match(name):
                continue
            for c in ((pod.get("spec") or {}).get("containers") or []):
                cname = c.get("name") if isinstance(c, dict) else None
                if isinstance(cname, str) and COMPONENT_RE.match(cname):
                    pairs.append((name, cname))
        return pairs

    def read(self, namespace, component, tail, since):
        pairs = [(p, c) for p, c in self.containers(namespace) if component is None or c == component]
        lines: list[tuple[str, str]] = []
        for pod, container in pairs[:20]:
            args = ["logs", "-n", namespace, pod, "-c", container, f"--tail={tail}", "--timestamps",
                    f"--limit-bytes={MAX_BYTES}"]
            if since is not None:
                args.append("--since-time=" + since.isoformat().replace("+00:00", "Z"))
            text = self.kube.run(args)
            lines += [(f"{pod}/{container}", raw) for raw in text.splitlines()]
        return lines


def collect(source: LogSource, namespace: str, component: str | None, tail: int,
            since: datetime | None) -> LogResult:
    raw = source.read(namespace, component, tail, since)
    labels = sorted({label for label, _ in raw})
    prefix = component is None
    out: list[str] = []
    redactions, size, truncated = 0, 0, False
    redactor = Redactor()
    for label, line in raw[-MAX_TAIL:] if len(raw) > MAX_TAIL else raw:
        clean, n = redactor(label, clip(line))
        redactions += n
        text = f"{label} {clean}" if prefix else clean
        size += len(text.encode()) + 1
        if size > MAX_BYTES:
            truncated = True
            break
        out.append(text)
    truncated = truncated or len(raw) > MAX_TAIL
    return LogResult(out, redactions, truncated, labels)


def parse_since(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("since needs a timezone (RFC 3339)")
    return ts


def components(pairs: Iterable[tuple[str, str]]) -> list[str]:
    return sorted({c for _, c in pairs})
