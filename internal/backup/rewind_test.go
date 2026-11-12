// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func appSnapshot(t *testing.T, f *fixture) SnapshotInfo {
	t.Helper()
	list, err := f.agent.ListSnapshots(context.Background(), "", "app:photos")
	if err != nil || len(list) == 0 {
		t.Fatalf("list: %v %v", list, err)
	}
	return list[0]
}

func TestListTreeAndDump(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	f.clock = f.clock.Add(time.Hour)
	f.run(ReasonScheduled)
	all, _ := f.agent.ListSnapshots(context.Background(), "", "")
	if len(all) != 8 || !all[0].TakenAt.After(all[7].TakenAt) {
		t.Fatalf("list = %d entries, newest first?", len(all))
	}
	s := appSnapshot(t, f)
	if s.AppID != "photos" || s.AppRevision != "r3" || s.Reason != ReasonScheduled || s.NodeID != "node1" {
		t.Fatalf("info = %+v", s)
	}
	tree, err := f.agent.Tree(context.Background(), "", s.ShortID, f.path("data/onemind/storage/photos"))
	if err != nil || len(tree) != 2 || tree[0].Name != "a.jpg" || tree[0].Type != "file" || tree[1].Type != "dir" {
		t.Fatalf("tree = %+v %v", tree, err)
	}
	var buf bytes.Buffer
	if err := f.agent.DumpFile(context.Background(), "", s.ID, f.path("data/onemind/storage/photos/sub/b.jpg"), &buf); err != nil || buf.String() != "photo-b" {
		t.Fatalf("dump = %q %v", buf.String(), err)
	}
	if err := f.agent.DumpFile(context.Background(), "", s.ID, f.path("data/onemind/storage/photos/sub"), &buf); err == nil {
		t.Fatal("dumped a directory")
	}
	if _, err := f.agent.Tree(context.Background(), "", "abc", "/"); err == nil {
		t.Fatal("short id accepted")
	}
}

// FILES-7 / BT-5: a restored file matches the snapshot's content and mtime,
// and restoring the pre-restore snapshot undoes it.
func TestRestoreFileAndUndo(t *testing.T) {
	f := newFixture(t)
	mtime := time.Date(2025, 1, 2, 3, 4, 5, 0, time.UTC)
	file := f.path("data/onemind/storage/photos/a.jpg")
	_ = os.Chtimes(file, mtime, mtime)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)

	f.write("data/onemind/storage/photos/a.jpg", "edited-later")
	f.clock = f.clock.Add(time.Hour)
	res, err := f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: file})
	if err != nil {
		t.Fatal(err)
	}
	fi, _ := os.Stat(file)
	if f.read("data/onemind/storage/photos/a.jpg") != "photo-a" || !fi.ModTime().Equal(mtime) || res.PreRestoreSnapshotID == "" {
		t.Fatalf("restored %q mtime %v result %+v", f.read("data/onemind/storage/photos/a.jpg"), fi.ModTime(), res)
	}
	pre, _ := f.repo.Snapshots(context.Background(), []string{"reason=pre-restore", "keep=14d", "unit=app:photos"})
	if len(pre) != 1 || pre[0].ID != res.PreRestoreSnapshotID {
		t.Fatalf("pre-restore snapshot = %v", pre)
	}
	if _, err := f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: res.PreRestoreSnapshotID, Path: file}); err != nil {
		t.Fatal(err)
	}
	if got := f.read("data/onemind/storage/photos/a.jpg"); got != "edited-later" {
		t.Fatalf("undo gave %q", got)
	}
	leftovers, _ := filepath.Glob(f.path("data/onemind/storage/photos/.onemind-restore-*"))
	if len(leftovers) != 0 {
		t.Fatalf("temp files left: %v", leftovers)
	}
}

func TestRestoreDeletedDirectory(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	dir := f.path("data/onemind/storage/photos/sub")
	os.RemoveAll(dir)
	res, err := f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: dir})
	if err != nil || res.PreRestoreSnapshotID != "" || res.Type != "dir" {
		t.Fatalf("res %+v err %v", res, err)
	}
	if f.read("data/onemind/storage/photos/sub/b.jpg") != "photo-b" {
		t.Fatal("directory content not restored")
	}
	// over an existing directory: old content is replaced, not merged
	f.write("data/onemind/storage/photos/sub/new.jpg", "n")
	res, err = f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: dir})
	if err != nil || res.PreRestoreSnapshotID == "" {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, "new.jpg")); !os.IsNotExist(err) {
		t.Fatal("newer file survived a directory restore")
	}
	old, _ := filepath.Glob(dir + ".onemind-old-*")
	if len(old) != 0 {
		t.Fatalf("moved-aside directory left: %v", old)
	}
}

func TestRestoreRefusals(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	sys, _ := f.agent.ListSnapshots(context.Background(), "", "system")
	cases := map[string]RestoreRequest{
		"outside snapshot": {SnapshotID: snap.ID, Path: f.path("k3s/token")},
		"traversal":        {SnapshotID: snap.ID, Path: f.path("data/onemind/storage/photos/../../identity/node.json")},
		"staging copy":     {SnapshotID: sys[0].ID, Path: filepath.Join(f.cfg.StateDir, "staging", "system", "gateway.db")},
		"missing in snap":  {SnapshotID: snap.ID, Path: f.path("data/onemind/storage/photos/nope.jpg")},
		"unknown snapshot": {SnapshotID: strings.Repeat("a", 64), Path: f.path("data/onemind/storage/photos/a.jpg")},
	}
	for name, req := range cases {
		if _, err := f.agent.RestorePath(context.Background(), req); err == nil {
			t.Errorf("%s: restore allowed", name)
		}
	}
	// a symlinked parent cannot redirect the write
	sub := f.path("data/onemind/storage/photos/sub")
	os.RemoveAll(sub)
	elsewhere := f.path("elsewhere")
	_ = os.MkdirAll(elsewhere, 0o755)
	_ = os.Symlink(elsewhere, sub)
	if _, err := f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: filepath.Join(sub, "b.jpg")}); err == nil || !strings.Contains(err.Error(), "symlink") {
		t.Fatalf("symlink parent: %v", err)
	}
	if _, err := os.Stat(filepath.Join(elsewhere, "b.jpg")); !os.IsNotExist(err) {
		t.Fatal("wrote through the symlink")
	}
}

func TestPreRestoreFailureChangesNothing(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	f.write("data/onemind/storage/photos/a.jpg", "current")
	f.repo.backupErr = &ResticError{Op: "backup", ExitCode: 1, Stderr: "disk full"}
	_, err := f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: f.path("data/onemind/storage/photos/a.jpg")})
	if err == nil || !strings.Contains(err.Error(), "nothing was changed") || f.read("data/onemind/storage/photos/a.jpg") != "current" {
		t.Fatalf("err = %v", err)
	}
}
