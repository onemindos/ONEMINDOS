// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// managedFixture is a hub whose apps and destinations come from the gateway:
// a "notes" app with one volume, and its database dump inside the shared
// PostgreSQL volume.
type managedFixture struct {
	*fixture
	signer *testSigner
	h      http.Handler
}

var (
	notesVol = VolumeRef{Namespace: "app-notes", Claim: "data", Volume: "pvc-1111"}
	pgVol    = VolumeRef{Namespace: "onemind-db", Claim: "data-postgres-0", Volume: "pvc-2222"}
	notesApp = AppSpec{ID: "notes", Revision: "2", Volumes: []VolumeRef{notesVol},
		Files: []VolumeFile{{VolumeRef: pgVol, Path: "onemind-dumps/app_notes.pgdump"}}}
)

func newManagedFixture(t *testing.T) *managedFixture {
	t.Helper()
	f := newFixture(t)
	c := f.cfg
	c.Targets = nil
	c.Units.Apps = nil
	c.StorageRoots = []string{f.path("storage")}
	c.Schedule.GatewayHourly = true
	f.cfg = c
	f.agent = f.newAgent(c)
	a := f.agent
	a.Units = func(context.Context) ([]Unit, error) { cc := a.conf(); return BuildUnits(&cc, fakeSQLite{}), nil }
	a.IsMount = func(string) (bool, error) { return true, nil }
	s := newTestSigner(t, f.root, f.clock)
	a.Jobs = &JobVerifier{PubKeyFile: s.pub, DonePath: f.path("state/jobs-done.json"), Now: func() time.Time { return f.clock }}
	f.write("storage/pvc-1111_app-notes_data/notes.txt", "v1")
	f.write("storage/pvc-1111_app-notes_data/sub/deep.txt", "deep-v1")
	f.write("storage/pvc-2222_onemind-db_data-postgres-0/onemind-dumps/app_notes.pgdump", "PGDMP-v1")
	f.write("storage/pvc-2222_onemind-db_data-postgres-0/pgdata/PG_VERSION", "17")
	return &managedFixture{fixture: f, signer: s, h: a.Handler(context.Background())}
}

func (m *managedFixture) do(t *testing.T, kind string, params any) (int, JobResult, []byte) {
	t.Helper()
	req := httptest.NewRequest("POST", "/api/v1/backup/jobs", bytes.NewReader(m.signer.job(t, kind, params)))
	req.RemoteAddr = "127.0.0.1:4000"
	w := httptest.NewRecorder()
	m.h.ServeHTTP(w, req)
	var r JobResult
	_ = json.Unmarshal(w.Body.Bytes(), &r)
	return w.Code, r, w.Body.Bytes()
}

func (m *managedFixture) ok(t *testing.T, kind string, params any) JobResult {
	t.Helper()
	code, r, body := m.do(t, kind, params)
	if code != 200 || r.State != StateSucceeded {
		t.Fatalf("%s: %d %s", kind, code, body)
	}
	return r
}

func usbTarget() map[string]any {
	return map[string]any{"targets": []map[string]any{{"id": "dst_usb", "kind": "usb", "name": "USB disk", "primary": true, "usb_uuid": "1234-ABCD"}}}
}

