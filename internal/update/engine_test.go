// SPDX-License-Identifier: Apache-2.0

package update

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/update/tuftest"
)

// --- fakes -------------------------------------------------------------

type calls struct{ log []string }

type fakeRAUC struct {
	c       *calls
	gateDir string
	err     error
}

// Install mimics RAUC + the pre-install handler: it writes the trial marker
// "<slot> <version>" read from the bundle (our fake bundles contain the version).
func (f *fakeRAUC) Install(_ context.Context, bundle string) error {
	f.c.log = append(f.c.log, "install "+filepath.Base(bundle))
	if f.err != nil {
		return f.err
	}
	b, err := os.ReadFile(bundle)
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(f.gateDir, "pending"), []byte("B "+strings.TrimPrefix(string(b), "bundle ")+"\n"), 0o644)
}

type fakeSnap struct {
	c   *calls
	err error
}

func (f *fakeSnap) Snapshot(_ context.Context, from, to string) (string, error) {
	f.c.log = append(f.c.log, "snapshot "+from+"->"+to)
	return "abc123", f.err
}

type fakeReboot struct{ c *calls }

func (f *fakeReboot) Reboot(context.Context) error { f.c.log = append(f.c.log, "reboot"); return nil }

// --- fixture -----------------------------------------------------------

type fixture struct {
	t      *testing.T
	dir    string
	repo   *tuftest.Repo
	srv    *httptest.Server
	cfg    *Config
	calls  *calls
	eng    *Engine
	served string // repo directory served over HTTP
}

const curVersion = "0.1.0"

func bundle(v string) []byte { return []byte("bundle " + v) }

func newFixture(t *testing.T, channel string, conf string) *fixture {
	t.Helper()
	f := &fixture{t: t, dir: t.TempDir(), calls: &calls{}}
	f.served = filepath.Join(f.dir, "repo")
	var err error
	if f.repo, err = tuftest.New(time.Now()); err != nil {
		t.Fatal(err)
	}
	f.srv = httptest.NewServer(http.FileServer(http.Dir(f.served)))
	t.Cleanup(f.srv.Close)

	mk := func(p, s string) {
		p = filepath.Join(f.dir, p)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(s), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	mk("os-release", "ID=debian\nONEMIND_VERSION=\""+curVersion+"\"\nONEMIND_BOARD=\"vm\"\n")
	mk("system.conf", "[system]\ncompatible=onemind-vm\nbootloader=grub\n")
	if err := os.MkdirAll(filepath.Join(f.dir, "gate"), 0o755); err != nil {
		t.Fatal(err)
	}
	f.setRoot(f.repo)

	text := "channel = " + channel + "\nurl = " + f.srv.URL + "\n" +
		"tuf_root_dir = " + filepath.Join(f.dir, "tuf") + "\nstate_dir = " + filepath.Join(f.dir, "state") + "\n" +
		"download_dir = " + filepath.Join(f.dir, "rauc") + "\ngate_dir = " + filepath.Join(f.dir, "gate") + "\n" +
		"os_release = " + filepath.Join(f.dir, "os-release") + "\nrauc_conf = " + filepath.Join(f.dir, "system.conf") + "\n" +
		"reboot_inhibit_file = " + filepath.Join(f.dir, "inhibit") + "\n" + conf
	if f.cfg, err = ParseConfig([]byte(text)); err != nil {
		t.Fatal(err)
	}
	f.eng = &Engine{
		Cfg:         f.cfg,
		Installer:   &fakeRAUC{c: f.calls, gateDir: filepath.Join(f.dir, "gate")},
		Snapshotter: &fakeSnap{c: f.calls},
		Rebooter:    &fakeReboot{c: f.calls},
		HTTP:        f.srv.Client(),
		Log:         slog.New(slog.NewTextHandler(io.Discard, nil)),
		Now:         time.Now,
	}
	return f
}

// setRoot ships r's root.json "in the image".
func (f *fixture) setRoot(r *tuftest.Repo) {
	b, err := r.RootJSON()
	if err != nil {
		f.t.Fatal(err)
	}
	p := filepath.Join(f.dir, "tuf", "security", "root.json")
	for _, ch := range []string{"security", "stable"} {
		p = filepath.Join(f.dir, "tuf", ch, "root.json")
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			f.t.Fatal(err)
		}
		if err := os.WriteFile(p, b, 0o644); err != nil {
			f.t.Fatal(err)
		}
	}
}

