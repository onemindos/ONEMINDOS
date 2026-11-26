#!/usr/bin/env -S python3 -I
# SPDX-License-Identifier: Apache-2.0
"""Surface parity ratchet: the gateway API and the screens and commands people use stay 1:1 (#1232).

The committed spec sdk/openapi/onemind-v1.json is the API contract. For every operation in it, this
finds who calls it on each surface people use:

  dashboard  dashboard/src and the design system ui/src (the dashboard renders both)
  cli        the `onemind` command, cmd/onemind/cli and the repo's internal/ packages it imports
  mobile     the phone app, mobile/src

and checks three rules (BUILDER-BRIEFING item 6):

  1. every operation has a dashboard caller;
  2. every operation that changes something (POST, PUT, PATCH, DELETE) has a CLI caller;
  3. every operation in the phone's 1.0 scope (the `mobile-scope` lines of exemptions.txt) has a
     mobile caller;

unless exemptions.txt lists it for that surface, under a group with a written reason and an owner
issue. The test (test/unit/test_surface_parity.py) fails on a missing caller that is not exempt, and
on an exemption that is stale: the caller now exists, or the operation is gone. So the list can only
shrink, the same ratchet as AWAITING_TOOL in core/onemind_core/surfaces/parity.py and
sdk/tools/openapi-lint/baseline.txt. HEAD and OPTIONS (the upload protocol's probes) are not checked,
as in surfaces/parity.py.

How a caller is found (by operation, not by path alone):
  - an SDK method: the hand-written methods of @onemind/sdk (sdk/ts/src) and the Go SDK (sdk/go)
    are mapped to the operation each calls, and a surface that calls `.domains.list(` or
    `.Actions.Approve(` calls that operation. (The generated SDK code is types only: openapi-typescript
    keys `operations` by operationId, oapi-codegen makes models. There is no generated method per
    operation to search for, so the operationId is the name this tool reports.)
  - a direct call: a path literal in a surface file (`req('POST', '/v1/tokens')`,
    `c.Do(ctx, http.MethodGet, "/v1/x/"+id, ...)`, `fmt.Sprintf("/v1/apps/%s", id)`), with the HTTP
    method read from the enclosing call.
  - a path-only literal: a path whose method cannot be read (a path kept in a table and sent
    elsewhere). It is NOT a caller by itself, because it would stand for every method on that path
    (a new DELETE next to a known GET would pass unseen). It counts only for the operations named in
    an `indirect <surface> <operationId> <reason>` line of exemptions.txt, and that line goes stale
    when a method-aware caller appears or the path-only literal disappears.
  Comments, tests, mocks and fixtures are not callers, and neither is a path literal that is only
  compared (`location !== `/v1/files/uploads/${id}``).

Run with: python3 -I sdk/tools/surface-parity [--report] [--print-exemptions]
Exit codes: 0 clean, 1 a rule failed, 2 an input cannot be read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SPEC = REPO_ROOT / "sdk" / "openapi" / "onemind-v1.json"
EXEMPTIONS = HERE / "exemptions.txt"

SURFACES = ("dashboard", "cli", "mobile")
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Where each surface's code lives, relative to the repo root, and the file types read.
SOURCES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "dashboard": (("dashboard/src", (".ts", ".tsx")), ("ui/src", (".ts", ".tsx"))),
    "cli": (("cmd/onemind/cli", (".go",)),),
    "mobile": (("mobile/src", (".ts", ".tsx")),),
}
SDK_TS = ("sdk/ts/src/client.ts",)
SDK_GO_DIR = "sdk/go"

# SDK methods whose path is built at run time (a verb, a route argument or a path kept in a
# variable), so the routes each one calls are named here. They replace what the scan reads.
SDK_OVERRIDES: dict[str, dict[str, tuple[tuple[str, str], ...]]] = {
    "ts": {
        "actions.approve": (("POST", "/v1/actions/{action_id}/approve"),),
        "actions.deny": (("POST", "/v1/actions/{action_id}/deny"),),
        "events.subscribe": (("GET", "/v1/events"),),
        "events.subscribeShared": (("GET", "/v1/events"),),
        "events.subscribeDashboardCard": (("GET", "/v1/me/dashboard-card/events"),),
    },
    "go": {
        "Actions.Approve": (("POST", "/v1/actions/{action_id}/approve"),),
        "Actions.ApproveAcceptingLicence": (("POST", "/v1/actions/{action_id}/approve"),),
        "Actions.ApproveBound": (("POST", "/v1/actions/{action_id}/approve"),),
        "Actions.Deny": (("POST", "/v1/actions/{action_id}/deny"),),
        "Events.Subscribe": (("GET", "/v1/events"),),
        "Work.Complete": (("GET", "/v1/work/projects/{project_id}/tasks/{task_id}"),
                          ("PATCH", "/v1/work/projects/{project_id}/tasks/{task_id}")),
    },
}


class InputError(Exception):
    pass


# ---- the spec --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Operation:
    op_id: str
    method: str
    path: str
    tags: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


def load_operations(spec_path: Path = SPEC) -> list[Operation]:
    try:
        doc = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"cannot read the spec {spec_path}: {e}") from e
    ops: list[Operation] = []
    for path, item in doc.get("paths", {}).items():
        for method, op in item.items():
            if method.upper() not in HTTP_METHODS:
                continue
            op_id = op.get("operationId")
            if not op_id:
                raise InputError(f"{method.upper()} {path} has no operationId")
            ops.append(Operation(op_id, method.upper(), path, tuple(op.get("tags", ()))))
    return ops


MobileScope = dict  # OpenAPI tag -> path prefixes (empty: the whole tag); from `mobile-scope` lines


def in_mobile_scope(op: Operation, scope: MobileScope) -> bool:
    for tag in op.tags:
        if tag in scope:
            prefixes = scope[tag]
            if not prefixes or any(op.path == p or op.path.startswith(p + "/") for p in prefixes):
                return True
    return False


def required_surfaces(op: Operation, scope: MobileScope) -> list[str]:
    out = ["dashboard"]
    if op.method in WRITE_METHODS:
        out.append("cli")
    if in_mobile_scope(op, scope):
        out.append("mobile")
    return out


# ---- reading source text ---------------------------------------------------------------------------
def strip_comments(text: str, go: bool = False) -> str:
    """Blank out // and /* */ comments (same length, newlines kept); strings stay as they are."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt in "/*":
            j = (text.find("\n", i) if nxt == "/" else text.find("*/", i + 2))
            j = n if j < 0 else (j if nxt == "/" else j + 2)
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "'\"`":
            i = _skip_string(text, i, go)
        else:
            i += 1
    return "".join(out)


