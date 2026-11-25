// SPDX-License-Identifier: Apache-2.0

package update

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/update/tuftest"
)

// usbStick publishes the fixture repo, signed `age` ago, into a fresh directory
// laid out like a channel (metadata and bundles side by side) and returns it.
func (f *fixture) usbStick(age time.Duration) string {
	f.t.Helper()
	f.repo.Now = time.Now().Add(-age)
	dir := filepath.Join(f.t.TempDir(), "usb")
	if err := f.repo.Publish(dir, 0); err != nil {
		f.t.Fatal(err)
	}
	return dir
}

const day = 24 * time.Hour

// The Year-1 scenario: no network, a 60-day-old stick (every expiry has passed:
// timestamp 1 d, snapshot 7 d, targets 30 d) still installs inside the grace.
func TestMirrorInstallsWithinOfflineGrace(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.srv.Close() // no network at all
	f.add("vm", "0.1.1", true)
	f.eng.Mirror = f.usbStick(60 * day)

	res, err := f.run(ModeApply)
	if err != nil {
		t.Fatal(err)
	}
	if res.Decision != DecideInstall || !res.Rebooted {
		t.Fatalf("decision %s rebooted %v", res.Decision, res.Rebooted)
	}
	wantCalls(t, f.calls, "snapshot 0.1.0->0.1.1", "install onemind-vm-0.1.1.raucb", "reboot")
	st := f.status()
	if st.State != heartbeat.UpdatePendingReboot || len(st.Warnings) == 0 || !strings.Contains(st.Warnings[0], "mirror") {
		t.Fatalf("status %+v", st)
	}
}

func TestMirrorBeyondGraceRefused(t *testing.T) {
	f := newFixture(t, "security", "window = any\noffline_grace = 720h\n") // 30 d
	f.add("vm", "0.1.1", true)
	f.eng.Mirror = f.usbStick(90 * day) // targets expired 60 d ago
	if _, err := f.run(ModeApply); err == nil || !strings.Contains(err.Error(), "expired") {
		t.Fatalf("err = %v, want expired", err)
	}
	wantCalls(t, f.calls)
}

func TestMirrorZeroGraceIsStrict(t *testing.T) {
	f := newFixture(t, "security", "window = any\noffline_grace = 0\n")
	f.add("vm", "0.1.1", true)
	f.eng.Mirror = f.usbStick(2 * day)
	if _, err := f.run(ModeApply); err == nil || !strings.Contains(err.Error(), "expired") {
		t.Fatalf("err = %v, want expired", err)
	}
	wantCalls(t, f.calls)
}

// The grace is for mirrors only: the same stale metadata served online is refused.
func TestOnlineNeverUsesGrace(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.repo.Now = time.Now().Add(-60 * day)
	f.publish(0)
	if _, err := f.run(ModeApply); err == nil || !strings.Contains(err.Error(), "expired") {
		t.Fatalf("err = %v, want expired", err)
	}
	wantCalls(t, f.calls)
}

// No trust downgrade: a stick signed by a key the image does not trust.
func TestMirrorWrongRootRefused(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	other, err := tuftest.New(time.Now())
	if err != nil {
		t.Fatal(err)
	}
	other.AddTarget(tuftest.Meta{Board: "vm", Version: "0.1.1", Compatible: "onemind-vm", MinFromVersion: "0.1.0", Security: true}, bundle("0.1.1"))
	dir := filepath.Join(t.TempDir(), "usb")
	if err := other.Publish(dir, 0); err != nil {
		t.Fatal(err)
	}
	f.eng.Mirror = dir
	if _, err := f.run(ModeApply); err == nil {
		t.Fatal("stick signed by an untrusted root was accepted")
	}
	wantCalls(t, f.calls)
}

// A valid signed index with a swapped bundle: hashes come from the signed
// metadata, so the file is rejected before RAUC sees it.
func TestMirrorTamperedBundleRefused(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	dir := f.usbStick(5 * day)
	if err := os.WriteFile(filepath.Join(dir, "onemind-vm-0.1.1.raucb"), []byte("evil bundle"), 0o644); err != nil {
		t.Fatal(err)
	}
	f.eng.Mirror = dir
	if _, err := f.run(ModeApply); err == nil {
		t.Fatal("tampered bundle was accepted")
	}
	wantCalls(t, f.calls)
}

// Rollback protection is shared with online checks: after a newer stick was
// seen, an older stick (replayed metadata) is refused even inside the grace.
func TestMirrorReplayOfOlderMetadataRefused(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	older := f.usbStick(3 * day)
	newer := f.usbStick(2 * day) // second Publish: higher metadata versions
	f.eng.Mirror = newer
	if _, err := f.run(ModeCheck); err != nil {
		t.Fatal(err)
	}
	f.eng.Mirror = older
	if _, err := f.run(ModeCheck); err == nil {
		t.Fatal("older metadata was accepted after newer was seen")
	}
}

func TestMirrorBadPath(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	for _, m := range []string{"relative/dir", filepath.Join(f.dir, "missing")} {
		f.eng.Mirror = m
		if _, err := f.run(ModeCheck); err == nil {
			t.Fatalf("mirror %q accepted", m)
		}
	}
	wantCalls(t, f.calls)
}

func TestParseOfflineGrace(t *testing.T) {
	c, err := ParseConfig([]byte("channel = security\nurl = https://example.org/s\n"))
	if err != nil || c.OfflineGrace != DefaultOfflineGrace {
		t.Fatalf("default: %v %v", c, err)
	}
	c, err = ParseConfig([]byte("channel = security\nurl = https://example.org/s\noffline_grace = 48h\n"))
	if err != nil || c.OfflineGrace != 48*time.Hour {
		t.Fatalf("48h: %v %v", c, err)
	}
	for _, bad := range []string{"-1h", "9000h", "soon"} {
		if _, err := ParseConfig([]byte("channel = security\nurl = https://example.org/s\noffline_grace = " + bad + "\n")); err == nil {
			t.Errorf("offline_grace = %s accepted", bad)
		}
	}
}