func (f *fixture) add(board, v string, security bool) string {
	return f.repo.AddTarget(tuftest.Meta{Board: board, Version: v, Compatible: "onemind-" + board,
		MinFromVersion: "0.1.0", Security: security, BuiltFromSnapshot: "20261112T000000Z",
		SBOM: board + "/" + v + "/sbom.spdx.json", CVEReport: board + "/" + v + "/cve.json"}, bundle(v))
}

func (f *fixture) publish(tsExpiry time.Duration) {
	if err := f.repo.Publish(f.served, tsExpiry); err != nil {
		f.t.Fatal(err)
	}
}

func (f *fixture) run(mode Mode) (*Result, error) {
	return f.eng.Run(context.Background(), mode, false)
}

func (f *fixture) status() *Status {
	st, err := LoadStatus(f.cfg)
	if err != nil {
		f.t.Fatal(err)
	}
	return st
}

func (f *fixture) write(rel, s string) {
	if err := os.WriteFile(filepath.Join(f.dir, rel), []byte(s), 0o644); err != nil {
		f.t.Fatal(err)
	}
}

func wantCalls(t *testing.T, c *calls, want ...string) {
	t.Helper()
	if strings.Join(c.log, "|") != strings.Join(want, "|") {
		t.Fatalf("calls = %q, want %q", c.log, want)
	}
}

// --- tests ---------------------------------------------------------------

func TestVerifyOKSnapshotInstallReboot(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.add("vm", "0.1.2-rc.1", true) // newest wins
	f.add("vm", "0.1.0", true)      // not newer
	f.publish(0)

	res, err := f.run(ModeScheduled)
	if err != nil {
		t.Fatal(err)
	}
	if res.Decision != DecideInstall || res.Candidate.Meta.Version != "0.1.2-rc.1" || !res.Rebooted {
		t.Fatalf("decision %s cand %+v rebooted %v", res.Decision, res.Candidate, res.Rebooted)
	}
	wantCalls(t, f.calls, "snapshot 0.1.0->0.1.2-rc.1", "install onemind-vm-0.1.2-rc.1.raucb", "reboot")
	st := f.status()
	if st.State != heartbeat.UpdatePendingReboot || st.Snapshot != "abc123" || st.TargetVersion != "0.1.2-rc.1" {
		t.Fatalf("status %+v", st)
	}
	if _, err := os.Stat(filepath.Join(f.cfg.DownloadDir, "onemind-vm-0.1.2-rc.1.raucb")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("bundle not removed after install: %v", err)
	}

	// Next run before the reboot happened: no second install, just the reboot.
	f.calls.log = nil
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	wantCalls(t, f.calls, "reboot")
}

func TestExpiredTimestampRefused(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.publish(-time.Hour)
	_, err := f.run(ModeScheduled)
	if err == nil || !strings.Contains(err.Error(), "expired") {
		t.Fatalf("err = %v, want expired", err)
	}
	wantCalls(t, f.calls)
	if st := f.status(); st.State != heartbeat.UpdateError || !strings.Contains(st.LastResult, "check failed") {
		t.Fatalf("status %+v", st)
	}
}

func TestWrongRootRefused(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.publish(0)
	other, err := tuftest.New(time.Now())
	if err != nil {
		t.Fatal(err)
	}
	f.setRoot(other) // the image trusts a different root
	if _, err := f.run(ModeScheduled); err == nil {
		t.Fatal("metadata signed by an untrusted root was accepted")
	}
	wantCalls(t, f.calls)
}

func TestWrongBoardNotOffered(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("rpi5", "0.1.1", true)
	f.publish(0)
	res, err := f.run(ModeScheduled)
	if err != nil {
		t.Fatal(err)
	}
	if res.Decision != DecideNothing || len(res.Skips) != 1 || !strings.Contains(res.Skips[0].Why, "board") {
		t.Fatalf("res %+v", res)
	}
	wantCalls(t, f.calls)
}

