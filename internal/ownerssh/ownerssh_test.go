// SPDX-License-Identifier: Apache-2.0

package ownerssh

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const fp1 = "SHA256:Sm3mEwGWtcN5uE/w5uJvL4hEW37jBLnA2WL/97w+ods"
const key1 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGexample alex@laptop"

// fakeBox stands in for systemd: starting the apply unit reads the filed job and leaves a result, like
// `onemind-owner apply-job` does.
type fakeBox struct {
	dir    string
	active string
	rc     string
	jobs   []string
	starts int
}

func (f *fakeBox) Run(_ context.Context, name string, args ...string) ([]byte, error) {
	switch {
	case name == "systemctl" && args[0] == "is-active":
		return []byte(f.active + "\n"), nil
	case name == "systemctl" && args[0] == "start" && args[1] == ApplyUnit:
		f.starts++
		b, err := os.ReadFile(filepath.Join(f.dir, "job"))
		if err == nil {
			f.jobs = append(f.jobs, strings.ReplaceAll(strings.TrimSpace(string(b)), "\n", "|"))
			_ = os.Remove(filepath.Join(f.dir, "job"))
			rc := f.rc
			if rc == "" {
				rc = "0"
			}
			_ = os.WriteFile(filepath.Join(f.dir, "result"), []byte("rc="+rc+"\nonemind-owner: whatever\n"), 0o600)
		}
		_ = os.WriteFile(filepath.Join(f.dir, "keys.list"), []byte("256 "+fp1+" alex@laptop (ED25519)\n"), 0o600)
		return nil, nil
	}
	return nil, errors.New("unexpected " + name)
}

func newMgr(t *testing.T) (*Manager, *fakeBox) {
	t.Helper()
	d := t.TempDir()
	f := &fakeBox{dir: d, active: "inactive"}
	return &Manager{Dir: d, Run: f, Have: func(string) bool { return true }}, f
}

func TestStateAsksForTheListOnceAndParsesIt(t *testing.T) {
	m, f := newMgr(t)
	st, err := m.State(context.Background())
	if err != nil || !st.Enabled || st.Running || len(st.Keys) != 1 {
		t.Fatalf("%+v %v", st, err)
	}
	k := st.Keys[0]
	if k.Fingerprint != fp1 || k.Type != "ed25519" || k.Bits != 256 || k.Comment != "alex@laptop" {
		t.Fatalf("%+v", k)
	}
	if _, err := m.State(context.Background()); err != nil || f.starts != 1 {
		t.Fatalf("the list is published once, not on every read: starts=%d %v", f.starts, err)
	}
	f.active = "active"
	_ = os.WriteFile(filepath.Join(m.Dir, "disabled"), nil, 0o600)
	if st, _ := m.State(context.Background()); !st.Running || st.Enabled {
		t.Fatalf("running and the flag file are read live: %+v", st)
	}
}

func TestInternetFacingOnlyWhereTheCloudRuleShips(t *testing.T) {
	m, _ := newMgr(t)
	m.Have = func(p string) bool { return p != PublicRule }
	if st, err := m.State(context.Background()); err != nil || st.Internet {
		t.Fatalf("a home box answers the LAN and mesh only: %+v %v", st, err)
	}
	m.Have = func(string) bool { return true }
	if st, err := m.State(context.Background()); err != nil || !st.Internet {
		t.Fatalf("a cloud board (PublicRule present) is internet-facing: %+v %v", st, err)
	}
}

// The path the host service checks is the file the cloud boards really ship, and that file sends 22 to the ssh chain.
func TestPublicRuleIsTheCloudBoardsFile(t *testing.T) {
	for _, board := range []string{"cloud", "vm-do"} {
		raw, err := os.ReadFile(filepath.Join("..", "..", "os", "boards", board, "rootfs", PublicRule))
		if err != nil || !strings.Contains(string(raw), "tcp dport 22 jump ssh") {
			t.Fatalf("%s: %s must exist and send port 22 to the ssh chain: %v", board, PublicRule, err)
		}
	}
}

func TestParseKeysIgnoresNoise(t *testing.T) {
	raw := "no keys\n2048 " + fp1 + "  (RSA)\n256 " + fp1 + " a b c (ECDSA-SK)\n"
	ks := ParseKeys([]byte(raw))
	if len(ks) != 2 || ks[0].Comment != "" || ks[0].Type != "rsa" || ks[1].Comment != "a b c" || ks[1].Type != "ecdsa-sk" {
		t.Fatalf("%+v", ks)
	}
	if got := ParseKeys([]byte("no keys\n")); got == nil || len(got) != 0 {
		t.Fatalf("an empty list is an empty slice, not null: %#v", got)
	}
}

