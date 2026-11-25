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
		Aliases: filepath.Join(dir, "etc", "mdns-aliases"),
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
	want := []string{"systemctl start onemind-hostname.service", "systemctl try-restart avahi-daemon.service", "systemctl restart onemind-mdns-aliases.service"}
	if strings.Join(calls, "|") != strings.Join(want, "|") {
		t.Fatalf("calls %v", calls)
	}
	// The old names keep answering: onemind.local and the name the box had until now.
	if got := ReadAliases(h.Aliases); strings.Join(got, ",") != strings.Join(MergeAliases(nil, strings.ToLower(old), "kitchen"), ",") {
		t.Fatalf("aliases after the first rename: %v", got)
	}
	if err := h.Set(context.Background(), "garage"); err != nil {
		t.Fatal(err)
	}
	if got := ReadAliases(h.Aliases); strings.Join(got, ",") != strings.Join(MergeAliases([]string{"kitchen", "onemind"}, strings.ToLower(old), "garage"), ",") {
		t.Fatalf("aliases after the second rename: %v", got)
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
	if err := h.Set(context.Background(), "attic"); err == nil || !strings.Contains(err.Error(), "denied") {
		t.Fatalf("helper unit failure must surface: %v", err)
	}
	// The failed rename is rolled back on disk: the next boot must not apply a name the owner was told failed.
	if b, _ := os.ReadFile(h.File); string(b) != "garage\n" {
		t.Fatalf("a failed rename left %q in the saved name", b)
	}
	if got := ReadAliases(h.Aliases); strings.Contains(strings.Join(got, ","), "attic") {
		t.Fatalf("a failed rename left aliases %v", got)
	}
}

func TestSystemHostnameRollsBackWhenTheHostsFileFails(t *testing.T) {
	dir := t.TempDir()
	hosts := filepath.Join(dir, "hosts-dir") // a directory: rewriting it fails
	if err := os.Mkdir(hosts, 0o755); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Hostname(); err != nil {
		t.Skip(err)
	}
	var calls []string
	h := SystemHostname{File: filepath.Join(dir, "hostname"), K3sEnv: filepath.Join(dir, "k3s.env"), Hosts: hosts,
		Aliases: filepath.Join(dir, "mdns-aliases"), NoMDNS: true,
		Run: func(_ context.Context, name string, args ...string) ([]byte, error) {
			calls = append(calls, name+" "+strings.Join(args, " "))
			return nil, nil
		}}
	if err := os.WriteFile(h.File, []byte("garage\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := h.Set(context.Background(), "attic"); err == nil {
		t.Fatal("a hosts file failure must fail the rename")
	}
	if b, _ := os.ReadFile(h.File); string(b) != "garage\n" {
		t.Fatalf("saved name not restored: %q", b)
	}
	if _, err := os.Stat(h.Aliases); !os.IsNotExist(err) {
		t.Fatalf("alias list not removed: %v", err)
	}
	// The helper ran again so the running name goes back to the restored one.
	if len(calls) != 2 || calls[1] != "systemctl start onemind-hostname.service" {
		t.Fatalf("calls %v", calls)
	}
}

func TestAvahiFailureAfterTheRenameIsOnlyAWarning(t *testing.T) {
	dir := t.TempDir()
	if _, err := os.Hostname(); err != nil {
		t.Skip(err)
	}
	h := SystemHostname{File: filepath.Join(dir, "hostname"), K3sEnv: filepath.Join(dir, "k3s.env"), Hosts: filepath.Join(dir, "none"),
		Aliases: filepath.Join(dir, "mdns-aliases"),
		Run: func(_ context.Context, _ string, args ...string) ([]byte, error) {
			if len(args) > 1 && args[1] == "avahi-daemon.service" {
				return []byte("no avahi"), errors.New("exit 1")
			}
			return nil, nil
		}}
	if err := h.Set(context.Background(), "attic"); err != nil {
		t.Fatalf("the box is renamed; an avahi failure must not report failure: %v", err)
	}
	if b, _ := os.ReadFile(h.File); string(b) != "attic\n" {
		t.Fatalf("saved name %q", b)
	}
}

func TestMergeAliases(t *testing.T) {
	got := MergeAliases([]string{"old", "BAD NAME", " kitchen "}, "garage", "kitchen")
	if strings.Join(got, ",") != "garage,old,onemind" {
		t.Fatalf("%v", got)
	}
	if got := MergeAliases(nil, "onemind", "onemind"); len(got) != 0 {
		t.Fatalf("the current name is never an alias: %v", got)
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
