// SPDX-License-Identifier: Apache-2.0

package fabric

import (
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

// A container's /etc/hosts is a bind mount: rename onto it fails with EBUSY, so the file is written in place.
func TestWriteFileFallsBackToInPlaceWhenRenameIsBusy(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "hosts")
	if err := os.WriteFile(path, []byte("old\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	orig := rename
	rename = func(string, string) error { return &os.LinkError{Op: "rename", Err: syscall.EBUSY} }
	defer func() { rename = orig }()
	if err := writeFile(path, []byte("new\n"), 0o644); err != nil {
		t.Fatalf("writeFile: %v", err)
	}
	got, _ := os.ReadFile(path)
	if string(got) != "new\n" {
		t.Fatalf("content %q", got)
	}
	left, _ := filepath.Glob(filepath.Join(dir, ".tmp-*"))
	if len(left) != 0 {
		t.Fatalf("temp files left behind: %v", left)
	}
}

func TestWriteFileOtherRenameErrorsAreReturned(t *testing.T) {
	dir := t.TempDir()
	orig := rename
	rename = func(string, string) error { return syscall.EACCES }
	defer func() { rename = orig }()
	if err := writeFile(filepath.Join(dir, "x"), []byte("y"), 0o644); err == nil {
		t.Fatal("an EACCES rename must not be hidden")
	}
}
