// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"
)

// BT-1: one run makes a snapshot per unit, tagged so the repository explains
// itself without OneMind, and retention runs per unit and keep class.
func TestRunTagsEveryUnitAndAppliesRetention(t *testing.T) {
	f := newFixture(t)
	r := f.run(ReasonScheduled)
	if r.State != StateSucceeded || len(r.Units) != 4 {
		t.Fatalf("run = %+v", r)
	}
	want := map[string][]string{
		"system":     {"audit_head=" + strings.Repeat("0", 63) + "3"},
		"k3s":        {"k3s=v1.33.5-k3s1"},
		"app:photos": {"app=photos", "rev=r3"},
		"node:node1": nil,
	}
	for _, u := range r.Units {
		snaps, _ := f.repo.Snapshots(context.Background(), []string{"unit=" + u.Unit})
		if len(snaps) != 1 || snaps[0].ID != u.SnapshotID {
			t.Fatalf("unit %s: snapshots %v", u.Unit, snaps)
		}
		tags := snaps[0].Tags
		base := []string{"onemind", "box=box1", "gen=0", "node=node1", "run=" + r.ID, "reason=scheduled", "keep=ladder"}
		for _, w := range append(base, want[u.Unit]...) {
			if !slices.Contains(tags, w) {
				t.Errorf("unit %s: tag %q missing in %v", u.Unit, w, tags)
			}
		}
		if snaps[0].Hostname != "node1" {
			t.Errorf("host = %q, want the node id (no real hostname in the repo)", snaps[0].Hostname)
		}
	}
	if len(f.repo.forgets) != 4 {
		t.Fatalf("forget calls = %d, want one per unit", len(f.repo.forgets))
	}
	got := strings.Join(f.repo.forgets[0], " ")
	if got != "onemind box=box1 unit=system keep=ladder --keep-hourly 24 --keep-daily 7 --keep-weekly 4 --keep-monthly 12" {
		t.Fatalf("forget = %q", got)
	}
	// staging is cleaned after the run, and the half-written audit line was not copied
	if _, err := os.Stat(filepath.Join(f.cfg.StateDir, "staging", "system")); !os.IsNotExist(err) {
		t.Fatalf("staging left behind: %v", err)
	}
}

func TestPreUpdateSnapshotsKeepByAge(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonPreUpdate)
	if got := strings.Join(f.repo.forgets[0], " "); !strings.Contains(got, "keep=14d --keep-within 14d") {
		t.Fatalf("forget = %q", got)
	}
}

// BT-2: a damaged k3s datastore fails its unit, writes no k3s snapshot, and
// the run is partial.
func TestK3sIntegrityFailureFailsUnitOnly(t *testing.T) {
	f := newFixture(t)
	f.write("k3s/state.db", "CORRUPT")
	r := f.run(ReasonScheduled)
	if r.State != StatePartial {
		t.Fatalf("state = %s", r.State)
	}
	for _, u := range r.Units {
		if u.Unit == "k3s" && (u.State != StateFailed || u.SnapshotID != "" || !strings.Contains(u.Error, "integrity check")) {
			t.Fatalf("k3s unit = %+v", u)
		}
	}
	if s, _ := f.repo.Snapshots(context.Background(), []string{"unit=k3s"}); len(s) != 0 {
		t.Fatal("a k3s snapshot was written")
	}
}

func TestBrokenAuditChainFailsSystemUnit(t *testing.T) {
	f := newFixture(t)
	f.write("data/onemind/audit/audit.jsonl", auditLines(2)+`{"seq":3,"prev_hash":"`+strings.Repeat("f", 64)+`","hash":"`+strings.Repeat("e", 64)+`"}`+"\n")
	r := f.run(ReasonScheduled)
	if r.Units[0].Unit != "system" || r.Units[0].State != StateFailed || !strings.Contains(r.Units[0].Error, "chain broken") {
		t.Fatalf("system = %+v", r.Units[0])
	}
}

func TestMissingSourceFailsUnit(t *testing.T) {
	f := newFixture(t)
	os.RemoveAll(f.path("data/onemind/identity"))
	r := f.run(ReasonManual)
	if r.State != StatePartial || r.Units[3].State != StateFailed {
		t.Fatalf("run = %+v", r)
	}
}

func TestAllUnitsFailIsFailed(t *testing.T) {
	f := newFixture(t)
	f.repo.backupErr = &ResticError{Op: "backup", ExitCode: 1, Stderr: "boom"}
	if r := f.run(ReasonManual); r.State != StateFailed {
		t.Fatalf("state = %s", r.State)
	}
}

// BT-12 (source side): the box never runs forget against an append-only target.
func TestAppendOnlyTargetIsNeverForgotten(t *testing.T) {
	f := newFixture(t)
	if _, err := f.agent.Run(context.Background(), RunRequest{Reason: ReasonManual, TargetID: "peer"}); err != nil {
		t.Fatal(err)
	}
	if len(f.repo.forgets) != 0 {
		t.Fatalf("forget ran on append-only target: %v", f.repo.forgets)
	}
	if err := f.agent.Prune(context.Background(), "peer"); !errors.Is(err, errAppendOnly) {
		t.Fatalf("prune = %v", err)
	}
}

