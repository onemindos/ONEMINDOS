// SPDX-License-Identifier: Apache-2.0

//go:build unix

package backup

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

// swapForSymlink simulates an app that, while root restores, replaces path by
// a symlink to target (keeping the real thing aside).
func swapForSymlink(t *testing.T, path, target string) func() {
	return func() {
		if err := os.Rename(path, path+".real"); err != nil {
			t.Error(err)
			return
		}
		if err := os.Symlink(target, path); err != nil {
			t.Error(err)
		}
	}
}

func dirEmpty(t *testing.T, dir string) bool {
	t.Helper()
	ents, err := os.ReadDir(dir)
	return err == nil && len(ents) == 0
}

// A symlink swapped in for the parent folder between the check and the write
// must not redirect the file outside the tree.
func TestRestoreFileParentSwappedForSymlink(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	sub := f.path("data/onemind/storage/photos/sub")
	file := filepath.Join(sub, "b.jpg")
	f.write("data/onemind/storage/photos/sub/b.jpg", "edited")
	elsewhere := f.path("elsewhere")
	_ = os.MkdirAll(elsewhere, 0o755)
	testHookAfterOpen = swapForSymlink(t, sub, elsewhere)
	t.Cleanup(func() { testHookAfterOpen = nil })
	_, _ = f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: file})
	if _, err := os.Lstat(sub + ".real"); err != nil {
		t.Fatal("the simulated swap never ran")
	}
	if !dirEmpty(t, elsewhere) {
		t.Fatal("restore wrote through a swapped symlink")
	}
}

func TestRestoreDirParentSwappedForSymlink(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	photos := f.path("data/onemind/storage/photos")
	elsewhere := f.path("elsewhere")
	_ = os.MkdirAll(elsewhere, 0o755)
	testHookAfterOpen = swapForSymlink(t, photos, elsewhere)
	t.Cleanup(func() { testHookAfterOpen = nil })
	_, _ = f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: filepath.Join(photos, "sub")})
	if _, err := os.Lstat(photos + ".real"); err != nil {
		t.Fatal("the simulated swap never ran")
	}
	if !dirEmpty(t, elsewhere) {
		t.Fatal("directory restore wrote through a swapped symlink")
	}
}

// A symlink swapped in for the destination file is replaced, not followed.
func TestRestoreFileDestSwappedForSymlink(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	file := f.path("data/onemind/storage/photos/a.jpg")
	outside := f.path("elsewhere-file")
	_ = os.WriteFile(outside, []byte("precious"), 0o644)
	testHookAfterOpen = swapForSymlink(t, file, outside)
	t.Cleanup(func() { testHookAfterOpen = nil })
	_, _ = f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: file})
	if b, _ := os.ReadFile(outside); string(b) != "precious" {
		t.Fatalf("outside file overwritten: %q", b)
	}
}

// Planted before the restore starts: fail closed, for a file and a directory.
func TestRestoreRefusesPlantedSymlinks(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	photos := f.path("data/onemind/storage/photos")
	elsewhere := f.path("elsewhere")
	_ = os.MkdirAll(elsewhere, 0o755)
	_ = os.WriteFile(filepath.Join(elsewhere, "x"), []byte("precious"), 0o644)

	a := filepath.Join(photos, "a.jpg")
	_ = os.Remove(a)
	_ = os.Symlink(filepath.Join(elsewhere, "x"), a)
	if _, err := f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: a}); err == nil {
		t.Fatal("restored over a symlinked file")
	}
	if b, _ := os.ReadFile(filepath.Join(elsewhere, "x")); string(b) != "precious" {
		t.Fatalf("outside file overwritten: %q", b)
	}
	sub := filepath.Join(photos, "sub")
	_ = os.RemoveAll(sub)
	_ = os.Symlink(elsewhere, sub)
	if _, err := f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: sub}); err == nil {
		t.Fatal("restored over a symlinked directory")
	}
	if ents, _ := os.ReadDir(elsewhere); len(ents) != 1 {
		t.Fatalf("outside dir changed: %v", ents)
	}
}

// The low-level opener rejects a symlink at any depth.
func TestOpenDirNoFollowRejectsSymlinkComponent(t *testing.T) {
	root := t.TempDir()
	real := filepath.Join(root, "real", "deep")
	_ = os.MkdirAll(real, 0o755)
	_ = os.Symlink(filepath.Join(root, "real"), filepath.Join(root, "link"))
	if fd, err := openDirNoFollow(filepath.Join(root, "link", "deep"), false); err == nil {
		closeDir(fd)
		t.Fatal("followed a symlink")
	}
	fd, err := openDirNoFollow(real, false)
	if err != nil {
		t.Fatal(err)
	}
	closeDir(fd)
}
