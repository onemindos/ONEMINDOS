// SPDX-License-Identifier: Apache-2.0

package update

import (
	"strings"
	"testing"
	"time"
)

func TestDecide(t *testing.T) {
	win, _ := ParseWindow("02:00-05:00")
	at := func(h int) time.Time { return time.Date(2026, 11, 12, h, 30, 0, 0, time.Local) }
	base := DecideInput{Policy: PolicyAuto, Window: win, Now: at(3), HaveCandidate: true}
	cases := []struct {
		name string
		mod  func(*DecideInput)
		want Decision
	}{
		{"auto in window", func(*DecideInput) {}, DecideInstall},
		{"auto outside window", func(i *DecideInput) { i.Now = at(14) }, DecideWait},
		{"no candidate", func(i *DecideInput) { i.HaveCandidate = false }, DecideNothing},
		{"notify", func(i *DecideInput) { i.Policy = PolicyNotify }, DecideNotify},
		{"off", func(i *DecideInput) { i.Policy = PolicyOff }, DecideOff},
		{"postponed", func(i *DecideInput) { i.PostponeUntil = at(3).Add(time.Hour) }, DecidePostponed},
		{"postpone expired", func(i *DecideInput) { i.PostponeUntil = at(3).Add(-time.Hour) }, DecideInstall},
		{"trial blocks", func(i *DecideInput) { i.TrialPending = true }, DecideBlockedTrial},
		{"trial blocks explicit", func(i *DecideInput) { i.TrialPending, i.Explicit = true, true }, DecideBlockedTrial},
		{"explicit overrides off", func(i *DecideInput) { i.Policy, i.Explicit = PolicyOff, true }, DecideInstall},
		{"explicit outside window", func(i *DecideInput) { i.Now, i.Explicit = at(14), true }, DecideInstall},
	}
	for _, c := range cases {
		in := base
		c.mod(&in)
		if got, _ := Decide(in); got != c.want {
			t.Errorf("%s: got %s want %s", c.name, got, c.want)
		}
	}
}

func TestWindow(t *testing.T) {
	at := func(h, m int) time.Time { return time.Date(2026, 1, 1, h, m, 0, 0, time.UTC) }
	w, err := ParseWindow("22:00-04:00") // wraps midnight
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range []struct {
		h, m int
		in   bool
	}{{21, 59, false}, {22, 0, true}, {0, 0, true}, {3, 59, true}, {4, 0, false}, {12, 0, false}} {
		if w.Contains(at(c.h, c.m)) != c.in {
			t.Errorf("%02d:%02d in %s = %v", c.h, c.m, w, !c.in)
		}
	}
	for _, bad := range []string{"", "2-5", "02:00-02:00", "25:00-03:00", "02:00"} {
		if _, err := ParseWindow(bad); err == nil {
			t.Errorf("ParseWindow(%q) accepted", bad)
		}
	}
	if a, _ := ParseWindow("any"); !a.Contains(at(13, 0)) {
		t.Error("any")
	}
}

func TestParseConfig(t *testing.T) {
	c, err := ParseConfig([]byte("# comment\nchannel = security\nurl = https://example.org/tuf/security/\n"))
	if err != nil {
		t.Fatal(err)
	}
	if c.Policy != PolicyAuto || c.RequireSnapshot || c.Window.String() != "02:00-05:00" ||
		c.TargetsURL != "https://example.org/tuf/security" || c.CheckInterval != time.Hour {
		t.Fatalf("security defaults wrong: %+v", c)
	}
	c, err = ParseConfig([]byte("channel = stable\nurl = https://example.org/s\nwindow = 01:00-03:30\n"))
	if err != nil {
		t.Fatal(err)
	}
	if c.Policy != PolicyNotify || !c.RequireSnapshot || c.Window.String() != "01:00-03:30" {
		t.Fatalf("stable defaults wrong: %+v", c)
	}
	for _, bad := range []string{
		"channel = beta\nurl = https://x",
		"channel = security",
		"channel = security\nurl = http://example.org",
		"channel = security\nurl = https://x\npolicy = sometimes",
		"channel = security\nurl = https://x\nrestic_binary = /usr/bin/restic",
		"channel = security\nurl = https://x\nurl = https://y",
	} {
		if _, err := ParseConfig([]byte(bad)); err == nil {
			t.Errorf("accepted %q", bad)
		}
	}
	if _, err := ParseConfig([]byte("channel = security\nurl = http://127.0.0.1:8000")); err != nil {
		t.Errorf("loopback http refused: %v", err)
	}
	// CHANNEL.md §4: unknown keys are ignored, but recorded for the log.
	c, err = ParseConfig([]byte("channel=security\nurl=https://x\npolciy=off\nfuture_key=1\n"))
	if err != nil {
		t.Fatalf("unknown key refused: %v", err)
	}
	if c.Policy != PolicyAuto || strings.Join(c.Ignored, ",") != "future_key,polciy" {
		t.Fatalf("unknown keys: policy %s, ignored %v", c.Policy, c.Ignored)
	}
}

