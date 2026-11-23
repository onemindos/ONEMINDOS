# SPDX-License-Identifier: Apache-2.0
"""sdk/tools/openapi-lint (issue #874): the OpenAPI contract rules, one bad fixture per rule.

Runs the real tool as CI does (python3 -I) on small specs written here and on the committed spec
with its baseline. Stdlib only, so it runs under `python3 -I -m unittest discover -s sdk/tools/tests`.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "sdk" / "tools" / "openapi-lint"
SPEC = REPO / "sdk" / "openapi" / "onemind-v1.json"

ERR = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorBody"}}}, "description": "error"}
IDEM = {"in": "header", "name": "Idempotency-Key", "required": False, "schema": {"type": "string"}}
SECURED = [{"bearer": ["things:read"]}]


def op(**extra) -> dict:
    """A compliant operation: secured with a scope, errors are ErrorBody."""
    body = {"tags": ["things"], "security": copy.deepcopy(SECURED),
            "responses": {"200": {"description": "ok"}, "401": copy.deepcopy(ERR), "404": copy.deepcopy(ERR)}}
    body.update(extra)
    return body


def good_spec() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "fixture", "version": "1"},
        "components": {
            "schemas": {"ErrorBody": {"type": "object", "properties": {"error": {"type": "string"}}},
                        "Thing": {"type": "object", "properties": {"id": {"type": "string"}}}},
            "securitySchemes": {
                "bearer": {"type": "http", "scheme": "bearer"},
                "oauth": {"type": "oauth2", "flows": {"clientCredentials": {
                    "tokenUrl": "/token", "scopes": {"things:read": "read", "things:write": "write"}}}},
            },
        },
        "paths": {
            "/healthz": {"get": {"tags": ["meta"], "responses": {"200": {"description": "ok"}}}},
            "/v1/things": {
                "get": op(
                    parameters=[{"in": "query", "name": "limit", "schema": {"type": "integer"}},
                                {"in": "query", "name": "cursor", "schema": {"type": "string"}}],
                    responses={"200": {"description": "a page", "headers": {"Link": {"schema": {"type": "string"}}},
                                       "content": {"application/json": {"schema": {
                                           "type": "array", "items": {"$ref": "#/components/schemas/Thing"}}}}},
                               "401": copy.deepcopy(ERR)}),
                "post": op(parameters=[copy.deepcopy(IDEM)], security=[{"oauth": ["things:write"]}]),
            },
            "/v1/things/{id}": {
                "parameters": [{"in": "path", "name": "id", "required": True, "schema": {"type": "string"}}],
                "delete": op(parameters=[{"$ref": "#/components/parameters/Idem"}]),
            },
        },
    }


def with_param_component(spec: dict) -> dict:
    spec["components"]["parameters"] = {"Idem": copy.deepcopy(IDEM)}
    return spec


class OpenapiLint(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def run_lint(self, spec: dict, baseline: str = "", public: str = "GET /healthz  # open health check\n",
                 exempt: str = "", spec_file: Path | None = None) -> subprocess.CompletedProcess:
        files = {"baseline.txt": baseline, "public.txt": public, "exempt.txt": exempt}
        for name, text in files.items():
            (self.dir / name).write_text(text)
        if spec_file is None:
            spec_file = self.dir / "spec.json"
            spec_file.write_text(json.dumps(spec))
        return subprocess.run(
            [sys.executable, "-I", str(TOOL), "--spec", str(spec_file), "--baseline", str(self.dir / "baseline.txt"),
             "--public", str(self.dir / "public.txt"), "--exempt", str(self.dir / "exempt.txt")],
            capture_output=True, text=True, timeout=120)

    def assertFails(self, r, rule: str, route: str):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, re.compile(rf"^openapi-lint: {re.escape(rule)}: {re.escape(route)}: ", re.M))

    def good(self) -> dict:
        return with_param_component(good_spec())

    # -- the fixture itself is clean, so each failure below comes from one rule only ------------------
    def test_good_spec_passes(self):
        r = self.run_lint(self.good())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("openapi-lint: ok (4 operations, 0 baselined violations)", r.stdout)

    # -- security -------------------------------------------------------------------------------------
    def test_route_without_security_fails(self):
        s = self.good()
        del s["paths"]["/v1/things"]["get"]["security"]
        self.assertFails(self.run_lint(s), "security", "GET /v1/things")

    def test_empty_or_anonymous_security_fails(self):
        s = self.good()
        s["paths"]["/v1/things"]["get"]["security"] = []
        s["paths"]["/v1/things"]["post"]["security"] = [{}, {"bearer": ["things:write"]}]
        r = self.run_lint(s)
        self.assertFails(r, "security", "GET /v1/things")
        self.assertFails(r, "security", "POST /v1/things")

    def test_undeclared_scheme_fails(self):
        s = self.good()
        s["paths"]["/v1/things"]["get"]["security"] = [{"apiKey": ["things:read"]}]
        r = self.run_lint(s)
        self.assertFails(r, "security", "GET /v1/things")
        self.assertIn("'apiKey'", r.stdout)

    def test_document_level_security_counts(self):
        s = self.good()
        s["security"] = copy.deepcopy(SECURED)
        del s["paths"]["/v1/things"]["get"]["security"]
        self.assertEqual(self.run_lint(s).returncode, 0)

    def test_public_list_needs_a_reason_and_a_live_route(self):
        s = self.good()
        self.assertFails(self.run_lint(s, public=""), "security", "GET /healthz")
        r = self.run_lint(s, public="GET /healthz\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("needs a reason", r.stderr)
        r = self.run_lint(s, public="GET /healthz  # open\nGET /v1/gone  # removed route\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale entry: public.txt:2: GET /v1/gone", r.stdout)

    # -- scopes ---------------------------------------------------------------------------------------
    def test_secured_route_without_scopes_fails(self):
        s = self.good()
        s["paths"]["/v1/things"]["get"]["security"] = [{"bearer": []}]
        self.assertFails(self.run_lint(s), "scopes", "GET /v1/things")

    def test_oauth_scope_must_be_declared(self):
        s = self.good()
        s["paths"]["/v1/things"]["post"]["security"] = [{"oauth": ["things:delete"]}]
        r = self.run_lint(s)
        self.assertFails(r, "scopes", "POST /v1/things")
        self.assertIn("'things:delete'", r.stdout)

    # -- paging ---------------------------------------------------------------------------------------
    def test_list_without_cursor_or_link_fails(self):
        s = self.good()
        get = s["paths"]["/v1/things"]["get"]
        get["parameters"] = get["parameters"][:1]
        del get["responses"]["200"]["headers"]
        r = self.run_lint(s)
        self.assertFails(r, "paging", "GET /v1/things")
        self.assertIn("query `cursor`", r.stdout)
        self.assertIn("`Link`", r.stdout)

    def test_offset_paging_fails(self):
        s = self.good()
        s["paths"]["/v1/things"]["get"]["parameters"].append({"in": "query", "name": "offset", "schema": {"type": "integer"}})
        r = self.run_lint(s)
        self.assertFails(r, "paging", "GET /v1/things")
        self.assertIn("other paging names offset", r.stdout)

    def test_cursor_envelope_body_fails(self):
        s = self.good()
        s["paths"]["/v1/things"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {
            "type": "object", "properties": {"items": {"type": "array"}, "next_cursor": {"type": "string"}}}
        r = self.run_lint(s)
        self.assertFails(r, "paging", "GET /v1/things")
        self.assertIn("a JSON array body", r.stdout)
        self.assertIn("next_cursor", r.stdout)

    def test_string_limit_fails(self):
        s = self.good()
        s["paths"]["/v1/things"]["get"]["parameters"][0]["schema"] = {"type": "string"}
        self.assertFails(self.run_lint(s), "paging", "GET /v1/things")

    # -- error-schema ---------------------------------------------------------------------------------
    def test_error_without_body_fails(self):
        s = self.good()
        s["paths"]["/v1/things/{id}"]["delete"]["responses"]["404"] = {"description": "gone"}
        r = self.run_lint(s)
        self.assertFails(r, "error-schema", "DELETE /v1/things/{id}")
        self.assertIn("404 (no body)", r.stdout)

    def test_error_with_other_schema_fails(self):
        s = self.good()
        s["components"]["schemas"]["HTTPValidationError"] = {"type": "object"}
        s["paths"]["/v1/things"]["post"]["responses"]["422"] = {
            "description": "bad", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}}}
        r = self.run_lint(s)
        self.assertFails(r, "error-schema", "POST /v1/things")
        self.assertIn("422 (not ErrorBody)", r.stdout)

    def test_error_via_response_component_passes(self):
        s = self.good()
        s["components"]["responses"] = {"NotFound": copy.deepcopy(ERR)}
        s["paths"]["/v1/things"]["post"]["responses"]["404"] = {"$ref": "#/components/responses/NotFound"}
        self.assertEqual(self.run_lint(s).returncode, 0)

    # -- idempotency ----------------------------------------------------------------------------------
    def test_unsafe_route_without_idempotency_key_fails(self):
        s = self.good()
        s["paths"]["/v1/things"]["post"]["parameters"] = []
        self.assertFails(self.run_lint(s), "idempotency", "POST /v1/things")

    def test_header_name_is_case_insensitive(self):
        s = self.good()
        s["paths"]["/v1/things"]["post"]["parameters"] = [dict(IDEM, name="idempotency-key")]
        self.assertEqual(self.run_lint(s).returncode, 0)

    def test_exempt_list_allows_a_reviewed_route(self):
        s = self.good()
        s["paths"]["/v1/things"]["post"]["parameters"] = []
        self.assertEqual(self.run_lint(s, exempt="POST /v1/things  # reviewed: replay would store a token\n").returncode, 0)

    # -- baseline -------------------------------------------------------------------------------------
    def test_baselined_violation_passes_and_stale_line_fails(self):
        s = self.good()
        s["paths"]["/v1/things"]["post"]["parameters"] = []
        r = self.run_lint(s, baseline="idempotency POST /v1/things owner=core:things\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 baselined violations", r.stdout)
        r = self.run_lint(self.good(), baseline="# header\nidempotency POST /v1/things owner=core:things\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale baseline: baseline.txt:2: idempotency POST /v1/things", r.stdout)

    def test_baseline_covers_only_its_own_rule(self):
        s = self.good()
        s["paths"]["/v1/things"]["post"]["parameters"] = []
        del s["paths"]["/v1/things"]["post"]["security"]
        r = self.run_lint(s, baseline="idempotency POST /v1/things owner=core:things\n")
        self.assertFails(r, "security", "POST /v1/things")

    def test_baseline_lines_need_rule_and_owner(self):
        for line, why in (("idempotency POST /v1/things\n", "expected 4 fields"),
                          ("idempotency POST /v1/things core\n", "owner=<who>"),
                          ("speed POST /v1/things owner=x\n", "unknown rule")):
            r = self.run_lint(self.good(), baseline=line)
            self.assertEqual(r.returncode, 2, line)
            self.assertIn(why, r.stderr)

    def test_print_baseline_lists_findings_with_owner(self):
        s = self.good()
        s["paths"]["/v1/things"]["post"]["parameters"] = []
        self.run_lint(s)
        r = subprocess.run([sys.executable, "-I", str(TOOL), "--spec", str(self.dir / "spec.json"), "--print-baseline",
                            "--public", str(self.dir / "public.txt"), "--exempt", str(self.dir / "exempt.txt")],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.stdout, "idempotency POST /v1/things owner=core:things\n")

    # -- the committed spec ---------------------------------------------------------------------------
    def test_committed_spec_passes_with_the_committed_baseline(self):
        r = subprocess.run([sys.executable, "-I", str(TOOL)], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("openapi-lint: ok", r.stdout)

    def committed_with(self, path: str, operation: dict, schemes: bool) -> subprocess.CompletedProcess:
        spec = json.loads(SPEC.read_text(encoding="utf-8"))
        if schemes:
            spec["components"]["securitySchemes"] = {"bearer": {"type": "http", "scheme": "bearer"}}
        spec["paths"][path] = {"get": operation}
        out = self.dir / "committed.json"
        out.write_text(json.dumps(spec))
        here = TOOL
        return subprocess.run(
            [sys.executable, "-I", str(TOOL), "--spec", str(out), "--baseline", str(here / "baseline.txt"),
             "--public", str(here / "public.txt"), "--exempt", str(here / "idempotency-exempt.txt")],
            capture_output=True, text=True, timeout=120)

    def test_adding_a_route_without_scopes_to_the_committed_spec_fails(self):
        r = self.committed_with("/v1/zz-new", op(security=[{"bearer": []}]), schemes=True)
        self.assertFails(r, "scopes", "GET /v1/zz-new")
        r = self.committed_with("/v1/zz-new", {k: v for k, v in op().items() if k != "security"}, schemes=False)
        self.assertFails(r, "security", "GET /v1/zz-new")

    def test_check_stale_runs_the_lint(self):
        makefile = (REPO / "sdk" / "Makefile").read_text(encoding="utf-8")
        recipe = makefile.split("\ncheck-stale:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("contract-lint", recipe)
        target = makefile.split("\ncontract-lint:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("python3 -I tools/openapi-lint", target)


if __name__ == "__main__":
    unittest.main()
