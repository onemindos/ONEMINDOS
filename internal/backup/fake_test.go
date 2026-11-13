// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
	"io/fs"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// fakeRepo is an in-memory restic stand-in. It copies real files on Backup
// and writes them back on Restore, so rewind and verify run end to end.
type fakeRepo struct {
	mu        sync.Mutex
	now       func() time.Time
	snaps     []*fakeSnap
	forgets   [][]string
	checkErrs []error
	backupErr error
	// corrupt truncates this path on every restore (verification tests).
	corrupt string
}

type fakeFile struct {
	data  []byte
	mode  os.FileMode
	mtime time.Time
	dir   bool
}

type fakeSnap struct {
	Snapshot
	files map[string]fakeFile
}

func randID() string {
	var b [32]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

func (f *fakeRepo) Init(context.Context) error { return nil }

func (f *fakeRepo) Backup(_ context.Context, req BackupRequest) (BackupResult, error) {
	if f.backupErr != nil {
		return BackupResult{}, f.backupErr
	}
	files := map[string]fakeFile{}
	var total int64
	for _, p := range req.Paths {
		for d := filepath.Dir(p); ; d = filepath.Dir(d) {
			files[filepath.ToSlash(d)] = fakeFile{dir: true, mode: 0o755}
			if d == filepath.Dir(d) {
				break
			}
		}
		err := filepath.WalkDir(p, func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			fi, err := d.Info()
			if err != nil {
				return err
			}
			ff := fakeFile{mode: fi.Mode().Perm(), mtime: fi.ModTime(), dir: d.IsDir()}
			if d.Type().IsRegular() {
				if ff.data, err = os.ReadFile(path); err != nil {
					return err
				}
				total += int64(len(ff.data))
			}
			files[filepath.ToSlash(path)] = ff
			return nil
		})
		if err != nil {
			return BackupResult{}, err
		}
	}
	return f.add(req.Paths, req.Tags, req.Host, files, total), nil
}

func (f *fakeRepo) add(paths, tags []string, host string, files map[string]fakeFile, total int64) BackupResult {
	f.mu.Lock()
	defer f.mu.Unlock()
	id := randID()
	f.snaps = append(f.snaps, &fakeSnap{Snapshot{ID: id, ShortID: id[:8], Time: f.now(), Hostname: host,
		Paths: append([]string{}, paths...), Tags: append([]string{}, tags...)}, files})
	return BackupResult{SnapshotID: id, DataAdded: total, TotalBytes: total}
}

func (f *fakeRepo) BackupStdin(_ context.Context, name string, r io.Reader, tags []string, host string) (BackupResult, error) {
	b, _ := io.ReadAll(r)
	return f.add([]string{"/" + name}, tags, host, map[string]fakeFile{"/" + name: {data: b, mode: 0o600}}, int64(len(b))), nil
}

func hasAll(tags, filter []string) bool {
	for _, want := range filter {
		found := false
		for _, t := range tags {
			found = found || t == want
		}
		if !found {
			return false
		}
	}
	return true
}

func (f *fakeRepo) Snapshots(_ context.Context, filter []string) ([]Snapshot, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	var out []Snapshot
	for _, s := range f.snaps {
		if hasAll(s.Tags, filter) {
			out = append(out, s.Snapshot)
		}
	}
	return out, nil
}

func (f *fakeRepo) Forget(_ context.Context, filter, keep []string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.forgets = append(f.forgets, append(append([]string{}, filter...), keep...))
	return nil
}

func (f *fakeRepo) Prune(context.Context) error { return nil }

func (f *fakeRepo) Check(context.Context, string) error {
	if len(f.checkErrs) == 0 {
		return nil
	}
	e := f.checkErrs[0]
	f.checkErrs = f.checkErrs[1:]
	return e
}

func (f *fakeRepo) get(id string) (*fakeSnap, error) {
	for _, s := range f.snaps {
		if s.ID == id {
			return s, nil
		}
	}
	return nil, fmt.Errorf("no snapshot %s", id)
}