func TestCompareVersions(t *testing.T) {
	ordered := []string{"0.1.0-dev", "0.1.0-dev-next", "0.1.0-rc.1", "0.1.0-rc.2", "0.1.0-rc.10", "0.1.0", "0.1.1",
		"0.1.20261112025704", "0.1.20261113000000", "0.2.0", "0.2.0.1", "1.0.0"}
	for i := 0; i+1 < len(ordered); i++ {
		if c, err := compareVersions(ordered[i], ordered[i+1]); err != nil || c != -1 {
			t.Errorf("%s < %s: got %d %v", ordered[i], ordered[i+1], c, err)
		}
	}
	if c, _ := compareVersions("v1.2.3+build.5", "1.2.3"); c != 0 {
		t.Error("build metadata must not order")
	}
	// CHANNEL.md §5: dot-separated integers of any length; a missing part is 0.
	if c, _ := compareVersions("0.1", "0.1.0"); c != 0 {
		t.Error("0.1 == 0.1.0")
	}
	if c, _ := compareVersions("0.1.0.20261112025704", "0.1.20261112025704"); c != -1 {
		t.Error("parts compare positionally")
	}
	for _, bad := range []string{"unknown", "", "1..2", "1.2.x", "-1.2", "1.2.3-", "1.2.3-a..b"} {
		if _, err := compareVersions(bad, "1.0.0"); err == nil {
			t.Errorf("accepted %q", bad)
		}
	}
}

func TestSelectRules(t *testing.T) {
	c := &Config{Channel: ChannelSecurity}
	box := Box{Board: "vm", Compatible: "onemind-vm", Version: "0.1.0"}
	tg := func(v, min, compat string) Target {
		return Target{Path: "vm/" + v + "/onemind-vm-" + v + ".raucb",
			Meta: TargetMeta{Board: "vm", Version: v, Compatible: compat, MinFromVersion: min, Security: true}}
	}
	idx := &Index{Targets: []Target{
		tg("0.3.0", "0.2.0", "onemind-vm"),    // needs a newer base
		tg("0.2.0", "0.1.0", "onemind-other"), // wrong compatible
		tg("0.1.5", "0.1.0", "onemind-vm"),    // bad release
		tg("0.1.3", "0.1.0", "onemind-vm"),    // env-bad twice: still offered
		tg("0.1.2", "", "onemind-vm"),         // ok, older
		{Path: "vm/9.9.9/evil.raucb", Meta: TargetMeta{Board: "vm", Version: "9.9.9", Compatible: "onemind-vm", Security: true}},
	}}
	bad := BadReleases{imageBad: map[string]bool{"0.1.5": true}, envBad: map[string]int{"0.1.3": 2}}
	got, skips := Select(c, idx, box, bad)
	if got == nil || got.Meta.Version != "0.1.3" {
		t.Fatalf("got %+v; skips %+v", got, skips)
	}
	why := map[string]string{}
	for _, s := range skips {
		why[s.Path] = s.Why
	}
	for p, want := range map[string]string{
		"vm/0.3.0/onemind-vm-0.3.0.raucb": "needs at least",
		"vm/0.2.0/onemind-vm-0.2.0.raucb": "compatible",
		"vm/0.1.5/onemind-vm-0.1.5.raucb": "image-bad",
		"vm/9.9.9/evil.raucb":             "path does not match",
	} {
		if !strings.Contains(why[p], want) {
			t.Errorf("%s: why %q, want %q", p, why[p], want)
		}
	}
	bad.envBad["0.1.3"] = 3
	if got, _ := Select(c, idx, box, bad); got == nil || got.Meta.Version != "0.1.2" {
		t.Fatalf("env-bad limit not applied: %+v", got)
	}
}

func TestDownloadURL(t *testing.T) {
	tg := &Target{Path: "vm/0.1.1/onemind-vm-0.1.1.raucb", Hashes: map[string]string{"sha256": "ab"},
		Meta: TargetMeta{Board: "vm", Version: "0.1.1"}}
	// CHANNEL.md §3: flat layout, <url>/<basename(target path)>.
	c, err := ParseConfig([]byte("channel=security\nurl=https://github.com/o/r/releases/download/os-channel-security/\n"))
	if err != nil {
		t.Fatal(err)
	}
	if u := downloadURL(c, &Index{}, tg); u != "https://github.com/o/r/releases/download/os-channel-security/onemind-vm-0.1.1.raucb" {
		t.Error(u)
	}
	if u := downloadURL(c, &Index{ConsistentSnapshot: true}, tg); u != "https://github.com/o/r/releases/download/os-channel-security/ab.onemind-vm-0.1.1.raucb" {
		t.Error(u)
	}
	c.TargetsURL = "https://mirror.example/tuf/targets/{path}"
	if u := downloadURL(c, &Index{}, tg); u != "https://mirror.example/tuf/targets/vm/0.1.1/onemind-vm-0.1.1.raucb" {
		t.Error(u)
	}
}

func TestParseResticSummary(t *testing.T) {
	out := `{"message_type":"status","percent_done":0.5}
{"message_type":"summary","files_new":3,"snapshot_id":"1a2b3c4d"}
`
	if id, err := parseResticSummary([]byte(out)); err != nil || id != "1a2b3c4d" {
		t.Fatalf("%q %v", id, err)
	}
	if _, err := parseResticSummary([]byte(`{"message_type":"status"}`)); err == nil {
		t.Fatal("no summary accepted")
	}
}
