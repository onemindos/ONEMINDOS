// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// scriptRunner records calls and answers from a table keyed by subcommand.
type scriptRunner struct {
	calls []call
	reply func(args []string) (stdout string, code int)
}

type call struct{ args, env []string }

func (s *scriptRunner) Run(_ context.Context, _ string, args, env []string, _ io.Reader, out io.Writer) ([]byte, int, error) {
	s.calls = append(s.calls, call{args, env})
	stdout, code := "", 0
	if s.reply != nil {
		stdout, code = s.reply(args)
	}
	_, _ = io.WriteString(out, stdout)
	if code != 0 {
		return []byte("Fatal: something\n"), code, errors.New("exit status")
	}
	return nil, 0, nil
}

func sub(args []string) string {
	for _, a := range args {
		if !strings.HasPrefix(a, "-") && !strings.HasSuffix(a, ".pem") {
			return a
		}
	}
	return ""
}

func secretFile(t *testing.T, dir, name, v string) string {
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(v+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestNodeTargetKeepsSecretsOffTheCommandLine(t *testing.T) {
	dir := t.TempDir()
	c := DefaultConfig()
	c.DeviceKeyFile = "/k"
	tg := Target{ID: "peer", Kind: KindNode, URL: "https://peer.example:8000/box1/", User: "box1",
		PasswordFile: secretFile(t, dir, "pw", "s3cret-pw"), CAFile: "/ca.pem"}
	r := &scriptRunner{}
	rs, err := NewRestic(&c, tg, r)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = rs.Snapshots(context.Background(), []string{"onemind", "unit=system"})
	got := r.calls[0]
	joined := strings.Join(got.args, " ")
	if strings.Contains(joined, "s3cret") || !strings.Contains(strings.Join(got.env, "\n"), "RESTIC_REST_PASSWORD=s3cret-pw") {
		t.Fatalf("args %v env %v", got.args, got.env)
	}
	if joined != "--cacert /ca.pem snapshots --json --tag onemind,unit=system" {
		t.Fatalf("args = %q (one --tag with a comma list means AND)", joined)
	}
	for _, e := range got.env {
		if strings.HasPrefix(e, "HOME=") || strings.HasPrefix(e, "AWS_") {
			t.Fatalf("inherited env leaked: %s", e)
		}
	}
	if !strings.Contains(strings.Join(got.env, "\n"), "RESTIC_REPOSITORY=rest:https://peer.example:8000/box1/") {
		t.Fatalf("env = %v", got.env)
	}
}

func TestS3TargetRepositoryString(t *testing.T) {
	dir := t.TempDir()
	c := DefaultConfig()
	tg := Target{ID: "s3", Kind: KindS3, Endpoint: "https://s3.example.com/", Bucket: "b", Prefix: "/onemind/box1/",
		AccessKeyFile: secretFile(t, dir, "ak", "AK"), SecretKeyFile: secretFile(t, dir, "sk", "SK"), Region: "eu-1"}
	rs, err := NewRestic(&c, tg, &scriptRunner{})
	if err != nil {
		t.Fatal(err)
	}
	env := strings.Join(rs.Env, "\n")
	if rs.Repo != "s3:https://s3.example.com/b/onemind/box1" || !strings.Contains(env, "AWS_SECRET_ACCESS_KEY=SK") || !strings.Contains(env, "AWS_DEFAULT_REGION=eu-1") {
		t.Fatalf("repo %q env %q", rs.Repo, env)
	}
	tg.SecretKeyFile = secretFile(t, dir, "empty", "")
	if _, err := NewRestic(&c, tg, &scriptRunner{}); err == nil {
		t.Fatal("empty secret accepted")
	}
}

func TestInitOnlyWhenMissing(t *testing.T) {
	c := DefaultConfig()
	tg := Target{ID: "u", Kind: KindUSB, USBUUID: "AB-12", MountRoot: "/run/onemind/backup"}
	r := &scriptRunner{reply: func(a []string) (string, int) {
		if sub(a) == "cat" {
			return "", exitNoRepo
		}
		return "", 0
	}}
	rs, _ := NewRestic(&c, tg, r)
	if rs.Repo != "/run/onemind/backup/AB-12/onemind-restic" {
		t.Fatalf("repo = %s", rs.Repo)
	}
	if err := rs.Init(context.Background()); err != nil || len(r.calls) != 2 || sub(r.calls[1].args) != "init" {
		t.Fatalf("init: %v %v", err, r.calls)
	}
	r = &scriptRunner{reply: func([]string) (string, int) { return "", exitWrongKey }}
	rs, _ = NewRestic(&c, tg, r)
	if err := rs.Init(context.Background()); err == nil || len(r.calls) != 1 {
		t.Fatal("wrong key must not lead to init")
	}
}

func TestBackupArgsAndIncomplete(t *testing.T) {
	c := DefaultConfig()
	summary := `{"message_type":"status","percent_done":0.5}
{"message_type":"summary","snapshot_id":"abcdef0123","data_added":42,"total_bytes_processed":100}
`
	code := 0
	r := &scriptRunner{reply: func([]string) (string, int) { return summary, code }}
	rs, _ := NewRestic(&c, Target{ID: "u", Kind: KindUSB, USBUUID: "X", MountRoot: "/m"}, r)
	res, err := rs.Backup(context.Background(), BackupRequest{Paths: []string{"/a", "-weird"}, Excludes: []string{"cache/"}, Tags: []string{"onemind", "unit=x"}, Host: "n1"})
	if err != nil || res.SnapshotID != "abcdef0123" || res.DataAdded != 42 || res.Incomplete {
		t.Fatalf("res %+v err %v", res, err)
	}
	if got := strings.Join(r.calls[0].args, " "); got != "backup --json --host n1 --tag onemind --tag unit=x --exclude cache/ -- /a -weird" {
		t.Fatalf("args = %q", got)
	}
	code = exitIncomplete
	if res, err := rs.Backup(context.Background(), BackupRequest{Paths: []string{"/a"}, Host: "n1"}); err != nil || !res.Incomplete {
		t.Fatalf("exit 3: %+v %v", res, err)
	}
	code = exitLocked
	if _, err := rs.Backup(context.Background(), BackupRequest{Paths: []string{"/a"}, Host: "n1"}); !IsLocked(err) {
		t.Fatalf("exit 11: %v", err)
	}
}

func TestForgetLsRestoreArgs(t *testing.T) {
	c := DefaultConfig()
	ls := `{"time":"2026-11-12T10:00:00Z","paths":["/d"],"id":"x","struct_type":"snapshot","message_type":"snapshot"}
{"name":"d","type":"dir","path":"/d","mode":2147484141,"mtime":"2026-11-01T00:00:00Z","struct_type":"node","message_type":"node"}
{"name":"a","type":"file","path":"/d/a","size":3,"mode":420,"mtime":"2026-11-01T00:00:00Z","struct_type":"node","message_type":"node"}
{"name":"s","type":"dir","path":"/d/s","mode":2147484141,"mtime":"2026-11-01T00:00:00Z","struct_type":"node","message_type":"node"}
{"name":"b","type":"file","path":"/d/s/b","size":1,"mode":384,"mtime":"2026-11-01T00:00:00Z","struct_type":"node","message_type":"node"}
`
	r := &scriptRunner{reply: func(a []string) (string, int) {
		if sub(a) == "ls" {
			return ls, 0
		}
		return "", 0
	}}
	rs, _ := NewRestic(&c, Target{ID: "u", Kind: KindUSB, USBUUID: "X", MountRoot: "/m"}, r)
	ctx := context.Background()
	if err := rs.Forget(ctx, nil, nil); err == nil {
		t.Fatal("unfiltered forget accepted")
	}
	_ = rs.Forget(ctx, []string{"onemind", "box=b"}, []string{"--keep-hourly", "24"})
	if got := strings.Join(r.calls[0].args, "|"); got != "forget|--tag|onemind,box=b|--group-by||--keep-hourly|24" {
		t.Fatalf("forget = %q", got)
	}
	nodes, _ := rs.Ls(ctx, "x", "/d", false)
	if len(nodes) != 2 || nodes[0].Name != "a" || nodes[0].Mode.Perm() != 0o644 || !nodes[0].Mtime.Equal(time.Date(2026, 11, 1, 0, 0, 0, 0, time.UTC)) {
		t.Fatalf("ls direct = %+v", nodes)
	}
	if nodes, _ := rs.Ls(ctx, "x", "/", true); len(nodes) != 4 {
		t.Fatalf("ls recursive = %d", len(nodes))
	}
	_ = rs.Restore(ctx, "x", "/d/s", "/tmp/t")
	_ = rs.Restore(ctx, "x", "/", "/tmp/t")
	_ = rs.Dump(ctx, "x", "/d/../d/a", io.Discard)
	n := len(r.calls)
	if a := strings.Join(r.calls[n-3].args, " "); a != "restore --target /tmp/t -- x:/d/s" {
		t.Fatalf("restore sub = %q", a)
	}
	if a := strings.Join(r.calls[n-2].args, " "); a != "restore --target /tmp/t -- x" {
		t.Fatalf("restore all = %q", a)
	}
	if a := strings.Join(r.calls[n-1].args, " "); a != "dump -- x /d/a" {
		t.Fatalf("dump = %q", a)
	}
}

func TestPins(t *testing.T) {
	for _, arch := range []string{"amd64", "arm64"} {
		for _, name := range []string{"restic", "rest-server"} {
			p, ok := PinFor(name, arch)
			if !ok || len(p.BinarySHA256) != 64 || len(p.ArchiveSHA256) != 64 || !strings.Contains(p.Archive, p.Version) || p.License != "BSD-2-Clause" {
				t.Fatalf("%s/%s: %+v", name, arch, p)
			}
		}
	}
	if p, _ := PinFor("restic", "arm64"); p.Version != "0.19.1" {
		t.Fatalf("restic must stay on the B-R1 pin, got %s", p.Version)
	}
	bin := filepath.Join(t.TempDir(), "restic")
	_ = os.WriteFile(bin, []byte("not restic"), 0o755)
	p, _ := PinFor("restic", "amd64")
	if err := VerifyBinary(bin, p); err == nil || !strings.Contains(err.Error(), "not the pinned") {
		t.Fatalf("verify = %v", err)
	}
	c := DefaultConfig()
	c.BoxID, c.NodeID, c.Restic.Binary = "b", "n", bin
	c.DeviceKeyFile = secretFile(t, t.TempDir(), "k", "key")
	if _, err := New(c); err == nil {
		t.Fatal("New accepted an unpinned restic")
	}
}

func TestConfigValidate(t *testing.T) {
	base := func() Config {
		c := DefaultConfig()
		c.BoxID, c.NodeID = "box1", "node1"
		c.Targets = []Target{{ID: "u", Kind: KindUSB, USBUUID: "AB-12", Primary: true}}
		return c
	}
	if c := base(); c.Validate() != nil || c.Targets[0].MountRoot != "/run/onemind/backup" {
		t.Fatalf("base invalid or mount root not defaulted: %v", c.Validate())
	}
	for name, mut := range map[string]func(*Config){
		"comma in box id": func(c *Config) { c.BoxID = "a,b" },
		"two primaries": func(c *Config) {
			c.Targets = append(c.Targets, Target{ID: "v", Kind: KindUSB, USBUUID: "CD", Primary: true})
		},
		"no primary": func(c *Config) { c.Targets[0].Primary = false },
		"http node": func(c *Config) {
			c.Targets = append(c.Targets, Target{ID: "n", Kind: KindNode, URL: "http://x/", User: "u", PasswordFile: "/p"})
		},
		"empty retention":     func(c *Config) { c.Retention = Retention{} },
		"relative state":      func(c *Config) { c.StateDir = "state" },
		"bad app id":          func(c *Config) { c.Units.Apps = []AppSpec{{ID: "a=b"}} },
		"usb uuid slash":      func(c *Config) { c.Targets[0].USBUUID = "../x" },
		"unknown kind":        func(c *Config) { c.Targets[0].Kind = "ftp" },
		"minute out of range": func(c *Config) { c.Schedule.Minute = 60 },
	} {
		c := base()
		mut(&c)
		if c.Validate() == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	p := filepath.Join(t.TempDir(), "agent.json")
	_ = os.WriteFile(p, []byte(`{"box_id":"b","node_id":"n","schedule":{"minute":5,"verify_min_age":"30m"},
		"targets":[{"id":"u","kind":"usb","usb_uuid":"AB","primary":true}]}`), 0o600)
	c, err := LoadConfig(p)
	if err != nil || c.Schedule.VerifyMinAge.Duration != 30*time.Minute || c.Retention.Monthly != 12 || c.Schedule.MaintenanceHour != 3 {
		t.Fatalf("load: %+v %v", c, err)
	}
}

func TestRunMinuteIsStablePerBox(t *testing.T) {
	a, b := Config{BoxID: "box-a", Schedule: Schedule{Minute: -1}}, Config{BoxID: "box-a", Schedule: Schedule{Minute: -1}}
	if a.RunMinute() != b.RunMinute() || a.RunMinute() < 0 || a.RunMinute() > 59 {
		t.Fatal("derived minute not stable")
	}
	seen := map[int]bool{}
	for _, id := range []string{"a", "b", "c", "d", "e", "f", "g", "h"} {
		seen[(&Config{BoxID: id, Schedule: Schedule{Minute: -1}}).RunMinute()] = true
	}
	if len(seen) < 4 {
		t.Fatalf("minutes do not spread: %v", seen)
	}
}