func TestAddRemoveAndSwitchFileTheRightJob(t *testing.T) {
	m, f := newMgr(t)
	ctx := context.Background()
	if err := m.AddKey(ctx, key1); err != nil {
		t.Fatal(err)
	}
	if err := m.RemoveKey(ctx, fp1); err != nil {
		t.Fatal(err)
	}
	if err := m.SetEnabled(ctx, false); err != nil {
		t.Fatal(err)
	}
	if err := m.SetEnabled(ctx, true); err != nil {
		t.Fatal(err)
	}
	want := []string{"key-add|" + key1, "key-rm|" + fp1, "ssh|off", "ssh|on"}
	if strings.Join(f.jobs, "\n") != strings.Join(want, "\n") {
		t.Fatalf("jobs %q", f.jobs)
	}
	if _, err := os.Stat(filepath.Join(m.Dir, "job")); !os.IsNotExist(err) {
		t.Fatal("a finished job file is not left behind")
	}
}

func TestRefusesWhatItMustNotPassOn(t *testing.T) {
	m, f := newMgr(t)
	ctx := context.Background()
	for _, bad := range []string{"", `command="id" ` + key1, "ssh-ed25519 AAAA\nssh-rsa BBBB", "ssh-ed25519 AAAA\x00", strings.Repeat("ssh-", 3000)} {
		var ref *Refusal
		if err := m.AddKey(ctx, bad); !errors.As(err, &ref) || ref.Reason != "invalid_key" {
			t.Errorf("%q: %v", bad[:min(len(bad), 20)], err)
		}
	}
	for _, bad := range []string{"", "SHA256:short", "MD5:aa:bb", fp1 + "\nx", "../" + fp1} {
		var ref *Refusal
		if err := m.RemoveKey(ctx, bad); !errors.As(err, &ref) || ref.Reason != "invalid_fingerprint" {
			t.Errorf("%q: %v", bad, err)
		}
	}
	if f.starts != 0 || len(f.jobs) != 0 {
		t.Fatalf("a refused request starts nothing: %d %v", f.starts, f.jobs)
	}
}

func TestToolExitCodesBecomeStableReasons(t *testing.T) {
	for rc, reason := range map[string]string{"2": "invalid_key", "3": "unsafe_home", "4": "no_such_key"} {
		m, f := newMgr(t)
		f.rc = rc
		var ref *Refusal
		if err := m.RemoveKey(context.Background(), fp1); !errors.As(err, &ref) || ref.Reason != reason {
			t.Errorf("rc %s: %v", rc, err)
		}
	}
	m, f := newMgr(t)
	f.rc = "1"
	err := m.SetEnabled(context.Background(), true)
	var ref *Refusal
	if err == nil || errors.As(err, &ref) || strings.Contains(err.Error(), "whatever") {
		t.Fatalf("an unknown failure is an error that never echoes the program's output: %v", err)
	}
}

func TestUnavailableWithoutSshdOrTool(t *testing.T) {
	m, _ := newMgr(t)
	m.Have = func(p string) bool { return p != Sshd }
	if !strings.Contains(m.Unavailable(), "sshd") {
		t.Fatal(m.Unavailable())
	}
	var ref *Refusal
	if err := m.SetEnabled(context.Background(), true); !errors.As(err, &ref) || ref.Reason != "ssh_not_installed" {
		t.Fatalf("%v", err)
	}
	m.Have = func(p string) bool { return p != Tool }
	if m.Unavailable() == "" {
		t.Fatal("no tool, no SSH management")
	}
}

func TestTooManyKeys(t *testing.T) {
	m, _ := newMgr(t)
	var b strings.Builder
	for i := 0; i < MaxKeys; i++ {
		b.WriteString("256 " + fp1 + " k (ED25519)\n")
	}
	_ = os.WriteFile(filepath.Join(m.Dir, "keys.list"), []byte(b.String()), 0o600)
	var ref *Refusal
	if err := m.AddKey(context.Background(), key1); !errors.As(err, &ref) || ref.Reason != "too_many_keys" {
		t.Fatalf("%v", err)
	}
}