func (f *fakeRepo) Ls(_ context.Context, id, dir string, recursive bool) ([]Node, error) {
	s, err := f.get(id)
	if err != nil {
		return nil, err
	}
	var nodes []Node
	for p, ff := range s.files {
		n := Node{Name: filepath.Base(p), Path: p, Type: "file", Size: int64(len(ff.data)), Mode: ff.mode, Mtime: ff.mtime}
		if ff.dir {
			n.Type, n.Size = "dir", 0
		}
		nodes = append(nodes, n)
	}
	return filterNodes(nodes, cleanSnapPath(dir), recursive), nil
}

func (f *fakeRepo) Dump(_ context.Context, id, p string, w io.Writer) error {
	s, err := f.get(id)
	if err != nil {
		return err
	}
	ff, ok := s.files[p]
	if !ok || ff.dir {
		return fmt.Errorf("dump: %s not a file", p)
	}
	_, err = w.Write(ff.data)
	return err
}

func (f *fakeRepo) Restore(_ context.Context, id, sub, target string) error {
	s, err := f.get(id)
	if err != nil {
		return err
	}
	sub = cleanSnapPath(sub)
	for p, ff := range s.files {
		if !isUnder(p, sub) || (sub != "/" && p == sub) {
			continue
		}
		rel := p
		if sub != "/" {
			rel = strings.TrimPrefix(p, sub)
		}
		dst := filepath.Join(target, filepath.FromSlash(rel))
		if ff.dir {
			if err := os.MkdirAll(dst, 0o755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
			return err
		}
		data := ff.data
		if p == f.corrupt && len(data) > 0 {
			data = data[:len(data)-1]
		}
		if err := os.WriteFile(dst, data, ff.mode); err != nil {
			return err
		}
		_ = os.Chtimes(dst, ff.mtime, ff.mtime)
	}
	return nil
}

func (f *fakeRepo) AddKey(context.Context, string) error { return nil }

// fakeSQLite stands in for the sqlite3 CLI: ".backup" copies the file and
// "PRAGMA integrity_check" says ok unless the file contains CORRUPT.
type fakeSQLite struct{}

func (fakeSQLite) Run(_ context.Context, _ string, args, _ []string, _ io.Reader, out io.Writer) ([]byte, int, error) {
	if len(args) == 3 && args[0] == "-nofollow" {
		if fi, err := os.Lstat(args[1]); err == nil && fi.Mode()&os.ModeSymlink != 0 {
			return []byte("refusing to open a symlink"), 1, fmt.Errorf("symlink")
		}
		args = args[1:]
	}
	if len(args) == 2 && strings.HasPrefix(args[1], ".backup '") {
		dst := strings.TrimSuffix(strings.TrimPrefix(args[1], ".backup '"), "'")
		b, err := os.ReadFile(args[0])
		if err != nil {
			return []byte(err.Error()), 1, err
		}
		return nil, 0, os.WriteFile(dst, b, 0o600)
	}
	if len(args) == 2 && strings.HasPrefix(args[1], "PRAGMA integrity_check") {
		b, err := os.ReadFile(args[0])
		if err != nil {
			return []byte(err.Error()), 1, err
		}
		if bytes.Contains(b, []byte("CORRUPT")) {
			_, _ = io.WriteString(out, "*** in database main ***\nPage 3: btreeInitPage() returns error code 11\n")
		} else {
			_, _ = io.WriteString(out, "ok\n")
		}
		return nil, 0, nil
	}
	return []byte("unexpected"), 1, fmt.Errorf("unexpected sqlite args %v", args)
}

// fixture is a node with a system, k3s and app unit on a temp filesystem.
type fixture struct {
	t     *testing.T
	root  string
	clock time.Time
	repo  *fakeRepo
	agent *Agent
	cfg   Config
}

func auditLines(n int) string {
	var b strings.Builder
	prev := strings.Repeat("0", 64)
	for i := 1; i <= n; i++ {
		h := fmt.Sprintf("%064x", i)
		fmt.Fprintf(&b, `{"seq":%d,"event":"x","prev_hash":"%s","hash":"%s"}`+"\n", i, prev, h)
		prev = h
	}
	return b.String()
}

func newFixture(t *testing.T) *fixture {
	t.Helper()
	root, err := filepath.EvalSymlinks(t.TempDir()) // macOS: /var is a symlink
	if err != nil {
		t.Fatal(err)
	}
	f := &fixture{t: t, root: root, clock: time.Date(2026, 11, 12, 10, 30, 0, 0, time.UTC)}
	f.write("data/onemind/gateway/onemind.db", "gateway-db")
	f.write("data/onemind/custodian/ca.pem", "ca")
	f.write("data/onemind/audit/audit.jsonl", auditLines(3)+`{"seq":4,"half`)
	f.write("k3s/state.db", "k3s-state")
	f.write("k3s/token", "tok")
	f.write("data/onemind/storage/photos/a.jpg", "photo-a")
	f.write("data/onemind/storage/photos/sub/b.jpg", "photo-b")
	f.write("data/onemind/identity/node.json", "{}")
	f.write("secrets/device.key", "k")

	c := DefaultConfig()
	c.BoxID, c.NodeID = "box1", "node1"
	c.StateDir, c.ScratchDir = f.path("state"), f.path("scratch")
	c.DeviceKeyFile = f.path("secrets/device.key")
	c.Restic.SkipPinCheck = true
	c.Schedule.Minute = 17
	c.Targets = []Target{
		{ID: "usb1", Kind: KindUSB, Primary: true, USBUUID: "1234-ABCD", MountRoot: f.path("mnt"), AllowNonMountDir: true},
		{ID: "peer", Kind: KindNode, URL: "https://peer.example:8000/box1/", User: "box1", PasswordFile: f.path("secrets/device.key"), AppendOnly: true},
	}
	c.Units = UnitsSpec{
		System: &SystemSpec{PathsSpec: PathsSpec{Paths: []string{f.path("data/onemind/custodian")}},
			SQLite: []SQLiteFile{{Path: f.path("data/onemind/gateway/onemind.db"), Name: "gateway.db"}}, AuditLog: f.path("data/onemind/audit/audit.jsonl")},
		K3s:  &K3sSpec{PathsSpec: PathsSpec{Paths: []string{f.path("k3s/token")}}, StateDB: f.path("k3s/state.db"), Version: "v1.33.5-k3s1"},
		Apps: []AppSpec{{ID: "photos", Revision: "r3", Paths: []string{f.path("data/onemind/storage/photos")}}},
		Node: &PathsSpec{Paths: []string{f.path("data/onemind/identity")}},
	}
	if err := c.Validate(); err != nil {
		t.Fatal(err)
	}
	f.cfg = c
	f.repo = &fakeRepo{now: func() time.Time { return f.clock }}
	f.agent = f.newAgent(c)
	return f
}

func (f *fixture) newAgent(c Config) *Agent {
	st, err := OpenStore(filepath.Join(c.StateDir, "state.json"))
	if err != nil {
		f.t.Fatal(err)
	}
	a := newAgent(c, st)
	a.Now = func() time.Time { return f.clock }
	a.Log = slog.New(slog.NewTextHandler(io.Discard, nil))
	a.OpenRepo = func(Target) (Repo, error) { return f.repo, nil }
	units := BuildUnits(&a.Cfg, fakeSQLite{})
	a.Units = func(context.Context) ([]Unit, error) { return units, nil }
	a.FreeBytes = func(string) (int64, error) { return 1 << 40, nil }
	return a
}

func (f *fixture) path(rel string) string { return filepath.Join(f.root, filepath.FromSlash(rel)) }

func (f *fixture) write(rel, content string) {
	f.t.Helper()
	p := f.path(rel)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		f.t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(content), 0o600); err != nil {
		f.t.Fatal(err)
	}
}

func (f *fixture) read(rel string) string {
	f.t.Helper()
	b, err := os.ReadFile(f.path(rel))
	if err != nil {
		f.t.Fatal(err)
	}
	return string(b)
}

func (f *fixture) run(reason string) Run {
	f.t.Helper()
	r, err := f.agent.Run(context.Background(), RunRequest{Reason: reason})
	if err != nil {
		f.t.Fatal(err)
	}
	return r
}