def _skip_string(text: str, i: int, go: bool) -> int:
    q = text[i]
    n = len(text)
    j = i + 1
    if q == "`" and go:  # Go raw string: no escapes
        k = text.find("`", j)
        return n if k < 0 else k + 1
    if q == "`":
        return _skip_template_rest(text, j)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == q or text[j] == "\n":
            return j + 1
        j += 1
    return n


def _skip_template_rest(text: str, j: int) -> int:
    """From inside a TS template literal, the index just after its closing backtick."""
    n = len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            return j + 1
        if c == "$" and j + 1 < n and text[j + 1] == "{":
            j = _skip_braces(text, j + 1)
            continue
        j += 1
    return n


def _skip_braces(text: str, j: int) -> int:
    """text[j] == '{': the index just after its matching '}' (strings inside are skipped)."""
    n = len(text)
    depth = 0
    while j < n:
        c = text[j]
        if c in "'\"`":
            j = _skip_string(text, j, False)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


DYN = "\x00"  # a part of a path that is only known at run time


def read_literal(text: str, i: int, go: bool) -> tuple[str, int]:
    """The string literal starting at text[i] (a quote), with every interpolation as DYN, and its end."""
    q = text[i]
    n = len(text)
    j = i + 1
    buf: list[str] = []
    while j < n:
        c = text[j]
        if c == "\\" and not (go and q == "`"):
            buf.append(text[j + 1] if j + 1 < n else "")
            j += 2
            continue
        if c == q:
            return "".join(buf), j + 1
        if q == "`" and not go and c == "$" and j + 1 < n and text[j + 1] == "{":
            j = _skip_braces(text, j + 1)
            buf.append(DYN)
            continue
        if c == "\n" and q != "`":
            break
        buf.append(c)
        j += 1
    return "".join(buf), j