func TestConfigureWritesCredentialsAndKeepsThemOutOfManaged(t *testing.T) {
	m := newManagedFixture(t)
	// A node destination without its password is refused and changes nothing.
	code, r, _ := m.do(t, KindConfigure, map[string]any{"targets": []map[string]any{
		{"id": "dst_box", "kind": "node", "name": "Garage box", "primary": true, "url": "https://garage.example:8000/b/", "user": "box1"}}})
	if code != 200 || r.State != StateFailed || !strings.Contains(r.Error, "credentials were not provided") {
		t.Fatalf("missing credentials: %d %+v", code, r)
	}
	m.ok(t, KindConfigure, map[string]any{
		"targets": []map[string]any{
			{"id": "dst_usb", "kind": "usb", "name": "USB disk", "primary": true, "usb_uuid": "1234-ABCD"},
			{"id": "dst_box", "kind": "node", "name": "Garage box", "url": "https://garage.example:8000/b/", "user": "box1", "append_only": true}},
		"secrets": map[string]any{"dst_box": map[string]string{"password": "s3cr3t-value-for-test"}},
	})
	pw := m.path("state/secrets/dst_box.password")
	fi, err := os.Stat(pw)
	if err != nil || fi.Mode().Perm() != 0o600 {
		t.Fatalf("password file: %v %v", fi, err)
	}
	managed, _ := os.ReadFile(m.path("state/managed.json"))
	if bytes.Contains(managed, []byte("s3cr3t")) || !bytes.Contains(managed, []byte("dst_box.password")) {
		t.Fatalf("managed.json must name the file, never the secret: %s", managed)
	}
	// Reloading from disk gives the same destinations.
	c, err := LoadConfig(writeAgentJSON(t, m.fixture))
	if err != nil || len(c.Targets) != 2 || c.Targets[1].PasswordFile != pw {
		t.Fatalf("reload: %+v %v", c.Targets, err)
	}
	// Dropping the node destination deletes its credentials.
	m.ok(t, KindConfigure, usbTarget())
	if _, err := os.Stat(pw); !os.IsNotExist(err) {
		t.Fatalf("removed destination's password kept: %v", err)
	}
}

