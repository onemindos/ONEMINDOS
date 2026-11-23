#!/usr/bin/env -S python3 -I
# SPDX-License-Identifier: Apache-2.0
"""OpenAPI contract rules as a lint over sdk/openapi/onemind-v1.json (issue #874).

The committed spec is the reviewed API contract: the SDKs, the CLI and the MCP catalogue are made
from it. These rules keep every route the same shape, so a new route cannot invent its own auth,
paging or error body:

  security     every operation names a security scheme the spec declares, or is on public.txt
  scopes       every secured operation lists at least one scope (declared by the scheme for oauth2)
  paging       a list operation (one that takes limit, cursor, offset or page, or returns a
               next-cursor field) uses the one paging shape of contract §12.1: a JSON array,
               query `limit` (integer) and `cursor`, and a `Link: <...>; rel="next"` header
  error-schema every 4xx, 5xx and default response has a body, and the body is ErrorBody
  idempotency  every POST, PUT, PATCH and DELETE takes an Idempotency-Key header, or is on
               idempotency-exempt.txt

Violations known when the lint landed are in baseline.txt, one line each with an owner. The lint
fails on a violation that is not in the baseline, on a baseline line that no longer matches a
violation (fixed: delete the line), and on a public or exempt line whose operation is gone.

Run with: python3 -I sdk/tools/openapi-lint [--spec FILE] [--baseline FILE] [--public FILE]
          [--exempt FILE] [--print-baseline]
Exit codes: 0 clean (baselined violations allowed), 1 a rule failed, 2 an input cannot be read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DEFAULT_SPEC = REPO_ROOT / "sdk" / "openapi" / "onemind-v1.json"

RULES = ("security", "scopes", "paging", "error-schema", "idempotency")
METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
UNSAFE = {"post", "put", "patch", "delete"}
ERROR_SCHEMA = "#/components/schemas/ErrorBody"
PAGING_QUERY = {"limit", "cursor", "offset", "page", "page_size", "per_page"}
PAGING_FIELDS = {"next_cursor", "nextCursor"}  # a cursor in the body instead of the Link header
IDEMPOTENCY_HEADER = "idempotency-key"  # HTTP header names are case-insensitive (RFC 9110 §5.1)


class InputError(Exception):
    pass


def resolve(doc: dict, node):
    """Follow local `$ref`s ("#/components/..."); anything else is returned as is."""
    seen = set()
    while isinstance(node, dict) and isinstance(node.get("$ref"), str):
        ref = node["$ref"]
        if not ref.startswith("#/") or ref in seen:
            return node
        seen.add(ref)
        target = doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                return {}
            target = target[part]
        node = target
    return node


def operations(doc: dict):
    """(METHOD, path, operation, path-item parameters) for every operation, in spec order."""
    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        shared = item.get("parameters") or []
        for method in METHODS:
            op = item.get(method)
            if isinstance(op, dict):
                yield method.upper(), path, op, shared


def parameters(doc: dict, op: dict, shared: list) -> list[dict]:
    """The operation's parameters after the path item's, an operation entry winning (OpenAPI 3.1 §4.8.9)."""
    out: dict[tuple, dict] = {}
    for p in list(shared) + list(op.get("parameters") or []):
        p = resolve(doc, p)
        if isinstance(p, dict) and "name" in p:
            name = p["name"].lower() if p.get("in") == "header" else p["name"]
            out[(p.get("in"), name)] = p
    return list(out.values())


def schema_types(doc: dict, schema) -> set:
    """The JSON types a schema allows, looking through $ref, anyOf and oneOf."""
    schema = resolve(doc, schema)
    if not isinstance(schema, dict):
        return set()
    t = schema.get("type")
    types = set(t) if isinstance(t, list) else ({t} if t else set())
    for key in ("anyOf", "oneOf"):
        for sub in schema.get(key) or []:
            types |= schema_types(doc, sub)
    return types


def object_properties(doc: dict, schema) -> set:
    """Property names of an object schema, looking through $ref, allOf, anyOf and oneOf."""
    schema = resolve(doc, schema)
    if not isinstance(schema, dict):
        return set()
    names = set((schema.get("properties") or {}).keys())
    for key in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(key) or []:
            names |= object_properties(doc, sub)
    return names


def ok_response(doc: dict, op: dict):
    """The first 2xx response object (resolved), or {}."""
    for code in sorted((op.get("responses") or {}).keys()):
        if str(code).startswith("2"):
            resp = resolve(doc, op["responses"][code])
            return resp if isinstance(resp, dict) else {}
    return {}


def json_schema(resp: dict):
    """The schema of a response's JSON body, or None."""
    for mt, body in (resp.get("content") or {}).items():
        if "json" in mt and isinstance(body, dict):
            return body.get("schema")
    return None