def _expr_end(text: str, j: int) -> int:
    """End of one operand of `+`: the next `+`, `,`, `)`, `]`, `}`, `;` or newline at depth 0."""
    n = len(text)
    depth = 0
    while j < n:
        c = text[j]
        if c in "'\"`":
            j = _skip_string(text, j, False)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return j
            depth -= 1
        elif depth == 0 and c in "+,;\n":
            return j
        j += 1
    return n


def read_concat(text: str, i: int, go: bool) -> tuple[str, int]:
    """A literal plus whatever is joined to it with `+` (literals kept, expressions as DYN)."""
    s, j = read_literal(text, i, go)
    n = len(text)
    while True:
        k = j
        while k < n and text[k] in " \t":
            k += 1
        if k >= n or text[k] != "+":
            return s, j
        k += 1
        while k < n and text[k] in " \t\n":
            k += 1
        if k < n and text[k] in "'\"`":
            more, j = read_literal(text, k, go)
            s += more
        else:
            j = _expr_end(text, k)
            if j == k:
                return s, j
            s += DYN


PRINTF = re.compile(r"%[-+# 0-9.]*[sdvqx]")


def normalise(raw: str) -> list[str] | None:
    """A called path as segments, a run-time part as '{}'; None when it is not an API path."""
    s = PRINTF.sub(DYN, raw)
    s = s.split("?", 1)[0].split("#", 1)[0]
    if s.startswith(DYN + "/"):
        s = s[1:]  # `${hub}/v1/...`: the hub's base URL
    if not s.startswith("/"):
        return None
    segs = s.split("/")[1:]
    if segs and segs[-1] == "":
        segs = segs[:-1]
    out: list[str] = []
    for idx, seg in enumerate(segs):
        if seg == DYN or (seg.startswith("{") and seg.endswith("}")) or (DYN in seg and seg.startswith(DYN)):
            out.append("{}")
        elif DYN in seg:
            # `/v1/alerts${query}`: a run-time suffix glued to the last word is a query string.
            if idx == len(segs) - 1:
                out.append(seg.split(DYN, 1)[0])
            else:
                out.append("{}")
        else:
            out.append(seg)
    return out


# ---- the HTTP method of one call -------------------------------------------------------------------
METHOD_TOKEN = re.compile(r"""(?:['"](GET|POST|PUT|PATCH|DELETE)['"])|(?:http\.Method(Get|Post|Put|Patch|Delete)\b)""", re.I)
GET_HELPERS = re.compile(r"(?:^|[.\s(])(read|get|getBoth|getJSON|fetchJSON|readJSON|Get)\s*(?:<[^()]*>)?\s*$")


def enclosing_opens(text: str, pos: int, limit: int = 600) -> list[int]:
    """Indexes of the unmatched ( or { before pos, innermost first (stops at a ; at depth 0)."""
    opens: list[int] = []
    depth = 0
    i = pos - 1
    stop = max(0, pos - limit)
    while i >= stop:
        c = text[i]
        if c in ")}]":
            depth += 1
        elif c in "({[":
            if depth == 0:
                opens.append(i)
                if len(opens) >= 3:
                    break
            else:
                depth -= 1
        elif c == ";" and depth == 0:
            break
        i -= 1
    return opens


def matching_close(text: str, i: int) -> int:
    pair = {"(": ")", "{": "}", "[": "]"}[text[i]]
    depth = 0
    j = i
    n = len(text)
    while j < n:
        c = text[j]
        if c in "'\"`":
            j = _skip_string(text, j, False)
            continue
        if c == text[i]:
            depth += 1
        elif c == pair:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return n


def is_literal_brace(text: str, o: int) -> bool:
    """A `{` that opens an object or composite literal (`f({`, `key: {`, `request{`), not a body."""
    if o > 0 and (text[o - 1].isalnum() or text[o - 1] == "_"):
        return True  # Go composite literal: request{...}
    j = o - 1
    while j >= 0 and text[j] in " \t\n":
        j -= 1
    if j < 0:
        return False
    if text[j] == "=":  # `x = {` is an object; `=> {` is an arrow function's body
        return j == 0 or text[j - 1] not in ">="
    return text[j] in "(,:["


