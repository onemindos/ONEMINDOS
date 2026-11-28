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

func TestNASCopyRejectsLinkedNamespace(t *testing.T) {
	const box = "test-box"
	for _, part := range []string{"mount", "boxes", box, "copies"} {
		t.Run(part, func(t *testing.T) {
			root := t.TempDir()
			target := Target{Kind: KindUSB, MountRoot: root, USBUUID: "mount", AllowNonMountDir: true}
			a := newAgent(Config{}, nil)
			prefix := filepath.Join(root, "mount", "boxes", box, "copies")
			if err := os.MkdirAll(prefix, 0o700); err != nil {
				t.Fatal(err)
			}
			linked := filepath.Join(root, "mount")
			for _, name := range []string{"boxes", box, "copies"} {
				if filepath.Base(linked) == part {
					break
				}
				linked = filepath.Join(linked, name)
			}
			sibling := linked + "-sibling"
			if err := os.Rename(linked, sibling); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink(filepath.Base(sibling), linked); err != nil {
				t.Fatal(err)
			}
			for _, write := range []bool{false, true} {
				if store, err := a.openCopyStore(target, box, write); err == nil {
					store.close()
					t.Errorf("opened linked %s with write=%t", part, write)
				}
			}
		})
	}
}

func TestNASCopyRejectsUnsafeCandidatesAndKeepsOlderCopy(t *testing.T) {
	const box = "test-box"
	root := t.TempDir()
	target := Target{ID: "nas", Kind: KindUSB, MountRoot: root, USBUUID: "mount", AllowNonMountDir: true, Sovereign: true}
	a := newAgent(Config{Targets: []Target{target}}, nil)
	prefix := filepath.Join(root, "mount", "boxes", box, "copies")
	older, linkedDir, linkedRecord, fifo := strings.Repeat("1", 32), strings.Repeat("2", 32), strings.Repeat("3", 32), strings.Repeat("4", 32)
	for _, id := range []string{older, linkedRecord, fifo} {
		if err := os.MkdirAll(filepath.Join(prefix, id), 0o700); err != nil {
			t.Fatal(err)
		}
	}
	for _, name := range []string{older + "/complete.json", older + "/box.omb", fifo + "/complete.json"} {
		if err := os.WriteFile(filepath.Join(prefix, name), []byte("valid bytes"), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Symlink(older, filepath.Join(prefix, linkedDir)); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("../"+older+"/complete.json", filepath.Join(prefix, linkedRecord, "complete.json")); err != nil {
		t.Fatal(err)
	}
	if err := syscall.Mkfifo(filepath.Join(prefix, fifo, "box.omb"), 0o600); err != nil {
		t.Fatal(err)
	}

	ctx := context.Background()
	for _, bad := range []struct{ id, op string }{{linkedDir, "record"}, {linkedRecord, "record"}, {fifo, "bundle"}} {
		if _, err := a.sovereignCopy(ctx, copyJob{Operation: bad.op, TargetID: target.ID, BoxID: box, CopyID: bad.id}); err == nil {
			t.Errorf("read %s from unsafe candidate %s", bad.op, bad.id)
		}
	}
	ids, err := a.sovereignCopy(ctx, copyJob{Operation: "list", TargetID: target.ID, BoxID: box})
	if err != nil || !slices.Equal(ids.([]string), []string{older, fifo}) {
		t.Fatalf("listing %v, error %v", ids, err)
	}
	for _, op := range []string{"record", "bundle"} {
		got, err := a.sovereignCopy(ctx, copyJob{Operation: op, TargetID: target.ID, BoxID: box, CopyID: older})
		if err != nil || string(got.([]byte)) != "valid bytes" {
			t.Fatalf("the older copy's %s is unavailable: %v", op, err)
		}
	}
}

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
	fd, err := openDirNoFollow(root, false)
	if err != nil {
		t.Fatal(err)
	}
	store := nasCopyStore{os.NewFile(uintptr(fd), root)}
	defer store.close()
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
