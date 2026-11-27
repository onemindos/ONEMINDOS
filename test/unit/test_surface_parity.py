# SPDX-License-Identifier: Apache-2.0
"""Surface parity ratchet (#1232, BUILDER-BRIEFING item 6): the API and the screens and commands stay 1:1.

The real check runs sdk/tools/surface-parity over this repo: every operation in sdk/openapi/onemind-v1.json
has a dashboard caller, every write has an `onemind` command, every operation in the phone's scope has a
phone caller, or the operation is listed in sdk/tools/surface-parity/exemptions.txt with a reason and an
owner issue. A stale exemption fails too, so the list only shrinks. The other tests pin how a caller is
recognised, on a small fake repo.
"""
import importlib.util
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("surface_parity", ROOT / "sdk" / "tools" / "surface-parity" / "__main__.py")
sp = importlib.util.module_from_spec(_spec)
sys.modules["surface_parity"] = sp  # dataclasses look their module up by name
_spec.loader.exec_module(sp)


class RepoIsAccountedFor(unittest.TestCase):
    def test_every_operation_has_its_callers_or_an_exemption(self):
        ops = sp.load_operations()
        result = sp.scan(ROOT, ops)
        ex, errors = sp.load_exemptions()
        bad = errors + sp.problems(ops, result, ex)
        self.assertEqual(bad, [], "\n" + "\n".join(bad) + "\n\nSee sdk/tools/surface-parity/exemptions.txt (header) "
                         "and BUILDER-BRIEFING item 6: add the screen or command, or delete a stale line.")

    def test_the_scan_finds_callers_on_every_surface(self):
        # A guard against the scanner silently finding nothing (which would make every row an exemption).
        result = sp.scan(ROOT)
        for surface, floor in (("dashboard", 150), ("cli", 60), ("mobile", 60)):
            self.assertGreater(len(result.callers.get(surface, {})), floor, surface)
        # Reached only through @onemind/sdk methods (client.domains.list(), client.tips.list()), never a path string.
        self.assertTrue(any(c.how.startswith("sdk:") for c in result.callers["dashboard"]["domains.list"]))
        self.assertTrue(any(c.how.startswith("sdk:") for c in result.callers["dashboard"]["tips.list"]))
        # Reached only through the Go SDK (c.Actions.ApproveBound) in the CLI.
        self.assertTrue(any(c.how.startswith("sdk:") for c in result.callers["cli"]["actions.approve"]))

    def test_ssh_keys_list_is_exempt_only_while_the_ssh_screen_reads_the_same_list(self):
        # The dashboard-wider-read exemption (PR #1323 review) holds only while its reason is true: the SSH screen
        # reads GET /v1/ssh, whose keys are the same SshKey list GET /v1/ssh/keys returns, and the CLI lists keys
        # through the narrower read. If any half goes, this fails and the line must be argued again.
        ops = sp.load_operations()
        result = sp.scan(ROOT, ops)
        ex, _ = sp.load_exemptions()
        self.assertEqual(ex.entries.get(("dashboard", "ssh.keys.list")), "dashboard-wider-read")
        self.assertEqual(sorted(op for (_, op), g in ex.entries.items() if g == "dashboard-wider-read"), ["ssh.keys.list"])
        self.assertIn("dashboard/src/pages/SshKeys.tsx", {c.file for c in result.callers["dashboard"].get("ssh.get", [])})
        self.assertTrue(result.has("cli", "ssh.keys.list"))
        spec = json.loads((ROOT / "sdk" / "openapi" / "onemind-v1.json").read_text(encoding="utf-8"))
        schemas = spec["components"]["schemas"]
        self.assertEqual(spec["paths"]["/v1/ssh"]["get"]["responses"]["200"]["content"]["application/json"]["schema"],
                         {"$ref": "#/components/schemas/SshView"})
        self.assertEqual(spec["paths"]["/v1/ssh/keys"]["get"]["responses"]["200"]["content"]["application/json"]["schema"],
                         {"$ref": "#/components/schemas/SshKeys"})
        self.assertEqual(schemas["SshView"]["properties"]["keys"], schemas["SshKeys"]["properties"]["keys"])
        self.assertEqual(schemas["SshKeys"]["properties"]["keys"]["items"], {"$ref": "#/components/schemas/SshKey"})
        self.assertIn("keys", schemas["SshView"]["required"])

    def test_every_group_has_an_issue_and_a_reason(self):
        ex, errors = sp.load_exemptions()
        self.assertEqual(errors, [])
        for g in ex.groups.values():
            self.assertGreater(g.issue, 0, g.name)
            self.assertGreater(len(g.reason.split()), 5, g.name)

    def test_the_mobile_scope_is_declared(self):
        ex, _ = sp.load_exemptions()
        self.assertEqual(sorted(ex.mobile_scope), ["actions", "auth", "files", "photos", "push"])

    def test_every_indirect_line_still_has_its_path_only_literal(self):
        # The whole-repo check covers this too; this names the rule: an indirect line stands only for a
        # path the surface still names, never for an operation with no literal at all.
        ops = sp.load_operations()
        result = sp.scan(ROOT, ops)
        ex, _ = sp.load_exemptions()
        self.assertGreater(len(ex.indirect), 0)
        for surface, op_id in ex.indirect:
            self.assertTrue(result.path_only(surface, op_id), f"{surface} {op_id}")
            self.assertFalse(result.has(surface, op_id), f"{surface} {op_id}")


