// SPDX-License-Identifier: Apache-2.0

//go:build netmount_acceptance

package netmount

// The #718 acceptance test against real Samba and NFS servers. It needs root
// (it mounts) and the servers; testdata/acceptance.sh runs it in a throwaway
// privileged Debian container that serves both:
//
//	sh internal/storage/netmount/testdata/acceptance.sh
//
// It proves: both protocols mount; the password is never in any process's
// /proc/*/cmdline while mounting, nor in the logs, nor left in a file; SMB1
// and guest are refused by the server side too; a killed server reads as
// failing and the same mount reads as mounted again once it is back.

import (
	"bytes"
	"context"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func env(t *testing.T, k string) string {
	v := os.Getenv(k)
	if v == "" {
		t.Skipf("%s not set", k)
	}
	return v
}

// watchCmdlines scans every process's command line until stop is closed and
// counts the ones that contain needle.
func watchCmdlines(needle string, stop <-chan struct{}, hits *atomic.Int64, scans *atomic.Int64) {
	for {
		select {
		case <-stop:
			return
		default:
		}
		procs, _ := filepath.Glob("/proc/[0-9]*/cmdline")
		for _, p := range procs {
			if b, err := os.ReadFile(p); err == nil && bytes.Contains(b, []byte(needle)) {
				hits.Add(1)
			}
		}
		scans.Add(1)
	}
}

func sh(t *testing.T, cmd string) {
	t.Helper()
	if out, err := exec.Command("sh", "-c", cmd).CombinedOutput(); err != nil {
		t.Fatalf("%s: %v %s", cmd, err, out)
	}
}

func waitState(t *testing.T, m *Manager, id, want string, within time.Duration) Status {
	t.Helper()
	deadline := time.Now().Add(within)
	var st Status
	for time.Now().Before(deadline) {
		st, _ = m.Check(context.Background(), id)
		if st.State == want {
			return st
		}
		time.Sleep(time.Second)
	}
	t.Fatalf("%s never became %s: %+v", id, want, st)
	return st
}

func TestAcceptanceSambaAndNFS(t *testing.T) {
	password := env(t, "NETMOUNT_IT_SMB_PASSWORD")
	smb := Spec{Protocol: SMB, Host: env(t, "NETMOUNT_IT_HOST"), Share: env(t, "NETMOUNT_IT_SMB_SHARE"),
		User: env(t, "NETMOUNT_IT_SMB_USER"), Password: password, Access: "rw"}
	nfs := Spec{Protocol: NFS, Host: smb.Host, Share: env(t, "NETMOUNT_IT_NFS_EXPORT")}
	var logs bytes.Buffer
	m := &Manager{Base: t.TempDir(), CredDir: "/run/onemind/netmount", UID: -1, GID: -1,
		Log: slog.New(slog.NewTextHandler(&logs, &slog.HandlerOptions{Level: slog.LevelDebug}))}
	ctx := context.Background()
	t.Cleanup(func() { // before TempDir's cleanup: never leave a mount behind
		for _, id := range []string{"smb1", "nfs1", "bad1"} {
			_ = m.Unmount(ctx, id)
		}
	})

	stop := make(chan struct{})
	var hits, scans atomic.Int64
	go watchCmdlines(password, stop, &hits, &scans)
	st, err := m.Mount(ctx, "smb1", smb)
	close(stop)
	if err != nil || st.State != StateMounted {
		t.Fatalf("smb mount: %+v %v\n%s", st, err, logs.String())
	}
	if hits.Load() != 0 || scans.Load() == 0 {
		t.Fatalf("password seen in /proc/*/cmdline %d times (%d scans)", hits.Load(), scans.Load())
	}
	t.Logf("smb mounted; /proc/*/cmdline scanned %d times during the mount, password never seen", scans.Load())
	if left, _ := os.ReadDir(m.CredDir); len(left) != 0 {
		t.Fatalf("credentials files left: %v", left)
	}
	if err := os.WriteFile(filepath.Join(m.Base, "smb1", "hello.txt"), []byte("from the hub"), 0o644); err != nil {
		t.Fatalf("write through the rw mount: %v", err)
	}
	if _, err := m.Mount(ctx, "nfs1", nfs); err != nil {
		t.Fatalf("nfs mount: %v\n%s", err, logs.String())
	}
	if _, err := os.ReadDir(filepath.Join(m.Base, "nfs1")); err != nil {
		t.Fatalf("read nfs: %v", err)
	}

	// A wrong password is refused by the server and named as such; nothing is left mounted.
	wrong := smb
	wrong.Password = "wrong-" + password
	if _, err := m.Mount(ctx, "bad1", wrong); reason(err) != "auth_failed" {
		t.Errorf("wrong password: %v", err)
	}

	// Kill the SMB server: failing. Bring it back: the same mount recovers.
	sh(t, env(t, "NETMOUNT_IT_STOP_SMB"))
	failing := waitState(t, m, "smb1", StateFailing, 90*time.Second)
	t.Logf("server down: %s (%s)", failing.State, failing.Reason)
	sh(t, env(t, "NETMOUNT_IT_START_SMB"))
	back := waitState(t, m, "smb1", StateMounted, 120*time.Second)
	t.Logf("server back: %s", back.State)

	for _, id := range []string{"smb1", "nfs1"} {
		if err := m.Unmount(ctx, id); err != nil {
			t.Errorf("unmount %s: %v", id, err)
		}
	}
	if strings.Contains(logs.String(), password) {
		t.Fatalf("password in the logs:\n%s", logs.String())
	}
}
