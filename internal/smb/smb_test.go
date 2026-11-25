// SPDX-License-Identifier: Apache-2.0

package smb

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func i64(n int64) *int64 { return &n }

func twoShares() []Share {
	return []Share{
		{ID: "shr_1", Kind: KindHome, Name: "alex", User: "alex", Path: "home/alex"},
		{ID: "shr_2", Kind: KindTimeMachine, Name: "alex-timemachine", User: "alex", Path: ".system/timemachine/alex", QuotaBytes: i64(500 << 30)},
	}
}

func TestRenderConfHoldsTheSecurityRules(t *testing.T) {
	conf := RenderConf(twoShares(), DefaultPaths())
	for _, want := range []string{
		"server min protocol = SMB2_10", "map to guest = Never", "restrict anonymous = 2", "hosts deny = ALL",
		"hosts allow = 127.0.0.0/8 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10 ::1 fe80::/10 fc00::/7",
		"follow symlinks = no", "wide links = no", "unix extensions = no", "disable netbios = yes",
		"[alex]", "path = /data/onemind/files/home/alex", "valid users = alex", "force user = onemind",
		"[alex-timemachine]", "path = /data/onemind/files/.system/timemachine/alex",
		"fruit:time machine = yes", "fruit:time machine max size = 512000M",
	} {
		if !strings.Contains(conf, want) {
			t.Errorf("smb.conf lacks %q:\n%s", want, conf)
		}
	}
	for _, banned := range []string{"guest ok = yes", "NT1", "public = yes"} {
		if strings.Contains(conf, banned) {
			t.Errorf("smb.conf has %q", banned)
		}
	}
	if strings.Count(conf, "fruit:time machine = yes") != 1 {
		t.Error("only the Time Machine share is a Time Machine target")
	}
	if strings.Contains(RenderConf(twoShares()[:1], DefaultPaths()), "fruit") {
		t.Error("a box with no Time Machine share loads no fruit module")
	}
}

func TestValidateRefusesWhatCouldEscapeTheFilesLayout(t *testing.T) {
	bad := map[string]Share{
		"traversal":   {ID: "a", Kind: KindHome, Name: "x", User: "x", Path: "home/../etc"},
		"absolute":    {ID: "a", Kind: KindHome, Name: "x", User: "x", Path: "/etc"},
		"other tree":  {ID: "a", Kind: KindHome, Name: "x", User: "x", Path: "shared/x"},
		"tm in home":  {ID: "a", Kind: KindTimeMachine, Name: "x", User: "x", Path: "home/x", QuotaBytes: i64(2 << 30)},
		"newline":     {ID: "a", Kind: KindHome, Name: "x\n[global]", User: "x", Path: "home/x"},
		"user":        {ID: "a", Kind: KindHome, Name: "x", User: "x y", Path: "home/x"},
		"no quota":    {ID: "a", Kind: KindTimeMachine, Name: "x", User: "x", Path: ".system/timemachine/x"},
		"tiny quota":  {ID: "a", Kind: KindTimeMachine, Name: "x", User: "x", Path: ".system/timemachine/x", QuotaBytes: i64(1 << 20)},
		"home quota":  {ID: "a", Kind: KindHome, Name: "x", User: "x", Path: "home/x", QuotaBytes: i64(2 << 30)},
		"unknown":     {ID: "a", Kind: "disk", Name: "x", User: "x", Path: "home/x"},
		"dir newline": {ID: "a", Kind: KindHome, Name: "x", User: "x", Path: "home/x\ny"},
	}
	for name, s := range bad {
		if err := Validate([]Share{s}); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	dup := twoShares()
	dup[1].Name = "alex"
	if Validate(dup) == nil {
		t.Error("a duplicate share name was accepted")
	}
	if err := Validate(twoShares()); err != nil {
		t.Errorf("a good list was refused: %v", err)
	}
}

func TestAvahiAdvertisesTimeMachineOnlyWhenThereIsOne(t *testing.T) {
	if RenderAvahi(nil) != "" {
		t.Error("no shares, no record")
	}
	home := RenderAvahi(twoShares()[:1])
	if !strings.Contains(home, "_smb._tcp") || strings.Contains(home, "_adisk") {
		t.Errorf("home only:\n%s", home)
	}
	tm := RenderAvahi(twoShares())
	if !strings.Contains(tm, "_adisk._tcp") || !strings.Contains(tm, "dk0=adVN=alex-timemachine,adVF=0x82") {
		t.Errorf("with Time Machine:\n%s", tm)
	}
}

type call struct {
	stdin string
	argv  []string
}
type fakeRunner struct {
	mu    sync.Mutex
	calls []call
	fail  map[string]error // program -> error
}

func (f *fakeRunner) Run(_ context.Context, stdin, name string, args ...string) ([]byte, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, call{stdin, append([]string{name}, args...)})
	if err := f.fail[name]; err != nil {
		return []byte("boom: " + stdin), err
	}
	return nil, nil
}

func (f *fakeRunner) ran(prefix ...string) int {
	n := 0
	for _, c := range f.calls {
		if len(c.argv) >= len(prefix) && strings.Join(c.argv[:len(prefix)], " ") == strings.Join(prefix, " ") {
			n++
		}
	}
	return n
}

func newManager(t *testing.T) (*Manager, *fakeRunner) {
	t.Helper()
	p := DefaultPaths()
	p.StateDir = t.TempDir()
	r := &fakeRunner{fail: map[string]error{}}
	return &Manager{P: p, Run: r, Have: func(string) bool { return true }}, r
}