def method_of_call(text: str, start: int) -> str | None:
    """The HTTP method of the call the path literal at text[start] is an argument of, or None."""
    for o in enclosing_opens(text, start):
        if text[o] == "{" and not is_literal_brace(text, o):
            break  # a function or block body: the method is not in the call any more
        close = matching_close(text, o)
        args = text[o + 1:close]
        rel = start - (o + 1)
        # The method token nearest the path: the last one before it, else the first one after it.
        before_path = [m for m in METHOD_TOKEN.finditer(args) if m.start() < rel]
        m = before_path[-1] if before_path else METHOD_TOKEN.search(args, rel)
        if m:
            return (m.group(1) or m.group(2)).upper()
        before = text[max(0, o - 60):o]
        if text[o] == "(" and GET_HELPERS.search(before):
            return "GET"
    return None


# ---- matching a called path to the spec ------------------------------------------------------------
class Matcher:
    def __init__(self, ops: list[Operation]):
        self.by_path: dict[str, list[Operation]] = {}
        for op in ops:
            self.by_path.setdefault(op.path, []).append(op)
        self.templates = [(p, p.split("/")[1:]) for p in self.by_path]
        self.roots = {segs[0] for _, segs in self.templates if segs}

    def path_for(self, segs: list[str]) -> str | None:
        best, best_score = None, -1
        for path, tsegs in self.templates:
            if len(tsegs) != len(segs):
                continue
            score = 0
            for c, t in zip(segs, tsegs):
                tparam = t.startswith("{")
                if c == "{}":
                    if not tparam:
                        break
                elif tparam:
                    pass
                elif c == t:
                    score += 1
                else:
                    break
            else:
                if score > best_score:
                    best, best_score = path, score
        return best

    def ops_for(self, method: str | None, segs: list[str]) -> tuple[list[Operation], bool]:
        """The operations a call reaches, and whether the method was unknown (path-only)."""
        path = self.path_for(segs)
        if path is None:
            return [], False
        ops = self.by_path[path]
        if method is None:
            return list(ops), True
        return [op for op in ops if op.method == method], False


# ---- callers ---------------------------------------------------------------------------------------
@dataclass
class Caller:
    file: str
    how: str  # "call", "path-only" or "sdk:<method>"


@dataclass
class Scan:
    callers: dict[str, dict[str, list[Caller]]] = field(default_factory=dict)  # surface -> op_id -> callers

    def add(self, surface: str, op: Operation, caller: Caller) -> None:
        self.callers.setdefault(surface, {}).setdefault(op.op_id, []).append(caller)

    def has(self, surface: str, op_id: str) -> bool:
        """A method-aware caller: an SDK method or a call whose HTTP method was read."""
        return any(c.how != "path-only" for c in self.callers.get(surface, {}).get(op_id, ()))

    def path_only(self, surface: str, op_id: str) -> list[Caller]:
        """Literals of the operation's path whose HTTP method could not be read."""
        return [c for c in self.callers.get(surface, {}).get(op_id, ()) if c.how == "path-only"]


COMPARE_AFTER = re.compile(r"\s*[!=]==?")
COMPARE_BEFORE = re.compile(r"[!=]==?\s*$")


def is_comparison(text: str, start: int, end: int) -> bool:
    """The literal text[start:end] is an operand of ==, ===, != or !==: compared, not sent."""
    return bool(COMPARE_BEFORE.search(text[max(0, start - 8):start]) or COMPARE_AFTER.match(text, end))


def literal_calls(text: str, go: bool, matcher: Matcher):
    """Yield (method or None, path segments) for every API path literal in comment-free text."""
    roots = "|".join(sorted(re.escape(r) for r in matcher.roots))
    # A literal that starts with the path, or a template that starts with the hub URL: `${base}/v1/...`.
    for m in re.finditer(rf"""(?:(['"`])|`\$\{{[\w.]+\}})/(?:{roots})(?=[/'"`?$%]|\$\{{)""", text):
        i = m.start()
        raw, end = read_concat(text, i, go)
        if is_comparison(text, i, end):
            continue
        segs = normalise(raw)
        if segs is None:
            continue
        yield method_of_call(text, i), segs


