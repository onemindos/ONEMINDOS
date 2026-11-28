// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

type storageGW struct {
	mu      sync.Mutex
	log     []rec
	blocked bool
}

func newStorageGW(t *testing.T, token string) *storageGW {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", token)
	g := &storageGW{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		g.mu.Lock()
		defer g.mu.Unlock()
		var body map[string]any
		if raw, _ := io.ReadAll(r.Body); len(raw) > 0 {
			_ = json.Unmarshal(raw, &body)
		}
		g.log = append(g.log, rec{r.Method, r.URL.Path, r.URL.RawQuery, body, r.Header.Get("Idempotency-Key")})
		plan := map[string]any{"blocked": g.blocked, "encrypted": true, "steps": []any{map[string]any{}, map[string]any{}},
			"targets":  []any{map[string]any{"path": "/dev/sdb", "model": "Blank HDD", "size_bytes": 4e12}},
			"checks":   []any{map[string]any{"id": "blank", "ok": !g.blocked, "detail": "the disk is blank"}},
			"warnings": []any{"Copying takes a day."}}
		switch {
		case r.URL.Path == "/v1/storage/plans":
			jsonOut(w, 200, map[string]any{"type": body["type"], "risk": "destructive", "plan": plan, "plan_sha256": "abc"})
		case r.URL.Path == "/v1/storage/actions":
			if token != ownerTok {
				jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "agent/agent may not request storage.mirror.remove"})
				return
			}
			jsonOut(w, 202, map[string]any{"action": map[string]any{"id": "act_4", "state": "awaiting_approval", "type": body["type"]}, "plan": plan})
		case r.URL.Path == "/v1/storage/operations/act_4":
			jsonOut(w, 200, map[string]any{"type": "storage.mirror.add", "state": "running", "risk": "destructive", "journal": []any{map[string]any{"step": "wipe", "state": "done", "detail": nil}}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	return g
}

func (g *storageGW) count(path string) int {
	g.mu.Lock()
	defer g.mu.Unlock()
	n := 0
	for _, r := range g.log {
		if r.path == path {
			n++
		}
	}
	return n
}

func TestStorageRequestShowsThePlanThenFilesOnlyARequest(t *testing.T) {
	g := newStorageGW(t, ownerTok)
	r := run(t, "", false, "storage", "request", "add", "--device", "/dev/sdb")
	if r.code != 0 || !strings.Contains(r.out, "would erase and use: /dev/sdb") || !strings.Contains(r.out, "Copying takes a day.") || !strings.Contains(r.out, "Waiting for an owner") {
		t.Fatalf("request %+v", r)
	}
	if g.count("/v1/storage/plans") != 1 || g.count("/v1/storage/actions") != 1 {
		t.Fatalf("plan then request expected: %+v", g.log)
	}
	post := g.log[1]
	if post.body["type"] != "storage.mirror.add" || obj(post.body["params"])["device"] != "/dev/sdb" || post.idem == "" || post.body["approve"] != nil {
		t.Fatalf("body %+v", post)
	}
	for _, c := range g.log {
		if strings.Contains(c.path, "approve") {
			t.Fatalf("must never approve: %+v", c)
		}
	}
}

func TestStorageRequestDryRunFilesNothing(t *testing.T) {
	g := newStorageGW(t, ownerTok)
	r := run(t, "", false, "storage", "request", "repair", "--dry-run")
	if r.code != 0 || !strings.Contains(r.out, "Dry run: nothing was filed") || g.count("/v1/storage/actions") != 0 {
		t.Fatalf("dry run %+v / %+v", r, g.log)
	}
}

func TestStorageRequestStopsWhenTheBoxBlocksThePlan(t *testing.T) {
	g := newStorageGW(t, ownerTok)
	g.blocked = true
	r := run(t, "", false, "storage", "request", "add", "--device", "/dev/sdb")
	if r.code != ExitConflict || !strings.Contains(r.errOut, "safety check failed") || g.count("/v1/storage/actions") != 0 {
		t.Fatalf("blocked %+v / %+v", r, g.log)
	}
}

func TestStorageRequestRejectsBadInputBeforeAnyRequest(t *testing.T) {
	g := newStorageGW(t, ownerTok)
	for _, args := range [][]string{{"storage", "request", "explode"}, {"storage", "request", "add"}, {"storage", "request", "replace", "--device", "/dev/sdb"}} {
		if r := run(t, "", false, args...); r.code != ExitUsage {
			t.Fatalf("%v: %+v", args, r)
		}
	}
	if len(g.log) != 0 {
		t.Fatalf("no request expected: %+v", g.log)
	}
}

func TestStorageRequestIsRefusedForAnAgentWhereTheGatewayRefuses(t *testing.T) {
	newStorageGW(t, agentTok)
	if r := run(t, "", false, "storage", "request", "remove", "--member", "devid:2"); r.code == 0 || !strings.Contains(r.errOut, "may not request") {
		t.Fatalf("agent %+v", r)
	}
}

func TestStorageOperationAndTheLocalSubcommandsStillWork(t *testing.T) {
	newStorageGW(t, ownerTok)
	if r := run(t, "", false, "storage", "operation", "act_4"); r.code != 0 || !strings.Contains(r.out, "running") || !strings.Contains(r.out, "wipe") {
		t.Fatalf("operation %+v", r)
	}
	// The older local commands keep their own flag parsing: an unknown one is still an error, not a crash.
	if r := run(t, "", false, "storage", "disks", "--bogus"); r.code == 0 {
		t.Fatalf("local parser lost: %+v", r)
	}
}

// Disk sizes read like a disk label, in TB from 1000 GB up; the dashboard's diskSize test checks the same values.
func TestStorageSizeReadsLikeADiskLabel(t *testing.T) {
	for in, want := range map[float64]string{256e9: "256 GB", 1.5e12: "1.5 TB", 4e12: "4 TB", 999.96e9: "1 TB"} {
		if got := storageSize(in); got != want {
			t.Errorf("storageSize(%v) = %q, want %q", in, got, want)
		}
	}
	if got := storageSize(nil); got != "size not reported" {
		t.Errorf("nil: %q", got)
	}
}
