// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"strings"
	"testing"
	"time"
)

func TestFilesRename(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"POST /v1/files/ops": ok(map[string]any{"path": "/docs/b.txt"}),
	})
	outHas(t, run(t, "", false, "files", "rename", "/docs/a.txt", "b.txt", "--root", "home:usr_1").out, "Renamed /docs/a.txt to b.txt")
	b := g.sent("POST", "/v1/files/ops")[0].body
	if b["op"] != "rename" || b["root"] != "home:usr_1" || b["path"] != "/docs/a.txt" || b["name"] != "b.txt" || len(b) != 4 {
		t.Fatalf("rename body %+v", b)
	}
	if r := run(t, "", false, "files", "rename", "/a", "b"); r.code != ExitUsage {
		t.Fatalf("needs --root %+v", r)
	}
	if r := run(t, "", false, "files", "rename", "/a", "", "--root", "shared"); r.code != ExitUsage {
		t.Fatalf("empty name %+v", r)
	}
	if r := run(t, "", false, "files", "rename", "/a", "x/b", "--root", "shared"); r.code != ExitUsage {
		t.Fatalf("a name, not a path %+v", r)
	}
	if n := len(g.sent("POST", "/v1/files/ops")); n != 1 {
		t.Fatalf("refused calls must not reach the gateway, sent %d", n)
	}
}

func TestFilesRenamePrintsPendingOwnerRequest(t *testing.T) {
	newRouteGW(t, map[string]func(map[string]any) (int, any){
		"POST /v1/files/ops": func(map[string]any) (int, any) {
			return 202, map[string]any{"id": "frq_rename", "state": "awaiting_approval"}
		},
	})
	r := run(t, "", false, "files", "rename", "/a.txt", "b.txt", "--root", "shared")
	outHas(t, r.out, "Requested rename", "frq_rename", "An owner decides")
}

func TestFilesShareLinks(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/files/shares": ok([]any{map[string]any{"id": "shl_1", "name": "a.txt", "state": "active", "items": []any{map[string]any{"kind": "file"}}, "opened_count": 2.0, "expires_at": "2026-12-01T00:00:00Z"}}),
		"POST /v1/files/shares": func(map[string]any) (int, any) {
			return 202, map[string]any{"id": "frq_create", "state": "awaiting_approval", "one_time": map[string]any{"token": "oms_x", "url": "https://hub.test/v1/share/oms_x"}}
		},
		"DELETE /v1/files/shares/shl_1": func(map[string]any) (int, any) {
			return 202, map[string]any{"id": "frq_revoke", "state": "awaiting_approval"}
		},
	})
	out := run(t, "", false, "files", "share", "list").out
	outHas(t, out, "shl_1", "a.txt", "active", "2026-12-01")
	if strings.Contains(out, "oms_") {
		t.Fatalf("a listed link never shows its secret: %s", out)
	}
	before := time.Now().UTC()
	r := run(t, "longenough\n", false, "files", "share", "create", "/a.txt", "/b.txt", "--root", "shared", "--expires-in", "24h", "--name", "pics", "--password-stdin")
	outHas(t, r.out, "frq_create", "waiting for owner approval", "https://hub.test/v1/share/oms_x", "shown only now")
	b := g.sent("POST", "/v1/files/shares")[0]
	if b.idem != "" || b.body["name"] != "pics" || b.body["password"] != "longenough" {
		t.Fatalf("create %+v", b)
	}
	items := list(b.body["items"])
	if len(items) != 2 || obj(items[1])["root"] != "shared" || obj(items[1])["path"] != "/b.txt" {
		t.Fatalf("items %+v", b.body["items"])
	}
	exp, err := time.Parse(time.RFC3339, str(b.body["expires_at"]))
	if err != nil || exp.Sub(before) < 23*time.Hour || exp.Sub(before) > 25*time.Hour {
		t.Fatalf("expires_at %v %v", b.body["expires_at"], err)
	}
	if r := run(t, "", false, "files", "share", "create", "/a.txt"); r.code != ExitUsage {
		t.Fatalf("needs --root %+v", r)
	}
	for _, d := range []string{"1m", "5m", "359s", "719h1m", "720h", "800h"} {
		if r := run(t, "", false, "files", "share", "create", "/a.txt", "--root", "shared", "--expires-in", d); r.code != ExitUsage {
			t.Fatalf("%s must be refused %+v", d, r)
		}
	}
	// a password is never a flag: it would land in shell history and in /proc/PID/cmdline
	if r := run(t, "", false, "files", "share", "create", "/a.txt", "--root", "shared", "--password", "hunter2024"); r.code != ExitUsage {
		t.Fatalf("--password must not exist %+v", r)
	}
	if r := run(t, "short\n", false, "files", "share", "create", "/a.txt", "--root", "shared", "--password-stdin"); r.code != ExitUsage {
		t.Fatalf("short password %+v", r)
	}
	// 4 emoji are 4 characters (16 bytes): too short. 201 characters are too long.
	for _, pw := range []string{"😀😀😀😀", strings.Repeat("a", 201)} {
		if r := run(t, pw+"\n", false, "files", "share", "create", "/a.txt", "--root", "shared", "--password-stdin"); r.code != ExitUsage {
			t.Fatalf("password %d chars must be refused %+v", len([]rune(pw)), r)
		}
	}
	if r := run(t, "", false, "files", "share", "create", "/a.txt", "--root", "shared", "--password-stdin"); r.code != ExitUsage {
		t.Fatalf("empty stdin %+v", r)
	}
	if n := len(g.sent("POST", "/v1/files/shares")); n != 1 {
		t.Fatalf("refused calls must not reach the gateway, sent %d", n)
	}
	// the margins: the shortest and longest accepted choices stay inside the gateway's 5m..720h
	for _, d := range []string{"6m", "719h"} {
		if r := run(t, "", false, "files", "share", "create", "/a.txt", "--root", "shared", "--expires-in", d); r.code != 0 {
			t.Fatalf("%s must be accepted %+v", d, r)
		}
	}
	// the secret link: --json prints the gateway's body, -q prints only the URL
	if r := run(t, "", false, "--json", "files", "share", "create", "/a.txt", "--root", "shared"); r.code != 0 || !strings.Contains(r.out, `"one_time"`) || !strings.Contains(r.out, "oms_x") || strings.Contains(r.out, "shown only now") {
		t.Fatalf("--json %+v", r)
	}
	if r := run(t, "", false, "-q", "files", "share", "create", "/a.txt", "--root", "shared"); r.code != 0 || r.out != "https://hub.test/v1/share/oms_x\n" {
		t.Fatalf("-q %+v", r)
	}
	for _, p := range g.sent("POST", "/v1/files/shares") {
		if p.idem != "" {
			t.Fatalf("no Idempotency-Key on a create the gateway cannot replay: %q", p.idem)
		}
	}
	if r := run(t, "", false, "files", "share", "revoke", "shl_1"); r.code != ExitUsage {
		t.Fatalf("needs --yes %+v", r)
	}
	r = run(t, "", false, "files", "share", "revoke", "shl_1", "--yes")
	if r.code != 0 {
		t.Fatalf("revoke %+v", r)
	}
	outHas(t, r.out, "Requested end share link", "frq_revoke", "An owner decides")
	if len(g.sent("DELETE", "/v1/files/shares/shl_1")) != 1 {
		t.Fatal("one DELETE")
	}
}
