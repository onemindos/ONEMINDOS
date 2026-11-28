// SPDX-License-Identifier: Apache-2.0

//go:build linux

package cli

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

// limitFileSize sets this process's soft RLIMIT_FSIZE to 0, so any write that grows a regular file fails with EFBIG
// (the Go runtime ignores SIGXFSZ). It is the honest stand-in for a full USB stick: the file opens, the write fails.
// The hard limit is untouched so the cleanup can put the soft limit back. Callers must not run in parallel.
func limitFileSize(t *testing.T) {
	t.Helper()
	var old syscall.Rlimit
	if err := syscall.Getrlimit(syscall.RLIMIT_FSIZE, &old); err != nil {
		t.Fatalf("getrlimit: %v", err)
	}
	lim := old
	lim.Cur = 0
	if err := syscall.Setrlimit(syscall.RLIMIT_FSIZE, &lim); err != nil {
		t.Fatalf("setrlimit: %v", err)
	}
	t.Cleanup(func() {
		if err := syscall.Setrlimit(syscall.RLIMIT_FSIZE, &old); err != nil {
			t.Errorf("restore RLIMIT_FSIZE: %v", err)
		}
	})
}

// Review of #1318, MUST FIX 1: once the gateway has issued the kit, the disk key exists only in this answer. A failed
// write to --out must show the page instead of dropping it, remove the partial file and still exit non-zero.
func TestRecoveryKitIssueShowsThePageWhenTheFileCannotBeWritten(t *testing.T) {
	issues := kitHub(t, 201)
	path := filepath.Join(t.TempDir(), "kit.txt")
	limitFileSize(t)
	r := run(t, "", false, "recovery", "kit", "issue", "--out", path)
	if r.code != ExitError {
		t.Fatalf("a failed write must fail the command: %+v", r)
	}
	if !strings.Contains(r.out, testKitKey) || !strings.Contains(r.out, testDiskKey) {
		t.Fatalf("the issued page (owner key and disk key) must reach the terminal when the file fails: %+v", r)
	}
	if !strings.Contains(r.errOut, path) || !strings.Contains(r.errOut, "only copy") || !strings.Contains(r.errOut, "disk recovery key") {
		t.Errorf("stderr must name the file and say the printed page is the only copy: %q", r.errOut)
	}
	if strings.Contains(r.errOut, "issue another kit") {
		t.Errorf("stderr must not send the owner to issue another kit (the disk key is not given out again): %q", r.errOut)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Errorf("the partial kit file was left behind: %v", err)
	}
	if *issues != 1 {
		t.Errorf("issues = %d, want 1", *issues)
	}
}

func TestRecoveryKitIssueJSONShowsTheKeysWhenTheFileCannotBeWritten(t *testing.T) {
	kitHub(t, 201)
	path := filepath.Join(t.TempDir(), "kit.txt")
	limitFileSize(t)
	r := run(t, "", false, "--json", "recovery", "kit", "issue", "--out", path)
	if r.code != ExitError {
		t.Fatalf("a failed write must fail the command: %+v", r)
	}
	var got kitIssued
	if err := json.Unmarshal([]byte(r.out), &got); err != nil {
		t.Fatalf("stdout is not the kit answer as JSON: %v %q", err, r.out)
	}
	if got.OneTime.OwnerKey != testKitKey || got.OneTime.DiskKey == nil || *got.OneTime.DiskKey != testDiskKey ||
		!strings.Contains(got.OneTime.Text, testDiskKey) {
		t.Errorf("the JSON answer must carry the keys when the file failed: %+v", got)
	}
	var e map[string]any
	if err := json.Unmarshal([]byte(r.errOut), &e); err != nil || e["error"] != "write_failed" {
		t.Errorf("stderr %q: want the write_failed JSON error (%v)", r.errOut, err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Errorf("the partial kit file was left behind: %v", err)
	}
}
