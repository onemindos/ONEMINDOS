// SPDX-License-Identifier: Apache-2.0
//go:build linux

package localsnapshot

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

// Opt-in on a disposable Linux VM, never formats or mounts a host disk.
func TestBtrfsIntegration(t *testing.T) {
	if os.Getenv("ONEMIND_BTRFS_TEST") != "1" {
		t.Skip("requires Linux VM root and btrfs-progs")
	}
	if os.Geteuid() != 0 {
		t.Fatal("integration test requires root")
	}
	d, err := os.MkdirTemp("/run", "onemind-snapshot-test-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(d)
	run := func(name string, a ...string) {
		t.Helper()
		if b, err := exec.Command(name, a...).CombinedOutput(); err != nil {
			t.Fatalf("%s: %v: %s", name, err, b)
		}
	}
	image, mount := filepath.Join(d, "test.img"), filepath.Join(d, "mount")
	run("truncate", "-s", "512M", image)
	run("mkfs.btrfs", "-q", image)
	os.Mkdir(mount, 0700)
	run("mount", "-o", "loop", image, mount)
	defer func() { run("umount", mount) }()
	src, dst := filepath.Join(mount, "files"), filepath.Join(mount, "versions")
	run("btrfs", "subvolume", "create", src)
	os.Mkdir(dst, 0700)
	m := Manager{Config: Config{src, dst, 1, 1}}
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Second)
	os.WriteFile(filepath.Join(src, "note.txt"), []byte("yesterday"), 0600)
	if err = m.Tick(ctx, now); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(src, "note.txt"), []byte("today"), 0600)
	v, err := m.List(ctx)
	if err != nil || len(v) != 2 {
		t.Fatalf("%v %v", v, err)
	}
	b, err := os.ReadFile(filepath.Join(dst, v[0].ID, "note.txt"))
	if err != nil || string(b) != "yesterday" {
		t.Fatalf("snapshot: %q %v", b, err)
	}
	if err = os.WriteFile(filepath.Join(dst, v[0].ID, "note.txt"), []byte("changed"), 0600); err == nil {
		t.Fatal("snapshot writable")
	}
	if err = m.Tick(ctx, now.Add(48*time.Hour)); err != nil {
		t.Fatal(err)
	}
	v, err = m.List(ctx)
	if err != nil || len(v) != 2 {
		t.Fatalf("retention: %v %v", v, err)
	}
	run("btrfs", "subvolume", "create", filepath.Join(src, "nested"))
	if err = m.Tick(ctx, now.Add(72*time.Hour)); err == nil {
		t.Fatal("nested subvolume silently omitted")
	}
}
