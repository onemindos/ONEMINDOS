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
	if r := run(t, "", false, "files", "rename", "/a", "x/b", "--root", "shared"); r.code != ExitUsage {
		t.Fatalf("a name, not a path %+v", r)
	}
	if n := len(g.sent("POST", "/v1/files/ops")); n != 1 {
		t.Fatalf("refused calls must not reach the gateway, sent %d", n)
	}
}

func TestFilesShareLinks(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/files/shares": ok([]any{map[string]any{"id": "shl_1", "name": "a.txt", "state": "active", "items": []any{map[string]any{"kind": "file"}}, "opened_count": 2.0, "expires_at": "2026-12-01T00:00:00Z"}}),
		"POST /v1/files/shares": func(map[string]any) (int, any) {
			return 201, map[string]any{"id": "shl_2", "expires_at": "2026-12-01T00:00:00Z", "one_time": map[string]any{"token": "oms_x", "url": "https://hub.test/v1/share/oms_x"}}
		},
		"DELETE /v1/files/shares/shl_1": ok(map[string]any{"id": "shl_1", "state": "revoked"}),
	})
	out := run(t, "", false, "files", "share", "list").out
	outHas(t, out, "shl_1", "a.txt", "active", "2026-12-01")
	if strings.Contains(out, "oms_") {
		t.Fatalf("a listed link never shows its secret: %s", out)
	}
	before := time.Now().UTC()
	r := run(t, "", false, "files", "share", "create", "/a.txt", "/b.txt", "--root", "shared", "--expires-in", "24h", "--name", "pics", "--password", "longenough")
	outHas(t, r.out, "shl_2", "https://hub.test/v1/share/oms_x", "shown only now")
	b := g.sent("POST", "/v1/files/shares")[0]
	if b.idem == "" || b.body["name"] != "pics" || b.body["password"] != "longenough" {
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
	if r := run(t, "", false, "files", "share", "create", "/a.txt", "--root", "shared", "--expires-in", "1m"); r.code != ExitUsage {
		t.Fatalf("too short %+v", r)
	}
	if r := run(t, "", false, "files", "share", "create", "/a.txt", "--root", "shared", "--expires-in", "800h"); r.code != ExitUsage {
		t.Fatalf("too long %+v", r)
	}
	if n := len(g.sent("POST", "/v1/files/shares")); n != 1 {
		t.Fatalf("refused calls must not reach the gateway, sent %d", n)
	}
	if r := run(t, "", false, "files", "share", "revoke", "shl_1"); r.code != ExitUsage {
		t.Fatalf("needs --yes %+v", r)
	}
	if r := run(t, "", false, "files", "share", "revoke", "shl_1", "--yes"); r.code != 0 {
		t.Fatalf("revoke %+v", r)
	}
	if len(g.sent("DELETE", "/v1/files/shares/shl_1")) != 1 {
		t.Fatal("one DELETE")
	}
}