def check_security(doc, op):
    """security and scopes findings for one operation: (rule, message) pairs."""
    schemes = (doc.get("components") or {}).get("securitySchemes") or {}
    reqs = op["security"] if "security" in op else doc.get("security")
    if not reqs or any(not r for r in reqs):
        return [("security", "no security requirement: add one, or list the route in public.txt with a reason")]
    out = []
    for req in reqs:
        for name, scopes in req.items():
            scheme = resolve(doc, schemes.get(name))
            if not scheme:
                out.append(("security", f"names security scheme {name!r}, which components.securitySchemes does not declare"))
                continue
            if not scopes:
                out.append(("scopes", f"secured by {name!r} but lists no scope"))
                continue
            if scheme.get("type") == "oauth2":
                declared = set()
                for flow in (scheme.get("flows") or {}).values():
                    declared |= set((flow or {}).get("scopes") or {})
                for s in scopes:
                    if s not in declared:
                        out.append(("scopes", f"scope {s!r} is not declared by security scheme {name!r}"))
    return out


def check_paging(doc, op, params):
    """Contract §12.1 Lists: a JSON array, `?limit=` and `?cursor=`, and a `Link: <...>; rel="next"` header."""
    query = {p["name"]: p for p in params if p.get("in") == "query"}
    resp = ok_response(doc, op)
    body = json_schema(resp)
    fields = object_properties(doc, body)
    if not (PAGING_QUERY & set(query) or PAGING_FIELDS & fields):
        return []
    missing = []
    if "limit" not in query or "integer" not in schema_types(doc, query["limit"].get("schema")):
        missing.append("query `limit` (integer)")
    if "cursor" not in query:
        missing.append("query `cursor`")
    if "link" not in {str(h).lower() for h in (resp.get("headers") or {})}:
        missing.append("a `Link` (rel=\"next\") header on the 2xx response")
    if "array" not in schema_types(doc, body):
        missing.append("a JSON array body")
    other = sorted((PAGING_QUERY - {"limit", "cursor"}) & set(query)) + sorted(PAGING_FIELDS & fields)
    if not missing and not other:
        return []
    msg = "a list route uses the one paging shape (limit, cursor, Link rel=next; contract §12.1)"
    if missing:
        msg += "; missing " + ", ".join(missing)
    if other:
        msg += "; other paging names " + ", ".join(other)
    return [("paging", msg)]


def check_errors(doc, op):
    bad = []
    for code, resp in (op.get("responses") or {}).items():
        code = str(code)
        if not (code[:1] in ("4", "5") or code == "default"):
            continue
        resp = resolve(doc, resp)
        media = (resp.get("content") or {}) if isinstance(resp, dict) else {}
        if not media:
            bad.append(f"{code} (no body)")
        elif any(not isinstance(b, dict) or (b.get("schema") or {}).get("$ref") != ERROR_SCHEMA for b in media.values()):
            bad.append(f"{code} (not ErrorBody)")
    if not bad:
        return []
    return [("error-schema", "every error response is the one ErrorBody: " + ", ".join(bad))]


def check_idempotency(method, params):
    if method.lower() not in UNSAFE:
        return []
    if any(p.get("in") == "header" and p["name"].lower() == IDEMPOTENCY_HEADER for p in params):
        return []
    return [("idempotency", "an unsafe method takes an Idempotency-Key header, or is listed in idempotency-exempt.txt")]


def lint(doc: dict, public: set, exempt: set) -> list[tuple]:
    """Every finding as (rule, METHOD, path, message), in spec order."""
    if not isinstance(doc, dict) or not isinstance(doc.get("paths"), dict):
        raise InputError("the spec has no `paths` object")
    findings = []
    for method, path, op, shared in operations(doc):
        params = parameters(doc, op, shared)
        found = [] if (method, path) in public else check_security(doc, op)
        found += check_paging(doc, op, params)
        found += check_errors(doc, op)
        if (method, path) not in exempt:
            found += check_idempotency(method, params)
        seen = set()
        for rule, msg in found:
            if rule not in seen:  # one line per route and rule, so the baseline is one line each
                seen.add(rule)
                findings.append((rule, method, path, msg))
    return findings