def is_source(path: Path, exts: tuple[str, ...]) -> bool:
    name = path.name
    if not name.endswith(exts) or name.endswith(".d.ts"):
        return False
    if re.search(r"\.(test|spec)\.(ts|tsx)$", name) or name.endswith("_test.go"):
        return False
    stem = name.split(".", 1)[0].lower()
    if stem.startswith(("mock", "fixture")) or stem in {"fixtures", "testutil", "testing"}:
        return False
    parts = {p.lower() for p in path.parts}
    return not parts & {"test", "tests", "__tests__", "__mocks__", "testdata", "gen", "node_modules"}


GO_MODULE = "github.com/onemindos/onemindos/"


def surface_files(root: Path, surface: str):
    seen: set[Path] = set()
    for rel, exts in SOURCES[surface]:
        base = root / rel
        if not base.is_dir():
            raise InputError(f"{surface}: {base} is missing")
        for p in sorted(base.rglob("*")):
            if p.is_file() and is_source(p.relative_to(root), exts):
                seen.add(p)
                yield p
    if surface == "cli":
        # The repo's own internal/ packages the command imports call the gateway for it too
        # (`onemind fabric join` sends the join request through internal/fabric).
        pkgs: set[str] = set()
        for p in sorted(seen):
            pkgs.update(re.findall(r'"' + re.escape(GO_MODULE) + r'(internal/[\w/.-]+)"', p.read_text(encoding="utf-8")))
        for pkg in sorted(pkgs):
            for p in sorted((root / pkg).glob("*.go")):
                if p not in seen and is_source(p.relative_to(root), (".go",)):
                    seen.add(p)
                    yield p


def sdk_methods_ts(root: Path, matcher: Matcher) -> dict[str, list[Operation]]:
    """@onemind/sdk method chain (e.g. 'domains.list', 'instance.kiosk.set') -> the operations it calls."""
    out: dict[str, list[Operation]] = {}
    for rel in SDK_TS:
        text = strip_comments((root / rel).read_text(encoding="utf-8"))
        for m in re.finditer(r"""(['"`])/(?:v1|healthz)\b""", text):
            raw, _ = read_concat(text, m.start(), False)
            segs = normalise(raw)
            if segs is None:
                continue
            chain = ts_chain(text, m.start())
            if not chain:
                continue
            ops, _ = matcher.ops_for(method_of_call(text, m.start()), segs)
            out.setdefault(chain, []).extend(ops)
    for chain, routes in SDK_OVERRIDES["ts"].items():
        out[chain] = [op for method, path in routes for op in matcher.by_path.get(path, []) if op.method == method]
    return out


def ts_chain(text: str, pos: int) -> str | None:
    """The member chain of the SDK method a path literal sits in: 'readonly x = { y: { z: () => ...'."""
    keys: list[str] = []
    depth = 0
    i = pos - 1
    member = None
    while i >= 0:
        c = text[i]
        if c in ")}]":
            depth += 1
        elif c in "({[":
            if depth > 0:
                depth -= 1
            elif c == "{":
                head = text[max(0, i - 80):i]
                g = re.search(r"readonly\s+(\w+)\s*=\s*$", head)
                k = re.search(r"(\w+)\s*:\s*$", head)
                f = re.search(r"(?:async\s+)?(\w+)\s*\([^()]*\)\s*(?::[^{};]*)?$", head)
                if (g or k) and member is None:
                    # The innermost object of SDK methods: its last key before the literal is the method.
                    member = _last_key(text[i + 1:pos])
                if g:
                    keys.append(g.group(1))
                    break
                if k:
                    keys.append(k.group(1))
                elif (f and not keys and member is None and not head.rstrip().endswith("=>")
                      and f.group(1) not in {"if", "for", "while", "switch", "catch", "function", "async"}):
                    return f.group(1)  # a class method such as `async healthz() {`
        i -= 1
    else:
        return None
    if member is None:
        return None
    return ".".join(list(reversed(keys)) + [member])


