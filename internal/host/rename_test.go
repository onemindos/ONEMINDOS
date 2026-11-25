// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type fakeNames struct {
	set     []string
	reloads int
	err     error
}

func (f *fakeNames) Reload(context.Context) error { f.reloads++; return nil }

func (f *fakeNames) Set(_ context.Context, n string) error {
	f.set = append(f.set, n)
	return f.err
}

func TestSetHostnameRunsOnlyAnApprovedLabel(t *testing.T) {
	s, p := newService(t, t.TempDir(), "boot-1")
	if why := s.Unavailable(KindSetHostname); why == "" {
		t.Fatal("no Names: set-hostname must be unavailable")
	}
	n := &fakeNames{}
	s.Names = n
	for _, bad := range []Request{
		{ActionID: "a", Kind: KindSetHostname},                                    // no name
		{ActionID: "a", Kind: KindRestart, Hostname: "kitchen"},                   // name on another kind
		{ActionID: "a", Kind: KindSetHostname, Hostname: "Kitchen"},               // upper case
		{ActionID: "a", Kind: KindSetHostname, Hostname: "a.b"},                   // not one label
		{ActionID: "a", Kind: KindSetHostname, Hostname: "-kitchen"},              // leading dash
		{ActionID: "a", Kind: KindSetHostname, Hostname: "kitchen\nroot"},         // newline
		{ActionID: "a", Kind: KindSetHostname, Hostname: strings.Repeat("a", 64)}, // too long
		{ActionID: "a", Kind: KindSetHostname, Hostname: "kitchen", Unit: "x.service"},
	} {
		if err := bad.Validate(); err == nil {
			t.Errorf("%+v was valid", bad)
		}
	}
	op, created, err := s.Submit(context.Background(), Request{ActionID: "act-name", Kind: KindSetHostname, Hostname: "kitchen"})
	if err != nil || !created || op.Hostname != "kitchen" {
		t.Fatalf("%+v %v %v", op, created, err)
	}
	s.Wait()
	got, _ := s.Store.Get("act-name")
	if n.reloads != 1 {
		t.Fatalf("the gateway must be restarted once after a rename, got %d", n.reloads)
	}
	if got.State != StateSucceeded || len(n.set) != 1 || n.set[0] != "kitchen" || p.reboots != 0 {
		t.Fatalf("journal %+v, set %v, reboots %d", got, n.set, p.reboots)
	}
	var ref *Refusal
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-name", Kind: KindSetHostname, Hostname: "garage"}); !errors.As(err, &ref) || ref.Reason != "action_id_reused" {
		t.Fatalf("reused id: %v", err)
	}
	if _, created, err := s.Submit(context.Background(), Request{ActionID: "act-name", Kind: KindSetHostname, Hostname: "kitchen"}); err != nil || created || len(n.set) != 1 {
		t.Fatalf("a retry must not run twice: %v %v %v", created, err, n.set)
	}
	n.err = errors.New("exit status 1")
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-fail", Kind: KindSetHostname, Hostname: "garage"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if got, _ := s.Store.Get("act-fail"); got.State != StateFailed || got.Reason != "host_error" {
		t.Fatalf("a failed rename is reported failed: %+v", got)
	}
}

func TestSystemHostnameSavesTheNameAndAsksHostnamedAndAvahi(t *testing.T) {
	dir := t.TempDir()
	hosts := filepath.Join(dir, "hosts")
	if err := os.WriteFile(hosts, []byte("127.0.0.1\tlocalhost\n127.0.1.1\tonemind\n::1\t\tlocalhost\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	var calls []string
	// The name before the rename is the one the host service started with.
	old, err := os.Hostname()
	if err != nil || !nodeNameRe.MatchString(strings.ToLower(old)) {
		t.Skip("this machine's host name is not a node name")
	}
	h := SystemHostname{File: filepath.Join(dir, "etc", "hostname"), K3sEnv: filepath.Join(dir, "etc", "k3s.env"), Hosts: hosts,
		Run: func(_ context.Context, name string, args ...string) ([]byte, error) {
			calls = append(calls, name+" "+strings.Join(args, " "))
			return nil, nil
		}}
	if err := h.Set(context.Background(), "kitchen"); err != nil {
		t.Fatal(err)
	}
	if b, _ := os.ReadFile(h.File); string(b) != "kitchen\n" {
		t.Fatalf("saved name %q", b)
	}
	// The Kubernetes node keeps the name it had; a second rename does not move the pin.
	if b, _ := os.ReadFile(h.K3sEnv); string(b) != "K3S_NODE_NAME="+strings.ToLower(old)+"\n" {
		t.Fatalf("node name pin %q", b)
	}
	if b, _ := os.ReadFile(hosts); string(b) != "127.0.0.1\tlocalhost\n127.0.1.1\tkitchen\n::1\t\tlocalhost\n" {
		t.Fatalf("hosts %q", b)
	}
	want := []string{"hostnamectl --transient set-hostname kitchen", "systemctl try-restart avahi-daemon.service"}
	if strings.Join(calls, "|") != strings.Join(want, "|") {
		t.Fatalf("calls %v", calls)
	}
	if err := h.Set(context.Background(), "garage"); err != nil {
		t.Fatal(err)
	}
	if b, _ := os.ReadFile(h.K3sEnv); string(b) != "K3S_NODE_NAME="+strings.ToLower(old)+"\n" {
		t.Fatalf("a second rename moved the node name pin: %q", b)
	}
	calls = nil
	if err := h.Reload(context.Background()); err != nil || strings.Join(calls, "|") != "systemctl try-restart onemind-gateway.service" {
		t.Fatalf("reload: %v %v", err, calls)
	}
	if err := h.Set(context.Background(), "Not A Label"); err == nil {
		t.Fatal("a bad name must be refused before anything is written")
	}
	h.Run = func(context.Context, string, ...string) ([]byte, error) {
		return []byte("denied"), errors.New("exit 1")
	}
	if err := h.Set(context.Background(), "garage"); err == nil || !strings.Contains(err.Error(), "denied") {
		t.Fatalf("hostnamectl failure must surface: %v", err)
	}
}

func TestApplyHostnameAtBoot(t *testing.T) {
	dir := t.TempDir()
	file, hosts := filepath.Join(dir, "hostname"), filepath.Join(dir, "etc-hosts")
	var set []string
	do := func(n string) error { set = append(set, n); return nil }
	if n, err := ApplyHostname(file, hosts, do); n != "" || err != nil || len(set) != 0 {
		t.Fatalf("never renamed: nothing changes (%q %v %v)", n, err, set)
	}
	os.WriteFile(file, []byte("../etc\n"), 0o644)
	if _, err := ApplyHostname(file, hosts, do); err == nil || len(set) != 0 {
		t.Fatalf("a bad file must not be applied: %v %v", err, set)
	}
	os.WriteFile(file, []byte("kitchen\n"), 0o644)
	os.WriteFile(hosts, []byte("127.0.0.1\tlocalhost\n"), 0o644)
	if n, err := ApplyHostname(file, hosts, do); n != "kitchen" || err != nil || len(set) != 1 || set[0] != "kitchen" {
		t.Fatalf("%q %v %v", n, err, set)
	}
	if b, _ := os.ReadFile(hosts); !strings.Contains(string(b), "127.0.1.1\tkitchen\n") {
		t.Fatalf("hosts %q", b)
	}
	if n, err := CurrentHostname(file); n != "kitchen" || err != nil {
		t.Fatalf("%q %v", n, err)
	}
}
