// SPDX-License-Identifier: Apache-2.0

package netmount

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// scripted plays one program run: it records the argv and answers out/exit.
type scripted struct {
	argv [][]string
	out  string
	exit int
}

func (s *scripted) Exec(_ context.Context, name string, args ...string) ([]byte, int, error) {
	s.argv = append(s.argv, append([]string{name}, args...))
	return []byte(s.out), s.exit, nil
}

func TestArgsForceSMB3OrNFS4AndCarryNoPassword(t *testing.T) {
	m := &Manager{UID: 900, GID: 900}
	smb := strings.Join(m.Args("/m/a", smbSpec(), "/run/c", "ro"), " ")
	for _, want := range []string{"-t cifs //nas.example/family /m/a", "ro,", "vers=3", "sec=ntlmssp", "credentials=/run/c", "nosuid", "nodev", "uid=900"} {
		if !strings.Contains(smb, want) {
			t.Errorf("smb argv %q lacks %q", smb, want)
		}
	}
	nfs := strings.Join(m.Args("/m/b", Spec{Protocol: NFS, Host: "nas", Share: "/volume1/x/"}, "", "rw"), " ")
	if !strings.Contains(nfs, "-t nfs nas:/volume1/x /m/b -o rw,") || !strings.Contains(nfs, "vers=4") || !strings.Contains(nfs, "soft") {
		t.Errorf("nfs argv %q", nfs)
	}
	if strings.Contains(smb, secret) || strings.Contains(smb, "password") {
		t.Errorf("argv carries the password: %q", smb)
	}
}

func TestWriteCredsIsAPrivateFileInMemoryOnly(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "cred")
	m := &Manager{CredDir: dir, IsTmpfs: func(string) (bool, error) { return true, nil }}
	s := smbSpec()
	s.User = `WORK\alex`
	p, err := m.writeCreds(s)
	if err != nil {
		t.Fatal(err)
	}
	fi, err := os.Stat(p)
	if err != nil || fi.Mode().Perm() != 0o600 || filepath.Dir(p) != dir {
		t.Fatalf("credentials file %v: %v", fi, err)
	}
	b, _ := os.ReadFile(p)
	if string(b) != "username=alex\npassword="+secret+"\ndomain=WORK\n" {
		t.Errorf("credentials body has the wrong shape (%d bytes)", len(b))
	}
	if q, _ := m.writeCreds(s); q == p {
		t.Error("two credentials files share a name")
	}
	m.IsTmpfs = func(string) (bool, error) { return false, nil }
	m.CredDir = filepath.Join(t.TempDir(), "disk")
	if _, err := m.writeCreds(s); reason(err) != "creds_not_tmpfs" {
		t.Errorf("credentials off tmpfs: %v", err)
	}
	if left, _ := os.ReadDir(m.CredDir); len(left) != 0 {
		t.Errorf("a credentials file was written to disk: %v", left)
	}
}

func TestPrepareMarksAnEmptyMountPointAndRefusesAWrittenOne(t *testing.T) {
	m := &Manager{Base: filepath.Join(t.TempDir(), "net")}
	dir := filepath.Join(m.Base, "nas1")
	if err := m.prepare(dir); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, Marker)); err != nil {
		t.Fatalf("no marker: %v", err)
	}
	if err := m.prepare(dir); err != nil {
		t.Fatalf("prepare again: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "photo.jpg"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := m.prepare(dir); reason(err) != "mountpoint_not_empty" {
		t.Errorf("written mount point: %v", err)
	}
	file := filepath.Join(m.Base, "nas2")
	if err := os.WriteFile(file, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := m.prepare(file); reason(err) != "mountpoint_not_empty" {
		t.Errorf("mount point is a file: %v", err)
	}
}

func TestConfiguredAndUnavailable(t *testing.T) {
	for _, base := range []string{"", "relative", "/", "/etc", "/data", "/data/", "/home"} {
		if err := (&Manager{Base: base}).Configured(); err == nil {
			t.Errorf("base %q accepted", base)
		}
	}
	have := map[string]bool{"mount.nfs": true}
	m := &Manager{Base: "/data/onemind/net", LookPath: func(s string) (string, error) {
		if have[filepath.Base(s)] {
			return s, nil
		}
		return "", errors.New("not found")
	}}
	if err := m.Configured(); err != nil {
		t.Fatal(err)
	}
	if why := m.Unavailable(SMB); !strings.Contains(why, "cifs-utils") {
		t.Errorf("smb without mount.cifs: %q", why)
	}
	if why := m.Unavailable(NFS); why != "" {
		t.Errorf("nfs with mount.nfs: %q", why)
	}
}

func TestMountOnceClassifiesAndUmountDetaches(t *testing.T) {
	run := &scripted{out: "mount error(13): Permission denied for //nas.example/family", exit: 32}
	m := &Manager{Run: run, UID: -1, GID: -1}
	if err := m.mountOnce(context.Background(), "/m/a", smbSpec(), "/run/c", "ro"); reason(err) != "auth_failed" {
		t.Errorf("refused mount: %v", err)
	}
	run.out, run.exit = "", 0
	if err := m.mountOnce(context.Background(), "/m/a", smbSpec(), "/run/c", "ro"); err != nil {
		t.Errorf("mount: %v", err)
	}
	m.umount(context.Background(), "/m/a", false)
	m.umount(context.Background(), "/m/a", true)
	got := []string{}
	for _, a := range run.argv {
		got = append(got, strings.Join(a, " "))
	}
	if got[2] != "umount /m/a" || got[3] != "umount -l /m/a" {
		t.Errorf("umount argv: %v", got[2:])
	}
}

func TestProbeReadsTheMountPoint(t *testing.T) {
	m := &Manager{}
	if err := m.probe(context.Background(), t.TempDir()); err != nil {
		t.Errorf("readable folder: %v", err)
	}
	if err := m.probe(context.Background(), filepath.Join(t.TempDir(), "gone")); err == nil {
		t.Error("a missing folder read as healthy")
	}
}