def _last_key(body: str) -> str | None:
    """The last `key:` at depth 0 of an object literal body (strings and nested parts skipped)."""
    depth = 0
    last = None
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c in "'\"`":
            i = _skip_string(body, i, False)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0:
            m = re.match(r"(\w+)\s*:(?!:)", body[i:])
            if m and (i == 0 or not (body[i - 1].isalnum() or body[i - 1] == "_")):
                last = m.group(1)
                i += m.end()
                continue
        i += 1
    return last


def sdk_methods_go(root: Path, matcher: Matcher) -> dict[str, list[Operation]]:
    """Go SDK method chain (e.g. 'Actions.List', 'Healthz') -> the operations it calls."""
    out: dict[str, list[Operation]] = {}
    base = root / SDK_GO_DIR
    client = (base / "client.go").read_text(encoding="utf-8")
    fields = {svc: name for name, svc in re.findall(r"^\s+(\w+)\s+\*(\w+Service)\s*$", client, re.M)}
    for p in sorted(base.glob("*.go")):
        if p.name.endswith("_test.go"):
            continue
        text = strip_comments(p.read_text(encoding="utf-8"), go=True)
        funcs = list(re.finditer(r"^func \((\w+) \*(\w+)\) (\w+)\(", text, re.M))
        for idx, f in enumerate(funcs):
            recv, name = f.group(2), f.group(3)
            if not name[0].isupper():
                continue
            if recv == "Client":
                chain = name
            elif recv in fields:
                chain = f"{fields[recv]}.{name}"
            else:
                continue
            body = text[f.end(): funcs[idx + 1].start() if idx + 1 < len(funcs) else len(text)]
            for method, segs in literal_calls(body, True, matcher):
                ops, _ = matcher.ops_for(method, segs)
                out.setdefault(chain, []).extend(ops)
    for chain, routes in SDK_OVERRIDES["go"].items():
        out[chain] = [op for method, path in routes for op in matcher.by_path.get(path, []) if op.method == method]
    return out


def scan(root: Path = REPO_ROOT, ops: list[Operation] | None = None) -> Scan:
    ops = ops if ops is not None else load_operations(root / "sdk" / "openapi" / "onemind-v1.json")
    matcher = Matcher(ops)
    sdk = {"ts": sdk_methods_ts(root, matcher), "go": sdk_methods_go(root, matcher)}
    result = Scan()
    for surface in SURFACES:
        go = surface == "cli"
        methods = sdk["go" if go else "ts"]
        method_res = [(chain, re.compile(r"\." + r"\.".join(map(re.escape, chain.split("."))) + r"\s*(?:<[^()]*>)?\("), targets)
                      for chain, targets in methods.items() if targets]
        for p in surface_files(root, surface):
            rel = p.relative_to(root).as_posix()
            text = strip_comments(p.read_text(encoding="utf-8"), go=go)
            for method, segs in literal_calls(text, go, matcher):
                reached, path_only = matcher.ops_for(method, segs)
                for op in reached:
                    result.add(surface, op, Caller(rel, "path-only" if path_only else "call"))
            for chain, rx, targets in method_res:
                if rx.search(text):
                    for op in targets:
                        result.add(surface, op, Caller(rel, f"sdk:{chain}"))
    return result


# ---- exemptions ------------------------------------------------------------------------------------
@dataclass
class Group:
    name: str
    issue: int
    reason: str


@dataclass
class Exemptions:
    groups: dict[str, Group]
    entries: dict[tuple[str, str], str]  # (surface, op_id) -> group
    lines: dict[tuple[str, str], int]
    mobile_scope: MobileScope = field(default_factory=dict)
    indirect: dict[tuple[str, str], str] = field(default_factory=dict)  # (surface, op_id) -> reason
    indirect_lines: dict[tuple[str, str], int] = field(default_factory=dict)


