// SPDX-License-Identifier: Apache-2.0
package localsnapshot

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type replay struct {
	calls   []string
	fail    string
	foreign bool
}

func (r *replay) Run(_ context.Context, _ string, a ...string) ([]byte, int, error) {
	s := strings.Join(a, " ")
	r.calls = append(r.calls, s)
	if r.fail != "" && strings.Contains(s, r.fail) {
		return nil, 1, nil
	}
	switch {
	case strings.HasPrefix(s, "subvolume show"):
		parent := "source-id"
		if r.foreign {
			parent = "other-source"
		}
		return []byte("UUID: source-id\nParent UUID: " + parent), 0, nil
	case strings.HasPrefix(s, "property get"):
		return []byte("ro=true\n"), 0, nil
	case strings.HasPrefix(s, "subvolume snapshot"):
		return nil, 0, os.Mkdir(a[4], 0700)
	case strings.HasPrefix(s, "subvolume delete"):
		return nil, 0, os.Remove(a[2])
	}
	return nil, 0, nil
}

func setup(t *testing.T) (Manager, *replay) {
	t.Helper()
	// Use the checkout's protected ancestors rather than world-writable /tmp.
	d, err := os.MkdirTemp(".", ".snapshot-test-")
	if err != nil {
		t.Fatal(err)
	}
	d, _ = filepath.Abs(d)
	d, _ = filepath.EvalSymlinks(d)
	t.Cleanup(func() { os.RemoveAll(d) })
	c := Config{filepath.Join(d, "source"), filepath.Join(d, "versions"), 2, 2}
	for _, p := range []string{c.Source, c.Directory} {
		if err = os.Mkdir(p, 0700); err != nil {
			t.Fatal(err)
		}
	}
	r := &replay{}
	return Manager{c, r}, r
}

func TestScheduleRetentionAndCatchup(t *testing.T) {
	m, r := setup(t)
	ctx := context.Background()
	now := time.Date(2026, 11, 19, 12, 23, 0, 0, time.UTC)
	for _, at := range []time.Time{now, now.Add(2 * time.Minute), now.Add(72 * time.Hour), now.Add(96 * time.Hour)} {
		if err := m.Tick(ctx, at); err != nil {
			t.Fatal(err)
		}
	}
	v, err := m.List(ctx)
	if err != nil || len(v) != 4 {
		t.Fatalf("versions=%+v err=%v", v, err)
	}
	if strings.Count(strings.Join(r.calls, "\n"), "subvolume snapshot") != 6 {
		t.Fatal("duplicate or backfilled snapshots", r.calls)
	}
	if _, err = os.Stat(filepath.Join(m.Config.Directory, "hourly-20261119T122300Z")); !os.IsNotExist(err) {
		t.Fatal("old hourly retained", err)
	}
}

func TestFailureNeverPrunes(t *testing.T) {
	for _, fail := range []string{"snapshot -r", "filesystem sync", "subvolume list"} {
		t.Run(fail, func(t *testing.T) {
			m, r := setup(t)
			r.fail = fail
			if err := m.Tick(context.Background(), time.Now()); err == nil {
				t.Fatal("failure ignored")
			}
			if strings.Contains(strings.Join(r.calls, "\n"), "subvolume delete") {
				t.Fatal("pruned after failure")
			}
		})
	}
}

func TestForeignAndSymlinkEntriesFailClosed(t *testing.T) {
	m, r := setup(t)
	r.foreign = true
	p := filepath.Join(m.Config.Directory, "daily-20261118T120000Z")
	os.Mkdir(p, 0700)
	if _, err := m.List(context.Background()); err == nil {
		t.Fatal("foreign snapshot accepted")
	}
	os.Remove(p)
	os.Symlink(m.Config.Source, p)
	if _, err := m.List(context.Background()); err == nil {
		t.Fatal("symlink accepted")
	}
	if strings.Contains(strings.Join(r.calls, "\n"), "delete") {
		t.Fatal("foreign data deleted")
	}
}

func TestUnsafePathsAndConfig(t *testing.T) {
	m, _ := setup(t)
	os.Chmod(m.Config.Directory, 0755)
	if _, err := m.List(context.Background()); err == nil {
		t.Fatal("public directory accepted")
	}
	os.Chmod(m.Config.Directory, 0700)
	m.Config.Source = m.Config.Directory
	if _, err := m.List(context.Background()); err == nil {
		t.Fatal("overlapping source accepted")
	}
	p := filepath.Join(m.Config.Directory, "config.json")
	os.WriteFile(p, []byte(`{"hourly":0,"daily":1}`), 0600)
	if _, err := Load(p); err == nil {
		t.Fatal("zero retention accepted")
	}
	os.Chmod(p, 0644)
	if _, err := Load(p); err == nil {
		t.Fatal("public config accepted")
	}
	unlock, err := lock(filepath.Join(m.Config.Directory, "lock"))
	if err != nil {
		t.Fatal(err)
	}
	defer unlock()
	if u, err := lock(filepath.Join(m.Config.Directory, "lock")); err == nil {
		u()
		t.Fatal("concurrent writer accepted")
	}
}

func ExampleConfig() {
	fmt.Println(`{"source":"/data/onemind/files","directory":"/data/.snapshots/files","hourly":24,"daily":7}`)
	// Output: {"source":"/data/onemind/files","directory":"/data/.snapshots/files","hourly":24,"daily":7}
}