func TestApplyChecksTheConfigThenWritesAndStartsSamba(t *testing.T) {
	m, r := newManager(t)
	if err := m.Apply(context.Background(), twoShares()); err != nil {
		t.Fatal(err)
	}
	if r.ran("testparm") != 1 || r.ran("systemctl", "reload-or-restart", Unit) != 1 {
		t.Errorf("calls: %v", r.calls)
	}
	if r.calls[0].argv[0] != "testparm" { // checked before anything live changed
		t.Errorf("first call %v", r.calls[0].argv)
	}
	conf, _ := os.ReadFile(filepath.Join(m.P.StateDir, "smb.conf"))
	if !strings.Contains(string(conf), "[alex]") {
		t.Errorf("conf %s", conf)
	}
	pw, _ := os.ReadFile(filepath.Join(m.P.StateDir, "extrausers", "passwd"))
	if string(pw) != "alex:x:20000:20000:OneMind SMB account:/nonexistent:/usr/sbin/nologin\n" {
		t.Errorf("passwd %q", pw)
	}
	if len(m.Current()) != 2 {
		t.Errorf("current %v", m.Current())
	}
}

func TestARejectedConfigChangesNothingLive(t *testing.T) {
	m, r := newManager(t)
	r.fail["testparm"] = errors.New("exit 1")
	err := m.Apply(context.Background(), twoShares())
	var ref *Refusal
	if !errors.As(err, &ref) || ref.Reason != "config_rejected" {
		t.Fatalf("err %v", err)
	}
	for _, f := range []string{"smb.conf", "desired.json", "avahi.service"} {
		if _, err := os.Stat(filepath.Join(m.P.StateDir, f)); err == nil {
			t.Errorf("%s was written", f)
		}
	}
	if r.ran("systemctl") != 0 {
		t.Error("Samba was touched")
	}
}

func TestAnEmptyListStopsSambaAndRemovesItsConfigAndPasswords(t *testing.T) {
	m, r := newManager(t)
	if err := m.Apply(context.Background(), twoShares()); err != nil {
		t.Fatal(err)
	}
	if err := m.Apply(context.Background(), nil); err != nil {
		t.Fatal(err)
	}
	if r.ran("systemctl", "stop", Unit) != 1 || r.ran("pdbedit", "-s") != 1 {
		t.Errorf("calls: %v", r.calls)
	}
	for _, f := range []string{"smb.conf", "desired.json", "avahi.service"} {
		if _, err := os.Stat(filepath.Join(m.P.StateDir, f)); err == nil {
			t.Errorf("%s remains: nothing may stay configured", f)
		}
	}
}

func TestApplyKeepsUIDsAndDropsPeopleWhoLeft(t *testing.T) {
	m, r := newManager(t)
	a := Share{ID: "a", Kind: KindHome, Name: "alex", User: "alex", Path: "home/alex"}
	b := Share{ID: "b", Kind: KindHome, Name: "bo", User: "bo", Path: "home/bo"}
	if err := m.Apply(context.Background(), []Share{b}); err != nil { // bo first: 20000
		t.Fatal(err)
	}
	if err := m.Apply(context.Background(), []Share{a, b}); err != nil {
		t.Fatal(err)
	}
	pw, _ := os.ReadFile(filepath.Join(m.P.StateDir, "extrausers", "passwd"))
	if !strings.Contains(string(pw), "bo:x:20000:") || !strings.Contains(string(pw), "alex:x:20001:") {
		t.Errorf("uids moved: %q", pw)
	}
	if err := m.Apply(context.Background(), []Share{a}); err != nil {
		t.Fatal(err)
	}
	if r.ran("pdbedit", "-s", filepath.Join(m.P.StateDir, "smb.conf"), "-x", "-u", "bo") != 1 {
		t.Errorf("bo's Samba password stayed: %v", r.calls)
	}
}

func TestPasswordGoesOnStdinOnlyAndNeverIntoAnError(t *testing.T) {
	m, r := newManager(t)
	if err := m.Apply(context.Background(), twoShares()); err != nil {
		t.Fatal(err)
	}
	const secret = "correct horse battery"
	if err := m.SetPassword(context.Background(), "alex", secret); err != nil {
		t.Fatal(err)
	}
	last := r.calls[len(r.calls)-1]
	if last.stdin != secret+"\n"+secret+"\n" || strings.Contains(strings.Join(last.argv, " "), secret) {
		t.Errorf("password handling: %+v", last)
	}
	r.fail["smbpasswd"] = errors.New("exit 1")
	err := m.SetPassword(context.Background(), "alex", secret)
	if err == nil || strings.Contains(err.Error(), secret) {
		t.Errorf("error %v", err)
	}
	for _, bad := range []struct{ user, pw string }{{"alex", "short"}, {"alex", "line\nbreak12"}, {"mallory", secret}} {
		if m.SetPassword(context.Background(), bad.user, bad.pw) == nil {
			t.Errorf("accepted %+v", bad)
		}
	}
}

func TestNotInstalledIsRefusedWithAReason(t *testing.T) {
	m, _ := newManager(t)
	m.Have = func(p string) bool { return p != "smbd" }
	var ref *Refusal
	if err := m.Apply(context.Background(), twoShares()); !errors.As(err, &ref) || ref.Reason != "smb_not_installed" {
		t.Fatalf("err %v", err)
	}
	if !strings.Contains(m.Unavailable(), "smbd") {
		t.Error(m.Unavailable())
	}
}
