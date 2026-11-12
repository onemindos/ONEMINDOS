# SPDX-License-Identifier: Apache-2.0
"""Untrusted-text marking for MCP results (docs/leap/dev/MCP.md §6.1, DEV-MCP-5).

Text written by third parties (app names and descriptions from manifests, node hostnames,
reasons an agent wrote into the audit log) reaches the model. For each tool result or resource:

1. control characters and Unicode bidi overrides are stripped and the value is length-capped,
   in `structuredContent` and in the text alike;
2. `_meta["onemind/untrusted"]` lists the concrete JSON paths that hold untrusted text;
3. the text `content` wraps each such value as `<untrusted source="...">...</untrusted>`, with any
   `<untrusted` / `</untrusted` inside the value escaped so it cannot close its own wrapper.

Marking helps a well-behaved model; what actually holds is that an agent can only *request*.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from typing import Any

META_KEY = "onemind/untrusted"
# C0/C1 controls except tab and newline, plus the bidi embedding/override/isolate characters.
_STRIP = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩‎‏؜]")
_OPEN = re.compile(r"<(/?)untrusted", re.IGNORECASE)
CAPS = {"name": 80, "title": 80, "hostname": 80, "description": 500, "reason": 500, "message": 500}
DEFAULT_CAP = 500


def clean(value: str, field: str = "") -> str:
    value = _STRIP.sub("", unicodedata.normalize("NFC", value))
    cap = CAPS.get(field, DEFAULT_CAP)
    return value if len(value) <= cap else value[: cap - 1] + "…"


def escape(value: str) -> str:
    return _OPEN.sub(lambda m: "&lt;" + m.group(0)[1:], value)


def wrap(value: str, source: str) -> str:
    return f'<untrusted source="{escape(source).replace(chr(34), "")}">{escape(value)}</untrusted>'


def _walk(node: Any, pattern: list[str], path: str, found: list[tuple[str, list]]):
    """Resolve a pattern like ["apps", "*", "description"]; collect (path, container/key)."""
    if not pattern:
        return
    head, rest = pattern[0], pattern[1:]
    if head == "*":
        if isinstance(node, list):
            for i, item in enumerate(node):
                if rest:
                    _walk(item, rest, f"{path}[{i}]", found)
                elif isinstance(item, str):
                    found.append((f"{path}[{i}]", [node, i]))
        elif isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else k
                if rest:
                    _walk(v, rest, p, found)
                elif isinstance(v, str):
                    found.append((p, [node, k]))
        return
    if isinstance(node, dict) and head in node:
        p = f"{path}.{head}" if path else head
        if rest:
            _walk(node[head], rest, p, found)
        elif isinstance(node[head], str):
            found.append((p, [node, head]))


def mark(structured: dict, patterns: list[str], source_of=None) -> tuple[dict, str, list[str]]:
    """Return (cleaned structured, text with wrappers, untrusted paths).

    `patterns` use dots and `*` for any list item or key, e.g. "apps.*.description".
    `source_of(path)` names the source for the wrapper; by default the path itself.
    """
    structured = copy.deepcopy(structured)
    found: list[tuple[str, list]] = []
    for pat in patterns:
        _walk(structured, pat.split("."), "", found)
    for path, (container, key) in found:
        container[key] = clean(container[key], path.rsplit(".", 1)[-1])
    shown = copy.deepcopy(structured)
    found_shown: list[tuple[str, list]] = []
    for pat in patterns:
        _walk(shown, pat.split("."), "", found_shown)
    for path, (container, key) in found_shown:
        container[key] = wrap(container[key], source_of(path) if source_of else path)
    text = json.dumps(shown, separators=(",", ":"), ensure_ascii=False)
    return structured, text, sorted({p for p, _ in found})
