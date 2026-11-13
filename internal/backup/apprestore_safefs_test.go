// SPDX-License-Identifier: Apache-2.0

//go:build unix

package backup

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// An app restore runs as root while the app may still own its volume folders
// (and can turn any of them into a symlink). These tests plant a symlink
// before the restore and swap one in while it runs: the restore must refuse
// and must never write, rename or delete anything outside the volume.

const (
	vol1 = "storage/pvc-1111_app-notes_data"
	dump = "storage/pvc-2222_onemind-db_data-postgres-0/onemind-dumps/app_notes.pgdump"
)

// appRestoreSetup takes a snapshot of the notes app, then returns a func that
// runs an app restore of it and reports the job result.
func appRestoreSetup(t *testing.T) (m *managedFixture, restore func() JobResult, elsewhere string) {
	t.Helper()
	m = newManagedFixture(t)
	m.ok(t, KindConfigure, usbTarget())
	snap := appRun(t, m, ReasonManual).Units[0].SnapshotID
	elsewhere = m.path("elsewhere")
	if err := os.MkdirAll(elsewhere, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(elsewhere, "precious"), []byte("precious"), 0o644); err != nil {
		t.Fatal(err)
	}
	restore = func() JobResult {
		_, res, _ := m.do(t, KindRestore, map[string]any{"scope": "app", "app_id": "notes", "snapshot_id": snap, "stamp": "20261113T120000Z"})
		return res
	}
	return m, restore, elsewhere
}

// onlyPrecious fails if anything but the original file is in dir.
func onlyPrecious(t *testing.T, dir string) {
	t.Helper()
	ents, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(ents) != 1 || ents[0].Name() != "precious" {
		var names []string
		for _, e := range ents {
			names = append(names, e.Name())
		}
		t.Fatalf("the restore wrote outside the volume: %v", names)
	}
	if b, _ := os.ReadFile(filepath.Join(dir, "precious")); string(b) != "precious" {
		t.Fatalf("outside file overwritten: %q", b)
	}
}

func once(f func()) func() {
	done := false
	return func() {
		if !done {
			done = true
			f()
		}
	}
}

func TestAppRestoreRefusesPlantedSymlinks(t *testing.T) {
	plants := map[string]func(m *managedFixture, elsewhere string){
		"volume folder is a symlink": func(m *managedFixture, elsewhere string) {
			_ = os.RemoveAll(m.path(vol1))
			if err := os.Symlink(elsewhere, m.path(vol1)); err != nil {
				t.Fatal(err)
			}
		},
		"folder above a restored file is a symlink": func(m *managedFixture, elsewhere string) {
			dir := filepath.Dir(m.path(dump))
			_ = os.RemoveAll(dir)
			if err := os.Symlink(elsewhere, dir); err != nil {
				t.Fatal(err)
			}
		},
		"restored file is a symlink": func(m *managedFixture, elsewhere string) {
			_ = os.Remove(m.path(dump))
			if err := os.Symlink(filepath.Join(elsewhere, "precious"), m.path(dump)); err != nil {
				t.Fatal(err)
			}
		},
	}
	for name, plant := range plants {
		t.Run(name, func(t *testing.T) {
			m, restore, elsewhere := appRestoreSetup(t)
			plant(m, elsewhere)
			res := restore()
			if res.State != StateFailed || !strings.Contains(res.Error, "symlink") {
				t.Fatalf("restore through a planted symlink was not refused: %+v", res)
			}
			onlyPrecious(t, elsewhere)
			if _, err := os.Stat(m.path(vol1 + oldSuffix + "20261113T120000Z")); err == nil {
				t.Fatal("a refused restore left a moved-aside folder")
			}
		})
	}
}

// The path is checked, then the app swaps a folder for a symlink before the
// restore uses it: the open handle keeps the work on the real folder.
func TestAppRestoreSwappedForSymlinkMidRestore(t *testing.T) {
	swaps := map[string]func(m *managedFixture) string{
		"volume folder": func(m *managedFixture) string { return m.path(vol1) },
		"storage root":  func(m *managedFixture) string { return m.path("storage") },
		"folder above a restored file": func(m *managedFixture) string {
			return filepath.Dir(m.path(dump))
		},
	}
	for name, target := range swaps {
		t.Run(name, func(t *testing.T) {
			m, restore, elsewhere := appRestoreSetup(t)
			path := target(m)
			ran := false
			hook := once(swapForSymlink(t, path, elsewhere))
			testHookAfterOpen = func() { ran = true; hook() }
			t.Cleanup(func() { testHookAfterOpen = nil })
			_ = restore() // may succeed on the real folder or refuse; either way nothing escapes
			if !ran {
				t.Fatal("the simulated swap never ran")
			}
			onlyPrecious(t, elsewhere)
		})
	}
}

// A restore that fails half way rolls back through the same handles: the
// symlink the app planted meanwhile is not followed by the undo either.
func TestAppRestoreUndoDoesNotFollowSwappedParent(t *testing.T) {
	m, restore, elsewhere := appRestoreSetup(t)
	n := 0
	hook := swapForSymlink(t, filepath.Dir(m.path(dump)), elsewhere)
	testHookAfterOpen = func() {
		n++
		if n == 2 { // the volume swapped in; now the file's folder turns into a symlink
			hook()
		}
	}
	t.Cleanup(func() { testHookAfterOpen = nil })
	_ = restore()
	if n < 2 {
		t.Fatal("the simulated swap never ran")
	}
	onlyPrecious(t, elsewhere)
}
