// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
	"testing"
)

func TestNASListingSurvivesUnreadableCandidate(t *testing.T) {
	const childEnv = "ONEMIND_TEST_UNREADABLE_NAS"
	root := os.Getenv(childEnv)
	older, unreadable := strings.Repeat("1", 32), strings.Repeat("2", 32)
	if root == "" {
		var err error
		root, err = os.MkdirTemp("", "om-copy-list-")
		if err != nil {
			t.Fatal(err)
		}
		defer os.RemoveAll(root)
		for _, id := range []string{older, unreadable} {
			if err := os.Mkdir(filepath.Join(root, id), 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(root, id, "complete.json"), []byte("completion"), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		if err := os.Chmod(filepath.Join(root, unreadable), 0o000); err != nil {
			t.Fatal(err)
		}
		defer os.Chmod(filepath.Join(root, unreadable), 0o700)
		if os.Geteuid() == 0 {
			if err := os.Chmod(root, 0o755); err != nil {
				t.Fatal(err)
			}
			// Root bypasses directory permissions. Give only this test's child
			// a copy of the binary it can execute as the unprivileged UID.
			binary, err := os.Executable()
			if err != nil {
				t.Fatal(err)
			}
			contents, err := os.ReadFile(binary)
			if err != nil {
				t.Fatal(err)
			}
			executable := filepath.Join(root, "test")
			if err := os.WriteFile(executable, contents, 0o755); err != nil {
				t.Fatal(err)
			}
			cmd := exec.Command(executable, "-test.run=^TestNASListingSurvivesUnreadableCandidate$")
			cmd.Env = append(os.Environ(), childEnv+"="+root)
			cmd.SysProcAttr = &syscall.SysProcAttr{Credential: &syscall.Credential{Uid: 65534, Gid: 65534}}
			if out, err := cmd.CombinedOutput(); err != nil {
				t.Fatalf("unprivileged listing: %v\n%s", err, out)
			}
			return
		}
	}
	dir, err := os.OpenRoot(root)
	if err != nil {
		t.Fatal(err)
	}
	defer dir.Close()
	store := nasCopyStore{dir}
	ctx := context.Background()
	ids, err := store.records(ctx)
	if err != nil || !slices.Equal(ids, []string{older, unreadable}) {
		t.Fatalf("a bad candidate hid the older copy: listing %v, error %v", ids, err)
	}
	if _, err := store.get(ctx, unreadable+"/complete.json", 64); !errors.Is(err, os.ErrPermission) {
		t.Fatalf("expected the unreadable record to fail on read: %v", err)
	}
	if got, err := store.get(ctx, older+"/complete.json", 64); err != nil || string(got) != "completion" {
		t.Fatalf("the older record is unavailable: %v", err)
	}
	store.close()
	if _, err := store.records(ctx); err == nil {
		t.Fatal("the destination-wide listing failure was swallowed")
	}
}
