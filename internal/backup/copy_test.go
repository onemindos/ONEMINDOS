// SPDX-License-Identifier: Apache-2.0

//go:build unix

package backup

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"
)

// Design 25b: a restore into a new folder copies into an EMPTY folder under the
// Files root, overwrites nothing, leaves the app's data alone, and never copies
// a symlink.
func TestRestoreCopyIntoANewFolder(t *testing.T) {
	f := newFixture(t)
	f.agent.Cfg.CopyRoot = f.path("files")
	photos := f.path("data/onemind/storage/photos")
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	f.write("data/onemind/storage/photos/a.jpg", "edited-later")
	dest := f.path("files/spaces/p1/Restored/photos-1")
	if err := os.MkdirAll(dest, 0o750); err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()

	res, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Dest: dest})
	if err != nil {
		t.Fatal(err)
	}
	if got := f.read("files/spaces/p1/Restored/photos-1/photos/a.jpg"); got != "photo-a" {
		t.Fatalf("copied a.jpg = %q", got)
	}
	if got := f.read("files/spaces/p1/Restored/photos-1/photos/sub/b.jpg"); got != "photo-b" {
		t.Fatalf("copied b.jpg = %q", got)
	}
	if f.read("data/onemind/storage/photos/a.jpg") != "edited-later" {
		t.Fatal("the app's own data must not change")
	}
	if res.Files != 2 || res.Folders != 2 {
		t.Fatalf("result %+v", res)
	}

	// one file, into another empty folder
	one := f.path("files/spaces/p1/Restored/one")
	_ = os.MkdirAll(one, 0o750)
	if _, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Path: filepath.Join(photos, "a.jpg"), Dest: one}); err != nil {
		t.Fatal(err)
	}
	if got := f.read("files/spaces/p1/Restored/one/a.jpg"); got != "photo-a" {
		t.Fatalf("one file = %q", got)
	}

	// refusals: a folder that is not empty, outside the Files root, through a symlink, a path not in the snapshot
	if _, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Dest: dest}); err == nil || !strings.Contains(err.Error(), "not empty") {
		t.Fatalf("a non-empty folder must be refused: %v", err)
	}
	if _, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Dest: f.path("data/onemind/x")}); err == nil {
		t.Fatal("a folder outside the Files root must be refused")
	}
	link := f.path("files/spaces/p1/link")
	_ = os.Symlink(f.path("data/onemind/storage"), link)
	if _, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Dest: filepath.Join(link, "photos")}); err == nil {
		t.Fatal("a folder reached through a symlink must be refused")
	}
	empty := f.path("files/spaces/p1/Restored/empty")
	_ = os.MkdirAll(empty, 0o750)
	if _, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Path: "/etc", Dest: empty}); err == nil {
		t.Fatal("a path outside the snapshot must be refused")
	}
}

// What restic put in staging is copied as plain files and folders owned by the
// destination folder's owner; a symlink or a pipe in the snapshot is left out.
func TestCopyOwnedAtSkipsLinksAndSpecialFiles(t *testing.T) {
	stage := t.TempDir()
	dest, _ := filepath.EvalSymlinks(t.TempDir()) // macOS: /var is a symlink
	_ = os.MkdirAll(filepath.Join(stage, "d"), 0o700)
	_ = os.WriteFile(filepath.Join(stage, "d", "f"), []byte("x"), 0o400)
	_ = os.Symlink("/etc/shadow", filepath.Join(stage, "evil"))
	_ = syscallMkfifo(filepath.Join(stage, "pipe"))
	fd, err := openEmptyDir(dest)
	if err != nil {
		t.Fatal(err)
	}
	defer closeDir(fd)
	var res CopyResult
	if err := copyOwnedAt(stage, true, fd, "out", &res); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(filepath.Join(dest, "out", "evil")); !os.IsNotExist(err) {
		t.Fatal("a symlink must never be copied into a person's files")
	}
	fi, err := os.Stat(filepath.Join(dest, "out", "d", "f"))
	if err != nil || fi.Mode().Perm()&0o600 != 0o600 {
		t.Fatalf("the copy must be the owner's to read and write: %v %v", fi, err)
	}
	if res.Files != 1 || res.Skipped < 1 {
		t.Fatalf("result %+v", res)
	}
}

func syscallMkfifo(p string) error { return syscall.Mkfifo(p, 0o600) }

// Review of #1193: a copy that cannot fit is refused before anything is written,
// and an unknown free space never blocks it.
func TestRestoreCopyChecksFreeSpaceFirst(t *testing.T) {
	f := newFixture(t)
	f.agent.Cfg.CopyRoot = f.path("files")
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	dest := f.path("files/spaces/p1/Restored/full")
	if err := os.MkdirAll(dest, 0o750); err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	asked := map[string]bool{}
	f.agent.FreeBytes = func(p string) (int64, error) { asked[p] = true; return 20, nil }
	// photo-a and photo-b: 14 bytes; the folder needs 15 plus 15 to unpack, so 20 is short
	_, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Dest: dest})
	if err == nil || !strings.Contains(err.Error(), "not enough space") {
		t.Fatalf("err = %v", err)
	}
	if !asked[dest] {
		t.Fatalf("the copy's own disk was not asked: %v", asked)
	}
	if entries, _ := os.ReadDir(dest); len(entries) != 0 {
		t.Fatalf("a refused copy wrote %d entries", len(entries))
	}
	f.agent.FreeBytes = func(string) (int64, error) { return 30, nil }
	if _, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Dest: dest}); err != nil {
		t.Fatalf("enough space: %v", err)
	}
	other := f.path("files/spaces/p1/Restored/unknown")
	_ = os.MkdirAll(other, 0o750)
	f.agent.FreeBytes = func(string) (int64, error) { return 0, os.ErrPermission }
	if _, err := f.agent.RestoreCopy(ctx, CopyRequest{SnapshotID: snap.ID, Dest: other}); err != nil {
		t.Fatalf("unknown free space must not block: %v", err)
	}
}

// Review of #1193: openEmptyDir hands back an fd that it alone owns. It once
// wrapped fd in an os.File and dropped it, so the garbage collector closed fd
// under the copy (random "bad file descriptor" in unrelated tests).
func TestOpenEmptyDirFdSurvivesTheGarbageCollector(t *testing.T) {
	dir, err := filepath.EvalSymlinks(t.TempDir()) // macOS: /var is a symlink
	if err != nil {
		t.Fatal(err)
	}
	fd, err := openEmptyDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer closeDir(fd)
	for range 5 {
		runtime.GC()
		time.Sleep(time.Millisecond)
	}
	var st syscall.Stat_t
	if err := syscall.Fstat(fd, &st); err != nil {
		t.Fatalf("the fd was closed behind our back: %v", err)
	}
}