SPEC = {
    "openapi": "3.1.0",
    "paths": {
        "/v1/tokens": {"get": {"operationId": "tokens.list", "tags": ["tokens"]},
                       "post": {"operationId": "tokens.create", "tags": ["tokens"]}},
        "/v1/tokens/{token_id}": {"delete": {"operationId": "tokens.revoke", "tags": ["tokens"]}},
        "/v1/tokens/builtin": {"get": {"operationId": "tokens.builtin", "tags": ["tokens"]}},
        "/v1/domains": {"get": {"operationId": "domains.list", "tags": ["domains"]}},
        "/v1/actions": {"get": {"operationId": "actions.list", "tags": ["actions"]}},
        "/v1/apps/{app_id}/logs": {"get": {"operationId": "apps.logs", "tags": ["apps"]}},
    },
}

SDK_TS = """
export class OneMind {
  readonly domains = {
    list: () => this.call<X>({ method: "GET", path: "/v1/domains" }),
  };
}
"""

SDK_GO = """
package onemind

type Client struct {
	Actions *ActionsService
}

func (s *ActionsService) List(ctx context.Context) ([]Action, error) {
	return v, s.c.Do(ctx, http.MethodGet, "/v1/actions", nil, &v)
}
"""


class FakeRepo:
    def __init__(self, files: dict[str, str]):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        base = {
            "sdk/openapi/onemind-v1.json": json.dumps(SPEC),
            "sdk/ts/src/client.ts": SDK_TS,
            "sdk/go/client.go": SDK_GO,
            "dashboard/src/.keep": "",
            "ui/src/.keep": "",
            "cmd/onemind/cli/.keep": "",
            "mobile/src/.keep": "",
            "exemptions.txt": "",
        }
        base.update(files)
        for rel, text in base.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(textwrap.dedent(text), encoding="utf-8")

    def problems(self):
        ops = sp.load_operations(self.root / "sdk/openapi/onemind-v1.json")
        result = sp.scan(self.root, ops)
        ex, errors = sp.load_exemptions(self.root / "exemptions.txt")
        return errors + sp.problems(ops, result, ex), result

    def close(self):
        self.tmp.cleanup()


ALL_COVERED_DASH = """
    const a = () => api.req('GET', '/v1/tokens');
    const b = () => api.req('POST', '/v1/tokens', body);
    const c = (id: string) => api.req('DELETE', `/v1/tokens/${encodeURIComponent(id)}`);
    const d = () => read(sdk, '/v1/tokens/builtin');
    const e = () => sdk.domains.list();
    const f = () => client.call({ method: 'GET', path: '/v1/actions' });
    const g = (id: string) => get(sdk, route('/v1/apps/{app_id}/logs', { app_id: id }));
"""
ALL_COVERED_CLI = """
    package cli
    func x() {
        a.gwDo(http.MethodPost, "/v1/tokens", body)
        c.Do(bg(), http.MethodDelete, "/v1/tokens/"+url.PathEscape(id), nil, &v)
    }
"""