def read_lines(path: Path, fields: int, what: str):
    """Lines of `METHOD path ...` files: (line number, list of fields, comment). '#' starts a comment."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise InputError(f"cannot read {what} {path}: {e}") from e
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        line, _, comment = raw.partition("#")
        parts = line.split()
        if not parts:
            continue
        if len(parts) != fields:
            raise InputError(f"{path.name}:{no}: expected {fields} fields, got {len(parts)}: {raw.strip()!r}")
        out.append((no, parts, comment.strip()))
    return out


def read_routes(path: Path, what: str) -> dict:
    """public.txt and idempotency-exempt.txt: `METHOD /path  # why`, the reason is required."""
    routes = {}
    for no, (method, route), why in read_lines(path, 2, what):
        if not why:
            raise InputError(f"{path.name}:{no}: {method} {route} needs a reason after '#'")
        if (method.upper(), route) in routes:
            raise InputError(f"{path.name}:{no}: {method} {route} is listed twice")
        routes[(method.upper(), route)] = no
    return routes


def read_baseline(path: Path) -> dict:
    """baseline.txt: `rule METHOD /path owner=<who>  # optional note`."""
    entries = {}
    for no, (rule, method, route, owner), _ in read_lines(path, 4, "baseline"):
        if rule not in RULES:
            raise InputError(f"{path.name}:{no}: unknown rule {rule!r} (one of {', '.join(RULES)})")
        if not owner.startswith("owner=") or owner == "owner=":
            raise InputError(f"{path.name}:{no}: the fourth field is owner=<who>")
        key = (rule, method.upper(), route)
        if key in entries:
            raise InputError(f"{path.name}:{no}: {rule} {method} {route} is listed twice")
        entries[key] = no
    return entries


def owner_of(op: dict) -> str:
    tags = op.get("tags") or ["core"]
    return "owner=core:" + str(tags[0]).replace(" ", "-")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="openapi-lint", description=__doc__.splitlines()[0])
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    ap.add_argument("--baseline", type=Path, default=HERE / "baseline.txt")
    ap.add_argument("--public", type=Path, default=HERE / "public.txt")
    ap.add_argument("--exempt", type=Path, default=HERE / "idempotency-exempt.txt")
    ap.add_argument("--print-baseline", action="store_true",
                    help="print every current violation as baseline lines (for review), then exit 0")
    args = ap.parse_args(argv)
    try:
        try:
            doc = json.loads(args.spec.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise InputError(f"cannot read spec {args.spec}: {e}") from e
        public = read_routes(args.public, "public list")
        exempt = read_routes(args.exempt, "idempotency exceptions")
        findings = lint(doc, set(public), set(exempt))
        if args.print_baseline:
            ops = {(m, p): op for m, p, op, _ in operations(doc)}
            for rule, method, path, _ in sorted(findings, key=lambda f: RULES.index(f[0])):
                print(f"{rule} {method} {path} {owner_of(ops[(method, path)])}")
            return 0
        baseline = read_baseline(args.baseline)
    except InputError as e:
        print(f"openapi-lint: {e}", file=sys.stderr)
        return 2

    present = {(m, p) for m, p, _, _ in operations(doc)}
    errors = []
    for rule, method, path, msg in findings:
        if (rule, method, path) not in baseline:
            errors.append(f"{rule}: {method} {path}: {msg}")
    found = {(r, m, p) for r, m, p, _ in findings}
    for key, no in sorted(baseline.items(), key=lambda kv: kv[1]):
        if key not in found:
            errors.append(f"stale baseline: {args.baseline.name}:{no}: {' '.join(key)} no longer fails; delete the line")
    for name, listed in ((args.public.name, public), (args.exempt.name, exempt)):
        for (method, path), no in sorted(listed.items(), key=lambda kv: kv[1]):
            if (method, path) not in present:
                errors.append(f"stale entry: {name}:{no}: {method} {path} is not in the spec; delete the line")
    for e in errors:
        print(f"openapi-lint: {e}")
    if errors:
        print(f"openapi-lint: {len(errors)} problem(s); rules and files: sdk/tools/openapi-lint/README.md")
        return 1
    print(f"openapi-lint: ok ({len(present)} operations, {len(findings)} baselined violations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