func TestTamperedBundleRefused(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	p := f.add("vm", "0.1.1", true)
	f.publish(0)
	f.write(filepath.Join("repo", path.Base(p)), "bundle 0.1.X") // same length, different bytes
	_, err := f.run(ModeScheduled)
	if err == nil || !strings.Contains(err.Error(), "sha256 mismatch") {
		t.Fatalf("err = %v", err)
	}
	wantCalls(t, f.calls)
}

func TestConsistentSnapshotDownload(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.repo.ConsistentSnapshot = true
	f.setRoot(f.repo)
	f.add("vm", "0.1.1", true)
	f.publish(0)
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	wantCalls(t, f.calls, "snapshot 0.1.0->0.1.1", "install onemind-vm-0.1.1.raucb", "reboot")
}

// The channel as the release pipeline publishes it (os/update/CHANNEL.md
// §3, §5): flat files, pipeline version format, and target files served
// through a redirect as GitHub Release assets are.
func TestFlatChannelWithRedirect(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	v := "0.1.20261112025704"
	f.add("vm", v, true)
	f.publish(0)
	files := http.FileServer(http.Dir(f.served))
	var redirected int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasPrefix(r.URL.Path, "/assets/"):
			http.StripPrefix("/assets", files).ServeHTTP(w, r)
		case strings.HasSuffix(r.URL.Path, ".raucb"):
			if strings.Count(r.URL.Path, "/") != 1 {
				t.Errorf("target fetched by path, not basename: %s", r.URL.Path)
			}
			redirected++
			http.Redirect(w, r, "/assets"+r.URL.Path, http.StatusFound)
		default:
			files.ServeHTTP(w, r)
		}
	}))
	t.Cleanup(srv.Close)
	f.cfg.URL, f.cfg.TargetsURL, f.eng.HTTP = srv.URL, srv.URL, srv.Client()
	res, err := f.run(ModeScheduled)
	if err != nil {
		t.Fatal(err)
	}
	if res.Candidate == nil || res.Candidate.Meta.Version != v || redirected != 1 {
		t.Fatalf("candidate %+v, redirects %d", res.Candidate, redirected)
	}
	wantCalls(t, f.calls, "snapshot 0.1.0->"+v, "install onemind-vm-"+v+".raucb", "reboot")
}

func TestPendingTrialRefusesEvenExplicit(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.publish(0)
	f.write("gate/pending", "A "+curVersion+"\n") // the gate is deciding on the booted slot
	for _, m := range []Mode{ModeScheduled, ModeApply} {
		res, err := f.run(m)
		if err != nil {
			t.Fatal(err)
		}
		if res.Decision != DecideBlockedTrial {
			t.Fatalf("mode %d: decision %s", m, res.Decision)
		}
	}
	wantCalls(t, f.calls)
	if st := f.status(); st.State != heartbeat.UpdateTrial {
		t.Fatalf("state %s", st.State)
	}
}

func TestPostponeHonoured(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.publish(0)
	if err := os.MkdirAll(f.cfg.StateDir, 0o755); err != nil {
		t.Fatal(err)
	}
	f.write("state/postpone-until", time.Now().Add(48*time.Hour).UTC().Format(time.RFC3339))
	res, err := f.run(ModeScheduled)
	if err != nil {
		t.Fatal(err)
	}
	if res.Decision != DecidePostponed {
		t.Fatalf("decision %s", res.Decision)
	}
	wantCalls(t, f.calls)
	if st := f.status(); st.AvailableVersion == nil || *st.AvailableVersion != "0.1.1" {
		t.Fatalf("available not reported: %+v", st)
	}
}

func TestStableNotifiesOnly(t *testing.T) {
	f := newFixture(t, "stable", "window = any\n")
	f.add("vm", "0.2.0", false)
	f.publish(0)
	res, err := f.run(ModeScheduled)
	if err != nil {
		t.Fatal(err)
	}
	if res.Decision != DecideNotify {
		t.Fatalf("decision %s", res.Decision)
	}
	wantCalls(t, f.calls)
	// The owner applies; --no-reboot leaves it pending.
	if _, err := f.eng.Run(context.Background(), ModeApply, true); err != nil {
		t.Fatal(err)
	}
	wantCalls(t, f.calls, "snapshot 0.1.0->0.2.0", "install onemind-vm-0.2.0.raucb")
}