func writeAgentJSON(t *testing.T, f *fixture) string {
	t.Helper()
	b, _ := json.Marshal(f.cfg)
	p := f.path("agent.json")
	if err := os.WriteFile(p, b, 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestGatewayAppsMayNotNameHostPaths(t *testing.T) {
	m := newManagedFixture(t)
	m.ok(t, KindConfigure, usbTarget())
	code, r, _ := m.do(t, KindRun, map[string]any{"reason": "manual", "apps": []map[string]any{{"id": "x", "paths": []string{"/etc"}}}})
	if code != 200 || r.State != StateFailed || !strings.Contains(r.Error, "host paths") {
		t.Fatalf("host path accepted: %d %+v", code, r)
	}
	code, r, _ = m.do(t, KindRun, map[string]any{"reason": "manual", "apps": []map[string]any{{"id": "x",
		"files": []map[string]any{{"namespace": "a", "claim": "b", "volume": "c", "path": "../../etc/shadow"}}}}})
	if r.State != StateFailed || !strings.Contains(r.Error, "clean relative path") {
		t.Fatalf("escaping file accepted: %d %+v", code, r)
	}
}

func appRun(t *testing.T, m *managedFixture, reason string) Run {
	t.Helper()
	r := m.ok(t, KindRun, map[string]any{"reason": reason, "apps": []AppSpec{notesApp}, "units": []string{"app:notes"}})
	b, _ := json.Marshal(r.Result)
	var run Run
	_ = json.Unmarshal(b, &run)
	if run.State != StateSucceeded || len(run.Units) != 1 {
		t.Fatalf("run: %+v", run)
	}
	return run
}

func TestAppRestoreSwapsVolumesAndDumpThenCommitOrRollBack(t *testing.T) {
	m := newManagedFixture(t)
	m.ok(t, KindConfigure, usbTarget())
	good := appRun(t, m, ReasonManual)
	snap := good.Units[0].SnapshotID

	// The data breaks.
	m.clock = m.clock.Add(time.Hour)
	m.signer.now = m.clock
	m.write("storage/pvc-1111_app-notes_data/notes.txt", "BROKEN")
	_ = os.Remove(m.path("storage/pvc-1111_app-notes_data/sub/deep.txt"))
	m.write("storage/pvc-2222_onemind-db_data-postgres-0/onemind-dumps/app_notes.pgdump", "PGDMP-broken")

	// The gateway takes the pre-restore snapshot, then restores.
	pre := appRun(t, m, ReasonPreRestore).Units[0].SnapshotID
	stamp := "20261112T113000Z"
	r := m.ok(t, KindRestore, map[string]any{"scope": "app", "app_id": "notes", "snapshot_id": snap[:12], "stamp": stamp})
	b, _ := json.Marshal(r.Result)
	var res AppRestoreResult
	_ = json.Unmarshal(b, &res)
	if len(res.Items) != 2 || !res.Items[0].Restored || !res.Items[1].Restored {
		t.Fatalf("restore result: %+v", res)
	}
	if m.read("storage/pvc-1111_app-notes_data/notes.txt") != "v1" || m.read("storage/pvc-1111_app-notes_data/sub/deep.txt") != "deep-v1" {
		t.Fatal("volume not restored")
	}
	if m.read("storage/pvc-2222_onemind-db_data-postgres-0/onemind-dumps/app_notes.pgdump") != "PGDMP-v1" {
		t.Fatal("dump not restored")
	}
	if m.read("storage/pvc-2222_onemind-db_data-postgres-0/pgdata/PG_VERSION") != "17" {
		t.Fatal("the rest of the shared database volume must not be touched")
	}
	if m.read("storage/pvc-1111_app-notes_data.onemind-old-"+stamp+"/notes.txt") != "BROKEN" {
		t.Fatal("live data must be kept aside until the restore is finished")
	}

	// The app did not come back healthy: roll back.
	m.ok(t, KindRestoreFinish, map[string]any{"app_id": "notes", "stamp": stamp, "commit": false})
	if m.read("storage/pvc-1111_app-notes_data/notes.txt") != "BROKEN" ||
		m.read("storage/pvc-2222_onemind-db_data-postgres-0/onemind-dumps/app_notes.pgdump") != "PGDMP-broken" {
		t.Fatal("rollback did not put the live data back")
	}

	// Restore again and commit: the moved-aside copy is deleted, the
	// pre-restore snapshot still holds it (undo).
	m.ok(t, KindRestore, map[string]any{"scope": "app", "app_id": "notes", "snapshot_id": snap, "stamp": stamp})
	m.ok(t, KindRestoreFinish, map[string]any{"app_id": "notes", "stamp": stamp, "commit": true})
	if _, err := os.Stat(m.path("storage/pvc-1111_app-notes_data.onemind-old-" + stamp)); !os.IsNotExist(err) {
		t.Fatalf("old copy kept after commit: %v", err)
	}
	m.ok(t, KindRestore, map[string]any{"scope": "app", "app_id": "notes", "snapshot_id": pre, "stamp": "20261112T114000Z"})
	if m.read("storage/pvc-1111_app-notes_data/notes.txt") != "BROKEN" {
		t.Fatal("restoring the pre-restore snapshot must undo the restore")
	}
}

func TestAppRestoreAfterReinstallMatchesClaimNotVolume(t *testing.T) {
	m := newManagedFixture(t)
	m.ok(t, KindConfigure, usbTarget())
	snap := appRun(t, m, ReasonManual).Units[0].SnapshotID
	// The app was removed (Retain keeps pvc-1111) and installed again: new PV.
	m.write("storage/pvc-9999_app-notes_data/notes.txt", "fresh install")
	reinstalled := notesApp
	reinstalled.Volumes = []VolumeRef{{Namespace: "app-notes", Claim: "data", Volume: "pvc-9999"}}
	if err := m.agent.SetApps([]AppSpec{reinstalled}); err != nil {
		t.Fatal(err)
	}
	m.ok(t, KindRestore, map[string]any{"scope": "app", "app_id": "notes", "snapshot_id": snap, "stamp": "20261112T120000Z"})
	if m.read("storage/pvc-9999_app-notes_data/notes.txt") != "v1" {
		t.Fatal("restore must land in the current volume of the same claim")
	}
}

func TestRestoreRefusesOtherAppsSnapshot(t *testing.T) {
	m := newManagedFixture(t)
	m.ok(t, KindConfigure, usbTarget())
	run := m.ok(t, KindRun, map[string]any{"reason": "manual", "apps": []AppSpec{notesApp}, "units": []string{"system"}})
	b, _ := json.Marshal(run.Result)
	var r Run
	_ = json.Unmarshal(b, &r)
	_, res, _ := m.do(t, KindRestore, map[string]any{"scope": "app", "app_id": "notes", "snapshot_id": r.Units[0].SnapshotID, "stamp": "20261112T120000Z"})
	if res.State != StateFailed || !strings.Contains(res.Error, "not app:notes") {
		t.Fatalf("restored a system snapshot over an app: %+v", res)
	}
}

func TestJobsBrowseVerifyStatusAndKeys(t *testing.T) {
	m := newManagedFixture(t)
	m.ok(t, KindConfigure, usbTarget())
	snap := appRun(t, m, ReasonManual).Units[0].SnapshotID

	r := m.ok(t, KindSnapshots, map[string]any{"unit": "app:notes"})
	if b, _ := json.Marshal(r.Result); !strings.Contains(string(b), snap) {
		t.Fatalf("snapshots: %s", b)
	}
	dir := filepath.ToSlash(m.path("storage/pvc-1111_app-notes_data"))
	r = m.ok(t, KindTree, map[string]any{"snapshot_id": snap, "path": dir})
	if b, _ := json.Marshal(r.Result); !strings.Contains(string(b), `"name":"notes.txt"`) {
		t.Fatalf("tree: %s", b)
	}

	req := httptest.NewRequest("POST", "/api/v1/backup/jobs", bytes.NewReader(m.signer.job(t, KindFile, map[string]any{"snapshot_id": snap, "path": dir + "/notes.txt"})))
	req.RemoteAddr = "127.0.0.1:4000"
	w := httptest.NewRecorder()
	m.h.ServeHTTP(w, req)
	if body, _ := io.ReadAll(w.Body); w.Code != 200 || string(body) != "v1" || w.Header().Get("Content-Length") != "2" {
		t.Fatalf("file: %d %q %v", w.Code, body, w.Header())
	}

	// A badge is green only after a verified (scratch) restore.
	badge := func() string {
		b, _ := json.Marshal(m.ok(t, KindStatus, map[string]any{}).Result)
		var out struct{ Status Status }
		_ = json.Unmarshal(b, &out)
		return out.Status.Units["app:notes"].State
	}
	if got := badge(); got != BadgeUnverified {
		t.Fatalf("before verify: %s", got)
	}
	v := m.ok(t, KindVerify, map[string]any{"mode": "restore", "units": []string{"app:notes"}, "latest": true})
	if b, _ := json.Marshal(v.Result); !strings.Contains(string(b), `"verdict":"passed"`) {
		t.Fatalf("verify: %s", b)
	}
	if got := badge(); got != BadgeVerified {
		t.Fatalf("after verify: %s", got)
	}

	k := m.ok(t, KindKeyAdd, map[string]any{"which": "owner", "key": strings.Repeat("ABCD", 13)})
	if b, _ := json.Marshal(k.Result); !strings.Contains(string(b), `"ok":true`) {
		t.Fatalf("key add: %s", b)
	}
	if entries, _ := os.ReadDir(m.path("state")); func() bool {
		for _, e := range entries {
			if strings.HasPrefix(e.Name(), ".key-") {
				return true
			}
		}
		return false
	}() {
		t.Fatal("the key's temporary file must be removed")
	}

	if code, _, _ := m.do(t, "backup.nonsense", map[string]any{}); code != http.StatusBadRequest {
		t.Fatalf("unknown kind: %d", code)
	}
	if code, _, _ := m.do(t, KindRun, map[string]any{"reason": "manual", "surprise": 1}); code != http.StatusBadRequest {
		t.Fatalf("unknown param: %d", code)
	}
}

func TestUnsignedJobIsRefused(t *testing.T) {
	m := newManagedFixture(t)
	env := m.signer.envelope(t, KindRestore, map[string]any{"scope": "path", "snapshot_id": "x", "path": "/etc/passwd"})
	env["sig"] = "AAAA"
	b, _ := json.Marshal(env)
	req := httptest.NewRequest("POST", "/api/v1/backup/jobs", bytes.NewReader(b))
	req.RemoteAddr = "127.0.0.1:4000"
	w := httptest.NewRecorder()
	m.h.ServeHTTP(w, req)
	if w.Code != http.StatusForbidden {
		t.Fatalf("unsigned job: %d %s", w.Code, w.Body)
	}
}

func TestRunSkipsUnitsTheGatewayCouldNotPrepare(t *testing.T) {
	m := newManagedFixture(t)
	m.ok(t, KindConfigure, usbTarget())
	r := m.ok(t, KindRun, map[string]any{"reason": "manual", "apps": []AppSpec{notesApp}, "skip_units": []string{"app:notes"}})
	b, _ := json.Marshal(r.Result)
	var run Run
	_ = json.Unmarshal(b, &run)
	for _, u := range run.Units {
		if u.Unit == "app:notes" {
			t.Fatalf("a skipped unit was backed up: %+v", run.Units)
		}
	}
	if len(run.Units) == 0 {
		t.Fatal("the other units must still run")
	}
}
