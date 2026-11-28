// SPDX-License-Identifier: Apache-2.0

package update

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// REL-02 (#154): the security channel installs by default; the owner's approved opt-out and window
// (owner.conf under /data) override the read-only image file, and a broken owner file never turns
// automatic security updates off.

func TestOwnerOptOutStopsTheDefaultInstall(t *testing.T) {
	f := newFixture(t, "security", "window = any\n") // image default: policy auto
	f.add("vm", "0.1.1", true)
	f.publish(0)
	if err := WriteOwner(f.cfg, OwnerSettings{Policy: PolicyOff, Window: Window{Any: true}}); err != nil {
		t.Fatal(err)
	}
	res, err := f.run(ModeScheduled)
	if err != nil || res.Decision != DecideOff {
		t.Fatalf("%v %s", err, res.Decision)
	}
	wantCalls(t, f.calls)
	if st := f.status(); st.Policy != "off" || st.SettingsSource != SourceOwner {
		t.Fatalf("status %+v", st.Update)
	}
	// Turning automatic security updates back on: the next cycle installs.
	if err := WriteOwner(f.cfg, OwnerSettings{Policy: PolicyAuto, Window: Window{Any: true}}); err != nil {
		t.Fatal(err)
	}
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	wantCalls(t, f.calls, "snapshot 0.1.0->0.1.1", "install onemind-vm-0.1.1.raucb", "reboot")
}

func TestOwnerWindowReplacesTheImageWindow(t *testing.T) {
	f := newFixture(t, "security", "window = 02:00-05:00\n")
	f.eng.Now = func() time.Time { return time.Date(2026, 11, 12, 14, 30, 0, 0, time.Local) }
	f.add("vm", "0.1.1", true)
	f.publish(0)
	if res, _ := f.run(ModeScheduled); res.Decision != DecideWait {
		t.Fatalf("image window: decision %s", res.Decision)
	}
	w, _ := ParseWindow("14:00-15:00")
	if err := WriteOwner(f.cfg, OwnerSettings{Policy: PolicyAuto, Window: w}); err != nil {
		t.Fatal(err)
	}
	res, err := f.run(ModeScheduled)
	if err != nil || res.Decision != DecideInstall || !strings.Contains(res.Reason, "14:00-15:00") {
		t.Fatalf("%v %s %s", err, res.Decision, res.Reason)
	}
	wantCalls(t, f.calls, "snapshot 0.1.0->0.1.1", "install onemind-vm-0.1.1.raucb", "reboot")
}

func TestBrokenOwnerFileKeepsTheSecureDefault(t *testing.T) {
	for name, body := range map[string]string{
		"bad policy":     "policy = never\nwindow = any\n",
		"half written":   "policy = off\n",
		"foreign key":    "policy = off\nwindow = any\nurl = https://evil.example\n",
		"bad window":     "policy = off\nwindow = 25:00-01:00\n",
		"no key = value": "policy off\n",
	} {
		t.Run(name, func(t *testing.T) {
			c := Defaults(ChannelSecurity)
			c.StateDir = t.TempDir()
			if err := os.WriteFile(OwnerPath(&c), []byte(body), 0o644); err != nil {
				t.Fatal(err)
			}
			p, w, src, err := c.Effective()
			if err == nil || p != PolicyAuto || w.String() != "02:00-05:00" || src != SourceImage {
				t.Fatalf("got %s %s %s %v", p, w, src, err)
			}
		})
	}
}

func TestOwnerFileRoundTripAndReport(t *testing.T) {
	c := Defaults(ChannelSecurity)
	c.StateDir = t.TempDir()
	if p, w, src, err := c.Effective(); err != nil || p != PolicyAuto || w.String() != "02:00-05:00" || src != SourceImage {
		t.Fatalf("no owner file: %s %s %s %v", p, w, src, err)
	}
	if err := WriteOwner(&c, OwnerSettings{Policy: "sometimes"}); err == nil {
		t.Fatal("WriteOwner accepted a bad policy")
	}
	w, _ := ParseWindow("23:00-04:00")
	if err := WriteOwner(&c, OwnerSettings{Policy: PolicyNotify, Window: w}); err != nil {
		t.Fatal(err)
	}
	o, err := ReadOwner(&c)
	if err != nil || o.Policy != PolicyNotify || o.Window != w {
		t.Fatalf("%+v %v", o, err)
	}
	st := &Status{}
	st.State = "idle"
	if err := st.Save(&c); err != nil {
		t.Fatal(err)
	}
	u := Report(&c)
	if u == nil || u.Policy != "notify" || u.Window != "23:00-04:00" || u.SettingsSource != SourceOwner {
		t.Fatalf("report %+v", u)
	}
}

// Review (#1342): an install that waits for its reboot does not restart the box on its own once the
// owner turned updates off; the owner's explicit apply still does.
func TestOptOutAfterInstallHoldsThePendingReboot(t *testing.T) {
	f := newFixture(t, "security", "window = any\n")
	f.add("vm", "0.1.1", true)
	f.publish(0)
	f.write("inhibit", "mission running") // installs, then defers the reboot
	if _, err := f.run(ModeScheduled); err != nil {
		t.Fatal(err)
	}
	if st := f.status(); st.State != heartbeat.UpdatePendingReboot {
		t.Fatalf("status %+v", st.Update)
	}
	os.Remove(filepath.Join(f.dir, "inhibit"))
	if err := WriteOwner(f.cfg, OwnerSettings{Policy: PolicyOff, Window: Window{Any: true}}); err != nil {
		t.Fatal(err)
	}
	f.calls.log = nil
	res, err := f.run(ModeScheduled)
	if err != nil || res.Rebooted || !strings.Contains(f.status().LastResult, "policy off") {
		t.Fatalf("%v rebooted=%v %q", err, res.Rebooted, f.status().LastResult)
	}
	wantCalls(t, f.calls)
	if res, err := f.eng.Run(context.Background(), ModeApply, false); err != nil || !res.Rebooted {
		t.Fatalf("owner apply: %v %+v", err, res)
	}
	wantCalls(t, f.calls, "reboot")
}

func TestWriteOwnerTightensTheDirectoryAndLeavesNoTemp(t *testing.T) {
	c := Defaults(ChannelSecurity)
	c.StateDir = t.TempDir()
	if err := os.Chmod(c.StateDir, 0o777); err != nil {
		t.Fatal(err)
	}
	if err := WriteOwner(&c, OwnerSettings{Policy: PolicyOff, Window: Window{Any: true}}); err != nil {
		t.Fatal(err)
	}
	if fi, _ := os.Stat(c.StateDir); fi.Mode().Perm() != 0o755 {
		t.Fatalf("dir mode %v", fi.Mode().Perm())
	}
	ents, _ := os.ReadDir(c.StateDir)
	if len(ents) != 1 || ents[0].Name() != OwnerFile {
		t.Fatalf("entries %v", ents)
	}
}