// BT-9: once a restored box wrote a newer fence, the old box stops.
func TestFenceStopsReplacedBox(t *testing.T) {
	f := newFixture(t)
	c := f.cfg
	c.Generation = 1
	restored := f.newAgent(c)
	if err := restored.WriteFence(context.Background(), ""); err != nil {
		t.Fatal(err)
	}
	before := len(f.repo.snaps)
	r := f.run(ReasonScheduled)
	if r.State != StateRefused || !strings.Contains(r.Error, "replaced by a restore") || len(f.repo.snaps) != before {
		t.Fatalf("run = %+v, snapshots %d -> %d", r, before, len(f.repo.snaps))
	}
	if s, _ := f.agent.Status(context.Background()); !s.Fenced || s.Box.State != BadgeFailing {
		t.Fatalf("status = %+v", s)
	}
	// the restored box itself keeps working
	if _, err := restored.Run(context.Background(), RunRequest{Reason: ReasonManual}); err != nil {
		t.Fatal(err)
	}
}

// BT-14: too little room refuses the run and says how much is needed.
func TestSpaceCheckRefusesWithNeededSize(t *testing.T) {
	f := newFixture(t)
	f.agent.FreeBytes = func(string) (int64, error) { return 10, nil }
	r := f.run(ReasonScheduled)
	if r.State != StateRefused || !strings.Contains(r.Error, "bytes needed") || len(f.repo.snaps) != 0 {
		t.Fatalf("run = %+v", r)
	}
	// after a successful run only growth counts
	f.agent.FreeBytes = func(string) (int64, error) { return 1 << 30, nil }
	f.run(ReasonScheduled)
	f.agent.FreeBytes = func(string) (int64, error) { return 10, nil }
	if r := f.run(ReasonScheduled); r.State != StateSucceeded {
		t.Fatalf("no growth but refused: %+v", r)
	}
}

func TestUnmountedUSBIsRefused(t *testing.T) {
	f := newFixture(t)
	f.agent.Cfg.Targets[0].AllowNonMountDir = false
	f.agent.IsMount = func(string) (bool, error) { return false, nil }
	if r := f.run(ReasonScheduled); r.State != StateFailed || !strings.Contains(r.Error, "not mounted") {
		t.Fatalf("run = %+v", r)
	}
}

func TestBusyAndHeartbeat(t *testing.T) {
	f := newFixture(t)
	if h := f.agent.Heartbeat(); h.Running || h.LastRunAt != nil || h.LastResult != "none" {
		t.Fatalf("heartbeat = %+v", h)
	}
	if !f.agent.tryAcquire("x") {
		t.Fatal("acquire")
	}
	if _, err := f.agent.Run(context.Background(), RunRequest{Reason: ReasonManual}); !errors.Is(err, ErrBusy) {
		t.Fatalf("err = %v", err)
	}
	if !f.agent.Heartbeat().Running {
		t.Fatal("not running")
	}
	f.agent.release()
	f.run(ReasonManual)
	h := f.agent.Heartbeat()
	b, _ := json.Marshal(h)
	if string(b) != `{"running":false,"last_run_at":"2026-11-12T10:30:00Z","last_result":"succeeded"}` {
		t.Fatalf("heartbeat json = %s", b)
	}
}

func TestStatePersistsAcrossRestart(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	again := f.newAgent(f.cfg)
	if h := again.Heartbeat(); h.LastResult != StateSucceeded {
		t.Fatalf("after restart: %+v", h)
	}
	fi, err := os.Stat(filepath.Join(f.cfg.StateDir, "state.json"))
	if err != nil || fi.Mode().Perm() != 0o600 {
		t.Fatalf("state file mode: %v %v", fi, err)
	}
}

func TestAPI(t *testing.T) {
	f := newFixture(t)
	h := f.agent.Handler(context.Background())
	do := func(remote, method, path, body string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(method, path, strings.NewReader(body))
		req.RemoteAddr = remote
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)
		return w
	}
	if w := do("192.0.2.1:5000", "GET", "/api/v1/backup/status", ""); w.Code != http.StatusForbidden {
		t.Fatalf("remote caller: %d", w.Code)
	}
	if w := do("127.0.0.1:5000", "POST", "/api/v1/backup/run", `{"reason":"scheduled"}`); w.Code != http.StatusBadRequest {
		t.Fatalf("scheduled over API: %d", w.Code)
	}
	w := do("127.0.0.1:5000", "POST", "/api/v1/backup/run", `{"reason":"pre-update","wait":true}`)
	var out map[string]string
	_ = json.Unmarshal(w.Body.Bytes(), &out)
	if w.Code != 200 || out["state"] != StateSucceeded || !strings.HasPrefix(out["run_id"], "run_") {
		t.Fatalf("run: %d %s", w.Code, w.Body)
	}
	w = do("[::1]:5000", "GET", "/api/v1/backup/status", "")
	var s Status
	if err := json.Unmarshal(w.Body.Bytes(), &s); err != nil || s.LastRun == nil || s.LastRun.Reason != ReasonPreUpdate {
		t.Fatalf("status: %v %s", err, w.Body)
	}
	if !s.NextRun.Equal(time.Date(2026, 11, 12, 11, 17, 0, 0, time.UTC)) {
		t.Fatalf("next run = %v", s.NextRun)
	}
}

func TestGenerateKey(t *testing.T) {
	p := filepath.Join(t.TempDir(), "k")
	if err := GenerateKey(p); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(p)
	fi, _ := os.Stat(p)
	if len(bytes.TrimSpace(b)) != 64 || fi.Mode().Perm() != 0o600 {
		t.Fatalf("key %q mode %v", b, fi.Mode())
	}
	if err := GenerateKey(p); err == nil {
		t.Fatal("overwrote an existing key")
	}
	if err := checkKeyFile(p); err != nil {
		t.Fatal(err)
	}
	_ = os.Chmod(p, 0o644)
	if err := checkKeyFile(p); err == nil {
		t.Fatal("world-readable key accepted")
	}
}