def load_exemptions(path: Path = EXEMPTIONS) -> tuple[Exemptions, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise InputError(f"cannot read {path}: {e}") from e
    groups: dict[str, Group] = {}
    entries: dict[tuple[str, str], str] = {}
    lines: dict[tuple[str, str], int] = {}
    scope: dict[str, list[str]] = {}
    indirect: dict[tuple[str, str], str] = {}
    indirect_lines: dict[tuple[str, str], int] = {}
    errors: list[str] = []
    for no, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if parts[0] == "mobile-scope":
            if len(parts) < 2 or any(not x.startswith("/") for x in parts[2:]):
                errors.append(f"exemptions.txt:{no}: a scope line is `mobile-scope <tag> [/path/prefix ...]`")
                continue
            scope.setdefault(parts[1], []).extend(parts[2:])
            continue
        if parts[0] == "indirect":
            if len(parts) < 7 or parts[1] not in SURFACES:
                errors.append(f"exemptions.txt:{no}: an indirect line is `indirect <{'|'.join(SURFACES)}> "
                              "<operationId> <reason, at least four words: where the method is sent>`")
                continue
            key = (parts[1], parts[2])
            if key in indirect:
                errors.append(f"exemptions.txt:{no}: indirect {parts[1]} {parts[2]} is listed twice")
            indirect[key] = " ".join(parts[3:])
            indirect_lines[key] = no
            continue
        if parts[0] == "group":
            m = re.match(r"group\s+([a-z0-9][a-z0-9-]*)\s+issue=#(\d+)\s+(\S.*)$", s)
            if not m:
                errors.append(f"exemptions.txt:{no}: a group line is `group <name> issue=#<n> <reason>`")
                continue
            if m.group(1) in groups:
                errors.append(f"exemptions.txt:{no}: group {m.group(1)} is declared twice")
            groups[m.group(1)] = Group(m.group(1), int(m.group(2)), m.group(3))
            continue
        if len(parts) != 3 or parts[0] not in SURFACES:
            errors.append(f"exemptions.txt:{no}: an exemption line is `<{'|'.join(SURFACES)}> <operationId> <group>`")
            continue
        key = (parts[0], parts[1])
        if key in entries:
            errors.append(f"exemptions.txt:{no}: {parts[0]} {parts[1]} is listed twice")
        entries[key] = parts[2]
        lines[key] = no
    for key, g in entries.items():
        if g not in groups:
            errors.append(f"exemptions.txt:{lines[key]}: group {g} is not declared")
    for key, no in indirect_lines.items():
        if key in entries:
            errors.append(f"exemptions.txt:{no}: {key[0]} {key[1]} is both indirect and exempt (line {lines[key]}): keep one")
    return Exemptions(groups, entries, lines, {t: tuple(p) for t, p in scope.items()},
                      indirect, indirect_lines), errors


def covered(result: Scan, ex: Exemptions, surface: str, op_id: str) -> bool:
    """A method-aware caller, or a path-only literal the operation's `indirect` line vouches for."""
    if result.has(surface, op_id):
        return True
    return (surface, op_id) in ex.indirect and bool(result.path_only(surface, op_id))


def problems(ops: list[Operation], result: Scan, ex: Exemptions) -> list[str]:
    """Why the surfaces, the exemptions and the spec disagree; empty when every operation is covered."""
    out: list[str] = []
    by_id = {op.op_id: op for op in ops}
    tags = {t for op in ops for t in op.tags}
    for tag, prefixes in sorted(ex.mobile_scope.items()):
        if tag not in tags:
            out.append(f"exemptions.txt: mobile-scope {tag} names no OpenAPI tag in the spec")
        for p in prefixes:
            if not any(op.path == p or op.path.startswith(p + "/") for op in ops if tag in op.tags):
                out.append(f"exemptions.txt: mobile-scope {tag} {p} matches no operation")
    for op in sorted(ops, key=lambda o: o.op_id):
        for surface in required_surfaces(op, ex.mobile_scope):
            listed = (surface, op.op_id) in ex.entries
            if not covered(result, ex, surface, op.op_id) and not listed:
                what = {"dashboard": "a dashboard screen calling it through @onemind/sdk",
                        "cli": "an `onemind` command (Cobra, --json)",
                        "mobile": "a phone screen (it is in the mobile 1.0 scope)"}[surface]
                hint = ""
                if result.path_only(surface, op.op_id):
                    files = sorted({c.file for c in result.path_only(surface, op.op_id)})
                    hint = (f" ({files[0]} names its path but no HTTP method: call it with the method, or, when "
                            f"that file really sends {op.method}, vouch with `indirect {surface} {op.op_id} <reason>`)")
                out.append(f"{op.op_id} ({op.key}) has no {surface} caller{hint}: add {what}, or list "
                           f"`{surface} {op.op_id} <group>` in sdk/tools/surface-parity/exemptions.txt with an owner issue")
    for (surface, op_id), group in sorted(ex.entries.items()):
        no = ex.lines[(surface, op_id)]
        op = by_id.get(op_id)
        if op is None:
            out.append(f"exemptions.txt:{no}: {op_id} is not in the spec any more: delete the line")
        elif surface not in required_surfaces(op, ex.mobile_scope):
            out.append(f"exemptions.txt:{no}: {surface} {op_id} is not required on {surface}: delete the line")
        elif result.has(surface, op_id):
            files = sorted({c.file for c in result.callers[surface][op_id]})
            out.append(f"exemptions.txt:{no}: {surface} {op_id} is stale, {files[0]} now calls it: delete the line")
    for (surface, op_id), no in sorted(ex.indirect_lines.items()):
        op = by_id.get(op_id)
        if op is None:
            out.append(f"exemptions.txt:{no}: indirect {op_id} is not in the spec any more: delete the line")
        elif surface not in required_surfaces(op, ex.mobile_scope):
            out.append(f"exemptions.txt:{no}: indirect {surface} {op_id} is not required on {surface}: delete the line")
        elif result.has(surface, op_id):
            files = sorted({c.file for c in result.callers[surface][op_id] if c.how != "path-only"})
            out.append(f"exemptions.txt:{no}: indirect {surface} {op_id} is stale, {files[0]} now calls it with "
                       "its HTTP method: delete the line")
        elif not result.path_only(surface, op_id):
            out.append(f"exemptions.txt:{no}: indirect {surface} {op_id} is stale, no {surface} file names "
                       f"{op.path} any more: delete the line, or list the gap under a group")
    used = set(ex.entries.values())
    for name in sorted(set(ex.groups) - used):
        out.append(f"exemptions.txt: group {name} has no entries left: delete it")
    return out


def report(ops: list[Operation], result: Scan, ex: Exemptions) -> str:
    rows = []
    for op in sorted(ops, key=lambda o: o.op_id):
        cells = []
        for surface in SURFACES:
            need = surface in required_surfaces(op, ex.mobile_scope)
            if result.has(surface, op.op_id):
                cells.append("Y")
            elif covered(result, ex, surface, op.op_id):
                cells.append("indirect")
            elif (surface, op.op_id) in ex.entries:
                cells.append(f"x:{ex.entries[(surface, op.op_id)]}")
            elif result.path_only(surface, op.op_id):
                cells.append("MISSING(path-only)" if need else "path-only")
            else:
                cells.append("MISSING" if need else "-")
        rows.append(f"{op.op_id:48} {op.key:70} " + "  ".join(f"{c:24}" for c in cells))
    head = f"{'operation':48} {'route':70} " + "  ".join(f"{s:24}" for s in SURFACES)
    return "\n".join([head] + rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--report", action="store_true", help="print every operation and its callers per surface")
    ap.add_argument("--print-exemptions", action="store_true",
                    help="print an exemption line for every missing caller (to seed or review, never to get green)")
    args = ap.parse_args(argv)
    try:
        ops = load_operations()
        result = scan(REPO_ROOT, ops)
        ex, errs = load_exemptions()
    except InputError as e:
        print(f"surface-parity: {e}", file=sys.stderr)
        return 2
    if args.report:
        print(report(ops, result, ex))
        return 0
    if args.print_exemptions:
        for op in sorted(ops, key=lambda o: o.op_id):
            for surface in required_surfaces(op, ex.mobile_scope):
                if not covered(result, ex, surface, op.op_id):
                    tag = " (path-only)" if result.path_only(surface, op.op_id) else ""
                    print(f"{surface} {op.op_id} {ex.entries.get((surface, op.op_id), 'TODO')}{tag}")
        return 0
    bad = errs + problems(ops, result, ex)
    for line in bad:
        print(line)
    if bad:
        print(f"surface-parity: {len(bad)} problem(s)", file=sys.stderr)
        return 1
    print(f"surface-parity: {len(ops)} operations, {len(ex.entries)} exemptions, "
          f"{len(ex.indirect)} indirect, all accounted for")
    return 0


if __name__ == "__main__":
    sys.exit(main())