func TestPolicyOffAndCheckNeverInstall(t *testing.T) {
	f := newFixture(t, "security", "window = any\npolicy = off\n")
	f.add("vm", "0.1.1", true)
	f.publish(0)
	if res, _ := f.run(ModeScheduled); res.Decision != DecideOff {
		t.Fatalf("decision %s", res.Decision)
	}
	f.cfg.Policy = PolicyAuto
	res, err := f.run(ModeCheck)
	if err != nil || res.Decision != DecideInstall || !strings.Contains(f.status().LastResult, "would install") {
		t.Fatalf("check: %v %+v", err, res)
	}
	wantCalls(t, f.calls)
}

func TestSecurityOnlyFlaggedOnSecurityChannel(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", false)
	f.publish(0)
	if res, _ := f.run(ModeScheduled); res.Decision != DecideNothing {
		t.Fatalf("decision %s", res.Decision)
	}
}

func TestNoResticSecurityContinuesWithWarning(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.eng.Snapshotter = nil
	f.add("vm", "0.1.1", true)
	f.publish(0)
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	wantCalls(t, f.calls, "install onemind-vm-0.1.1.raucb", "reboot")
	st := f.status()
	if st.Snapshot != "none" || len(st.Warnings) != 1 || !strings.Contains(st.Warnings[0], "restic is not configured") {
		t.Fatalf("status %+v", st)
	}
}

func TestStableRequiresSnapshot(t *testing.T) {
	f := newFixture(t, "stable", "window = any\n")
	f.eng.Snapshotter = &fakeSnap{c: f.calls, err: errors.New("repo locked")}
	f.add("vm", "0.2.0", false)
	f.publish(0)
	_, err := f.eng.Run(context.Background(), ModeApply, false)
	if err == nil || !strings.Contains(err.Error(), "pre-update snapshot") {
		t.Fatalf("err = %v", err)
	}
	wantCalls(t, f.calls, "snapshot 0.1.0->0.2.0")
	if st := f.status(); st.State != heartbeat.UpdateError || len(st.History) != 1 {
		t.Fatalf("status %+v", st)
	}
}

func TestOutsideWindowWaits(t *testing.T) {
	f := newFixture(t, "security", "window = 02:00-05:00\n")
	f.eng.Now = func() time.Time { return time.Date(2026, 11, 12, 14, 0, 0, 0, time.Local) }
	f.add("vm", "0.1.1", true)
	f.publish(0)
	res, err := f.run(ModeScheduled)
	if err != nil || res.Decision != DecideWait {
		t.Fatalf("%v %s", err, res.Decision)
	}
	wantCalls(t, f.calls)
}

func TestRebootInhibitDefers(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.publish(0)
	f.write("inhibit", "mission running")
	res, err := f.run(ModeScheduled)
	if err != nil || res.Rebooted {
		t.Fatalf("%v rebooted=%v", err, res.Rebooted)
	}
	if st := f.status(); st.State != heartbeat.UpdatePendingReboot || !strings.Contains(st.LastResult, "deferred") {
		t.Fatalf("status %+v", st)
	}
	os.Remove(filepath.Join(f.dir, "inhibit"))
	f.calls.log = nil
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	wantCalls(t, f.calls, "reboot")
}