class Recognition(unittest.TestCase):
    def run_repo(self, files):
        repo = FakeRepo(files)
        self.addCleanup(repo.close)
        return repo.problems()

    def test_covered_repo_is_clean(self):
        bad, _ = self.run_repo({"dashboard/src/a.ts": ALL_COVERED_DASH, "cmd/onemind/cli/a.go": ALL_COVERED_CLI})
        self.assertEqual(bad, [])

    def test_a_new_operation_without_a_screen_fails(self):
        bad, _ = self.run_repo({"dashboard/src/a.ts": ALL_COVERED_DASH.replace("sdk.domains.list()", "0"),
                                "cmd/onemind/cli/a.go": ALL_COVERED_CLI})
        self.assertEqual(len(bad), 1)
        self.assertIn("domains.list (GET /v1/domains) has no dashboard caller", bad[0])

    def test_a_write_without_a_command_fails(self):
        bad, _ = self.run_repo({"dashboard/src/a.ts": ALL_COVERED_DASH, "cmd/onemind/cli/a.go": "package cli\n"})
        self.assertEqual(sorted(b.split(" ")[0] for b in bad), ["tokens.create", "tokens.revoke"])
        self.assertTrue(all("has no cli caller" in b for b in bad))

    def test_the_http_method_matters(self):
        # A GET on the path does not stand for the POST on the same path.
        dash = ALL_COVERED_DASH.replace("api.req('POST', '/v1/tokens', body)", "api.req('GET', '/v1/tokens')")
        bad, _ = self.run_repo({"dashboard/src/a.ts": dash, "cmd/onemind/cli/a.go": ALL_COVERED_CLI})
        self.assertEqual([b.split(" ")[0] for b in bad], ["tokens.create"])

    def test_a_literal_segment_wins_over_a_parameter(self):
        _, result = self.run_repo({"dashboard/src/a.ts": "read(sdk, '/v1/tokens/builtin');\n"})
        self.assertTrue(result.has("dashboard", "tokens.builtin"))
        self.assertFalse(result.has("dashboard", "tokens.revoke"))

    def test_comments_tests_and_mocks_are_not_callers(self):
        files = {
            "dashboard/src/a.ts": "// api.req('GET', '/v1/domains')\n/* sdk.domains.list() */\nconst url = 'https://x//y';\n",
            "dashboard/src/a.test.ts": "sdk.domains.list();\n",
            "dashboard/src/api/mock.ts": "api.req('GET', '/v1/domains');\n",
            "dashboard/src/api/fixtures.ts": "api.req('GET', '/v1/domains');\n",
            "cmd/onemind/cli/a_test.go": 'package cli\nfunc t() { c.Do(bg(), http.MethodPost, "/v1/tokens", nil, nil) }\n',
        }
        _, result = self.run_repo(files)
        self.assertFalse(result.has("dashboard", "domains.list"))
        self.assertFalse(result.has("cli", "tokens.create"))

    def test_a_path_without_a_readable_method_is_not_a_caller_by_itself(self):
        _, result = self.run_repo({"dashboard/src/a.ts": "export const PATHS = { tokens: '/v1/tokens' };\n"})
        self.assertFalse(result.has("dashboard", "tokens.list"))
        self.assertFalse(result.has("dashboard", "tokens.create"))
        self.assertEqual({c.how for c in result.path_only("dashboard", "tokens.create")}, {"path-only"})

    # The rest of the dashboard and CLI, with /v1/tokens itself reached only through a table (path-only).
    TABLE_DASH = ALL_COVERED_DASH.replace("const a = () => api.req('GET', '/v1/tokens');\n", "") \
        .replace("api.req('POST', '/v1/tokens', body)", "api.req(METHOD, P.tokens, body)") + "    const P = { tokens: '/v1/tokens' };\n"
    INDIRECT = ("indirect dashboard tokens.list a.ts sends GET through req(METHOD, P.tokens)\n"
                "indirect dashboard tokens.create a.ts sends POST through req(METHOD, P.tokens)\n")

    def test_an_indirect_line_vouches_for_a_path_only_literal(self):
        files = {"dashboard/src/a.ts": self.TABLE_DASH, "cmd/onemind/cli/a.go": ALL_COVERED_CLI}
        bad, _ = self.run_repo(files)
        self.assertEqual(sorted(b.split(" ")[0] for b in bad), ["tokens.create", "tokens.list"])
        self.assertTrue(all("names its path but no HTTP method" in b for b in bad))
        bad, _ = self.run_repo({**files, "exemptions.txt": self.INDIRECT})
        self.assertEqual(bad, [])

    def test_a_new_method_on_a_path_with_only_path_only_callers_fails(self):
        # The hole the review found: DELETE /v1/tokens added next to the vouched GET and POST must fail on
        # the dashboard and the CLI, though both name the path.
        spec = json.loads(json.dumps(SPEC))
        spec["paths"]["/v1/tokens"]["delete"] = {"operationId": "tokens.wipe", "tags": ["tokens"]}
        cli = ALL_COVERED_CLI.replace("a.gwDo(http.MethodPost, \"/v1/tokens\", body)", "a.gwDo(m, tokensPath, body)") \
            + 'const tokensPath = "/v1/tokens"\n'
        files = {"sdk/openapi/onemind-v1.json": json.dumps(spec), "dashboard/src/a.ts": self.TABLE_DASH,
                 "cmd/onemind/cli/a.go": cli,
                 "exemptions.txt": self.INDIRECT + "indirect cli tokens.create a.go sends POST through gwDo(m, tokensPath)\n"}
        bad, _ = self.run_repo(files)
        self.assertEqual(len(bad), 2, bad)
        self.assertIn("tokens.wipe (DELETE /v1/tokens) has no dashboard caller", bad[0])
        self.assertIn("tokens.wipe (DELETE /v1/tokens) has no cli caller", bad[1])

    def test_an_indirect_line_goes_stale(self):
        files = {"dashboard/src/a.ts": self.TABLE_DASH, "cmd/onemind/cli/a.go": ALL_COVERED_CLI,
                 "exemptions.txt": self.INDIRECT}
        # A method-aware caller appears: the line must go.
        files["dashboard/src/b.ts"] = "api.req('GET', '/v1/tokens');\n"
        bad, _ = self.run_repo(files)
        self.assertEqual(bad, ["exemptions.txt:1: indirect dashboard tokens.list is stale, dashboard/src/b.ts now calls "
                               "it with its HTTP method: delete the line"])
        # The path-only literal disappears: the line must go (and the gap shows).
        del files["dashboard/src/b.ts"]
        files["dashboard/src/a.ts"] = self.TABLE_DASH.replace("const P = { tokens: '/v1/tokens' };", "")
        bad, _ = self.run_repo(files)
        self.assertIn("exemptions.txt:1: indirect dashboard tokens.list is stale, no dashboard file names /v1/tokens "
                      "any more: delete the line, or list the gap under a group", bad)
        self.assertIn("exemptions.txt:2: indirect dashboard tokens.create is stale, no dashboard file names /v1/tokens "
                      "any more: delete the line, or list the gap under a group", bad)

    def test_bad_indirect_lines_fail(self):
        ex = textwrap.dedent("""\
            group gap issue=#1 a gap with a long enough reason here
            indirect dashboard tokens.list too short
            indirect tablet tokens.list a reason that is long enough
            indirect dashboard domains.list a reason that is long enough
            dashboard domains.list gap
            indirect dashboard gone.op a reason that is long enough
            indirect dashboard tokens.builtin a reason that is long enough
            indirect dashboard tokens.builtin a reason that is long enough
            """)
        bad, _ = self.run_repo({"dashboard/src/a.ts": ALL_COVERED_DASH.replace("sdk.domains.list()", "0"),
                                "cmd/onemind/cli/a.go": ALL_COVERED_CLI, "exemptions.txt": ex})
        text = "\n".join(bad)
        self.assertEqual(text.count("an indirect line is"), 2)
        self.assertIn("dashboard domains.list is both indirect and exempt", text)
        self.assertIn("indirect gone.op is not in the spec any more", text)
        self.assertIn("indirect dashboard tokens.builtin is listed twice", text)
        self.assertIn("indirect dashboard tokens.builtin is stale", text)

    def test_a_compared_path_is_not_a_caller(self):
        # dashboard/src/files/api.ts: `location !== `/v1/files/uploads/${row.id}`` checks an address, it sends nothing.
        dash = ("if (location !== `/v1/tokens/${id}`) throw x;\n"
                "if (`/v1/tokens/${id}` === where) ok();\n"
                'if (p == "/v1/tokens/" + id) ok();\n')
        _, result = self.run_repo({"dashboard/src/a.ts": dash, "cmd/onemind/cli/a.go": 'package cli\nfunc x() { if p != "/v1/tokens/"+id {} }\n'})
        self.assertNotIn("tokens.revoke", result.callers.get("dashboard", {}))
        self.assertNotIn("tokens.revoke", result.callers.get("cli", {}))

    def test_go_paths_built_by_concatenation_and_sprintf(self):
        cli = 'package cli\nfunc x() {\n  a.gwDo(http.MethodDelete, fmt.Sprintf("/v1/tokens/%s", id), nil)\n  c.Do(bg(), http.MethodGet, "/v1/apps/"+url.PathEscape(id)+"/logs", nil, &v)\n}\n'
        _, result = self.run_repo({"cmd/onemind/cli/a.go": cli})
        self.assertTrue(result.has("cli", "tokens.revoke"))
        self.assertTrue(result.has("cli", "apps.logs"))

    def test_sdk_methods_count_for_the_operation_they_call(self):
        files = {"dashboard/src/a.tsx": "const d = await client.domains.list();\n",
                 "cmd/onemind/cli/a.go": "package cli\nfunc x() { c.Actions.List(bg()) }\n"}
        _, result = self.run_repo(files)
        self.assertEqual([c.how for c in result.callers["dashboard"]["domains.list"]], ["sdk:domains.list"])
        self.assertEqual([c.how for c in result.callers["cli"]["actions.list"]], ["sdk:Actions.List"])

    def test_a_hub_url_prefix_is_not_part_of_the_path(self):
        _, result = self.run_repo({"mobile/src/a.ts": "this.tus('GET', `${this.base}/v1/tokens/builtin?x=1`, {});\n",
                                   "mobile/src/b.ts": "const u = `${this.base}/v1/tokens/builtin?x=1`;\nfetch(u);\n"})
        self.assertTrue(result.has("mobile", "tokens.builtin"))
        self.assertEqual({c.file for c in result.path_only("mobile", "tokens.builtin")}, {"mobile/src/b.ts"})

    def test_an_exemption_covers_a_gap_and_goes_stale_when_the_caller_lands(self):
        ex = "group gap issue=#1 a gap with a long enough reason here\ndashboard domains.list gap\n"
        dash = ALL_COVERED_DASH.replace("sdk.domains.list()", "0")
        bad, _ = self.run_repo({"dashboard/src/a.ts": dash, "cmd/onemind/cli/a.go": ALL_COVERED_CLI, "exemptions.txt": ex})
        self.assertEqual(bad, [])
        bad, _ = self.run_repo({"dashboard/src/a.ts": ALL_COVERED_DASH, "cmd/onemind/cli/a.go": ALL_COVERED_CLI, "exemptions.txt": ex})
        self.assertEqual(bad, ["exemptions.txt:2: dashboard domains.list is stale, dashboard/src/a.ts now calls it: delete the line"])
        # Deleting the line then leaves the group empty, which must go too.
        bad, _ = self.run_repo({"dashboard/src/a.ts": ALL_COVERED_DASH, "cmd/onemind/cli/a.go": ALL_COVERED_CLI,
                                "exemptions.txt": ex.splitlines()[0] + "\n"})
        self.assertEqual(bad, ["exemptions.txt: group gap has no entries left: delete it"])

    def test_bad_exemption_lines_fail(self):
        ex = textwrap.dedent("""\
            group gap issue=#1 a gap with a long enough reason here
            group noissue a reason without an issue
            dashboard gone.op gap
            dashboard domains.list nosuchgroup
            cli tokens.list gap
            tablet tokens.list gap
            """)
        bad, _ = self.run_repo({"dashboard/src/a.ts": ALL_COVERED_DASH.replace("sdk.domains.list()", "0"),
                                "cmd/onemind/cli/a.go": ALL_COVERED_CLI, "exemptions.txt": ex})
        text = "\n".join(bad)
        self.assertIn("a group line is", text)
        self.assertIn("an exemption line is", text)
        self.assertIn("group nosuchgroup is not declared", text)
        self.assertIn("gone.op is not in the spec any more", text)
        self.assertIn("cli tokens.list is not required on cli", text)

    def test_the_mobile_scope_decides_what_the_phone_must_call(self):
        files = {"dashboard/src/a.ts": ALL_COVERED_DASH, "cmd/onemind/cli/a.go": ALL_COVERED_CLI,
                 "exemptions.txt": "mobile-scope actions /v1/actions\n"}
        bad, _ = self.run_repo(files)
        self.assertEqual(len(bad), 1)
        self.assertIn("actions.list (GET /v1/actions) has no mobile caller", bad[0])
        files["mobile/src/a.ts"] = "api.req('GET', '/v1/actions');\n"
        bad, _ = self.run_repo(files)
        self.assertEqual(bad, [])
        files["exemptions.txt"] = "mobile-scope nosuchtag\n"
        bad, _ = self.run_repo(files)
        self.assertEqual(bad, ["exemptions.txt: mobile-scope nosuchtag names no OpenAPI tag in the spec"])


if __name__ == "__main__":
    unittest.main()