func TestVerdictAfterBoot(t *testing.T) {
	for _, tc := range []struct {
		name, booted, bad, want, result string
	}{
		{"committed", "0.1.1", "", heartbeat.UpdateCommitted, "committed 0.1.1"},
		{"rolled back", "0.1.0", "2026-11-12T03:05:00Z version=0.1.1 verdict=image-bad\n", heartbeat.UpdateRolledBack, "gate verdict image-bad"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := newFixture(t, "security", "window = any\n")
			f.add("vm", "0.1.1", true)
			f.publish(0)
			if _, err := f.run(ModeScheduled); err != nil { // installs 0.1.1, "reboots"
				t.Fatal(err)
			}
			// Simulate the boot + gate: marker removed, booted version set.
			os.Remove(filepath.Join(f.dir, "gate", "pending"))
			f.write("os-release", "ONEMIND_VERSION=\""+tc.booted+"\"\nONEMIND_BOARD=\"vm\"\n")
			f.write("gate/bad-releases", tc.bad)
			f.calls.log = nil
			res, err := f.run(ModeScheduled)
			if err != nil {
				t.Fatal(err)
			}
			st := f.status()
			if st.State != tc.want || !strings.Contains(st.LastResult, tc.result) || len(st.History) != 1 {
				t.Fatalf("status %+v", st)
			}
			// A rolled-back image-bad release is never offered again.
			if tc.want == heartbeat.UpdateRolledBack && (res.Decision != DecideNothing || len(f.calls.log) != 0) {
				t.Fatalf("re-offered: %s %v", res.Decision, f.calls.log)
			}
		})
	}
}

func TestTrialStateWhileGateDecides(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.publish(0)
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	// Booted into 0.1.1, gate still running (marker names the booted version).
	f.write("os-release", "ONEMIND_VERSION=\"0.1.1\"\nONEMIND_BOARD=\"vm\"\n")
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	st := f.status()
	if st.State != heartbeat.UpdateTrial || !strings.Contains(st.LastResult, "trial") {
		t.Fatalf("status %+v", st)
	}
	r := Report(f.cfg)
	b, _ := json.Marshal(r)
	var m map[string]any
	_ = json.Unmarshal(b, &m)
	for _, k := range []string{"channel", "current_version", "available_version", "state", "last_check", "last_result"} {
		if _, ok := m[k]; !ok {
			t.Fatalf("heartbeat update object lacks %q: %s", k, b)
		}
	}
	if len(m) != 6 {
		t.Fatalf("heartbeat update object has extra keys: %s", b)
	}
}

func TestLockExcludesConcurrentRuns(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	unlock, err := lock(f.cfg.StateDir)
	if err != nil {
		t.Fatal(err)
	}
	defer unlock()
	if _, err := f.run(ModeScheduled); !errors.Is(err, ErrBusy) {
		t.Fatalf("err = %v, want ErrBusy", err)
	}
}

// Rollback (replay) attack: after the box trusted version-2 metadata, a
// mirror that serves the older, still unexpired and validly signed
// version-1 metadata again must be refused, so an attacker cannot hide a
// newer security release by replaying an old index.
func TestReplayedOlderMetadataRefused(t *testing.T) {
	f := newFixture(t, "security", "window = any\npolicy = off\n")
	f.add("vm", "0.1.1", true)
	old := filepath.Join(f.dir, "old")
	if err := f.repo.Publish(old, 0); err != nil { // version 1
		t.Fatal(err)
	}
	f.add("vm", "0.1.2", true)
	f.publish(0) // version 2, served
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	for _, n := range []string{"timestamp.json", "snapshot.json", "targets.json"} {
		b, err := os.ReadFile(filepath.Join(old, n))
		if err != nil {
			t.Fatal(err)
		}
		f.write(filepath.Join("repo", n), string(b))
	}
	_, err := f.run(ModeScheduled)
	if err == nil || !strings.Contains(err.Error(), "timestamp version") {
		t.Fatalf("replayed version-1 metadata accepted: err = %v", err)
	}
	wantCalls(t, f.calls)
}

func TestSnapshotExcludesLocalRepository(t *testing.T) {
	for repo, want := range map[string]bool{
		"/data/backup/restic":         true,
		"local:/data/backup/restic/":  true,
		"sftp:backup:/srv/restic":     false,
		"rest:https://backup.invalid": false,
	} {
		c := Defaults(ChannelSecurity)
		c.ResticRepository = repo
		ex := snapshotExcludes(&c)
		got := false
		for _, e := range ex {
			got = got || e == "/data/backup/restic"
		}
		if got != want || ex[0] != c.DownloadDir || ex[1] != c.StateDir {
			t.Errorf("%s: excludes %v", repo, ex)
		}
	}
}
