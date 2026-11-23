// SPDX-License-Identifier: Apache-2.0

package netmount

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const secret = "hunter2-Sealed!"

func smbSpec() Spec {
	return Spec{Protocol: SMB, Host: "nas.example", Share: "family", User: "alex", Password: secret}
}

// fakeHost plays mount and umount: a mount hides the marker (as a real mount
// covers the folder), an umount shows it again. It records every argv and
// what the credentials file looked like while mount ran.
type fakeHost struct {
	t        *testing.T
	argv     [][]string
	credMode os.FileMode
	credBody string
	fail     string // mount output for a failing mount
	mounted  map[string]bool
}

func (f *fakeHost) Exec(_ context.Context, name string, args ...string) ([]byte, int, error) {
	f.argv = append(f.argv, append([]string{name}, args...))
	switch name {
	case "mount":
		if f.fail != "" {
			return []byte(f.fail), 32, nil
		}
		dir := args[3]
		for _, o := range strings.Split(args[5], ",") {
			if p, ok := strings.CutPrefix(o, "credentials="); ok {
				fi, err := os.Stat(p)
				if err != nil {
					f.t.Fatalf("credentials file missing while mount runs: %v", err)
				}
				b, _ := os.ReadFile(p)
				f.credMode, f.credBody = fi.Mode().Perm(), string(b)
			}
		}
		if err := os.Rename(filepath.Join(dir, Marker), filepath.Join(dir, "..", "hidden-marker")); err != nil {
			f.t.Fatalf("hide marker: %v", err)
		}
		f.mounted[dir] = true
	case "umount":
		dir := args[len(args)-1]
		if f.mounted[dir] {
			_ = os.Rename(filepath.Join(dir, "..", "hidden-marker"), filepath.Join(dir, Marker))
			delete(f.mounted, dir)
		}
	}
	return nil, 0, nil
}

func newManager(t *testing.T) (*Manager, *fakeHost, *bytes.Buffer) {
	t.Helper()
	root := t.TempDir()
	f := &fakeHost{t: t, mounted: map[string]bool{}}
	logs := &bytes.Buffer{}
	m := &Manager{
		Base: filepath.Join(root, "net"), CredDir: filepath.Join(root, "cred"), UID: 900, GID: 900, Run: f,
		Log:       slog.New(slog.NewTextHandler(logs, &slog.HandlerOptions{Level: slog.LevelDebug})),
		IsTmpfs:   func(string) (bool, error) { return true, nil },
		IsMounted: func(d string) (bool, error) { return f.mounted[d], nil },
		Probe:     func(context.Context, string) error { return nil },
		LookPath:  func(s string) (string, error) { return "/usr/sbin/" + s, nil },
	}
	return m, f, logs
}

func reason(err error) string {
	var r *Refusal
	if errors.As(err, &r) {
		return r.Reason
	}
	return ""
}

func TestValidateRefusesGuestSystemPathsAndInjection(t *testing.T) {
	smb := func(mut func(*Spec)) Spec { s := smbSpec(); mut(&s); return s }
	nfs := func(share string) Spec { return Spec{Protocol: NFS, Host: "192.0.2.10", Share: share} }
	for name, tc := range map[string]struct {
		s    Spec
		want string
	}{
		"no user":          {smb(func(s *Spec) { s.User = "" }), "guest_refused"},
		"no password":      {smb(func(s *Spec) { s.Password = "" }), "guest_refused"},
		"guest":            {smb(func(s *Spec) { s.User = "Guest" }), "guest_refused"},
		"domain guest":     {smb(func(s *Spec) { s.User = `WORK\anonymous` }), "guest_refused"},
		"admin share":      {smb(func(s *Spec) { s.Share = "C$" }), "system_share"},
		"ipc share":        {smb(func(s *Spec) { s.Share = "IPC$/x" }), "system_share"},
		"option in share":  {smb(func(s *Spec) { s.Share = "a,vers=1.0" }), "invalid_share"},
		"dotdot share":     {smb(func(s *Spec) { s.Share = "a/../b" }), "invalid_share"},
		"option in host":   {smb(func(s *Spec) { s.Host = "nas,vers=1.0" }), "invalid_host"},
		"loopback":         {smb(func(s *Spec) { s.Host = "127.0.0.1" }), "invalid_host"},
		"ipv6":             {smb(func(s *Spec) { s.Host = "fd00::5" }), "ipv6_literal"},
		"newline password": {smb(func(s *Spec) { s.Password = "a\nusername=root" }), "invalid_password"},
		"bad access":       {smb(func(s *Spec) { s.Access = "rwx" }), "invalid_access"},
		"protocol":         {smb(func(s *Spec) { s.Protocol = "afp" }), "invalid_protocol"},
		"nfs root":         {nfs("/"), "system_share"},
		"nfs etc":          {nfs("/etc/ssl"), "system_share"},
		"nfs proc":         {nfs("/proc"), "system_share"},
		"nfs relative":     {nfs("volume1"), "system_share"},
		"nfs password":     {Spec{Protocol: NFS, Host: "nas", Share: "/volume1/x", Password: "p"}, "nfs_no_credentials"},
	} {
		if got := reason(tc.s.Validate()); got != tc.want {
			t.Errorf("%s: got %q, want %q", name, got, tc.want)
		}
	}
	for _, ok := range []Spec{smbSpec(), {Protocol: NFS, Host: "nas.lan", Share: "/volume1/photos", Access: "rw"}} {
		if err := ok.Validate(); err != nil {
			t.Errorf("%v refused: %v", ok, err)
		}
	}
}

func TestSpecNeverPrintsItsFields(t *testing.T) {
	s := smbSpec()
	var logs bytes.Buffer
	slog.New(slog.NewTextHandler(&logs, nil)).Info("x", "spec", s)
	for _, out := range []string{s.String(), s.GoString(), logs.String()} {
		for _, v := range []string{secret, "nas.example", "family", "alex"} {
			if strings.Contains(out, v) {
				t.Errorf("%q shows %q", out, v)
			}
		}
	}
}

func TestArgsForceSMB3OrNFS4AndCarryNoPassword(t *testing.T) {
	m, _, _ := newManager(t)
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

func TestMountTestsReadOnlyThenMountsAndDeletesCredentials(t *testing.T) {
	m, f, logs := newManager(t)
	s := smbSpec()
	s.Access = "rw"
	st, err := m.Mount(context.Background(), "nas1", s)
	if err != nil || st.State != StateMounted || st.Access != "rw" {
		t.Fatalf("mount: %+v %v", st, err)
	}
	var mounts []string
	for _, a := range f.argv {
		joined := strings.Join(a, " ")
		if strings.Contains(joined, secret) {
			t.Errorf("password in argv: %q", joined)
		}
		if a[0] == "mount" {
			mounts = append(mounts, a[6][:2])
		}
	}
	if strings.Join(mounts, ",") != "ro,rw" {
		t.Errorf("want a read-only test mount then the rw mount, got %v", mounts)
	}
	if f.credMode != 0o600 || !strings.Contains(f.credBody, "password="+secret+"\n") || !strings.Contains(f.credBody, "username=alex\n") {
		t.Errorf("credentials file: mode %o", f.credMode)
	}
	if left, _ := os.ReadDir(m.CredDir); len(left) != 0 {
		t.Errorf("credentials file left behind: %v", left)
	}
	for _, v := range []string{secret, "nas.example", "family"} {
		if strings.Contains(logs.String(), v) {
			t.Errorf("log shows %q: %s", v, logs)
		}
	}
	// Mounting a healthy mount again changes nothing.
	n := len(f.argv)
	if _, err := m.Mount(context.Background(), "nas1", s); err != nil || len(f.argv) != n {
		t.Errorf("remount of a healthy mount ran %v (%v)", f.argv[n:], err)
	}
}

func TestMountRefusesAWrittenMountPointAndCredsOffTmpfs(t *testing.T) {
	m, f, _ := newManager(t)
	dir := filepath.Join(m.Base, "nas1")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "photo.jpg"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := m.Mount(context.Background(), "nas1", smbSpec()); reason(err) != "mountpoint_not_empty" {
		t.Errorf("written mount point: %v", err)
	}
	m.IsTmpfs = func(string) (bool, error) { return false, nil }
	if _, err := m.Mount(context.Background(), "nas2", smbSpec()); reason(err) != "creds_not_tmpfs" {
		t.Errorf("credentials off tmpfs: %v", err)
	}
	if len(f.argv) != 0 {
		t.Errorf("mount ran: %v", f.argv)
	}
	m.LookPath = func(string) (string, error) { return "", errors.New("no") }
	if _, err := m.Mount(context.Background(), "nas3", smbSpec()); reason(err) != "client_missing" {
		t.Errorf("no cifs-utils: %v", err)
	}
	for _, base := range []string{"", "relative", "/", "/etc", "/data"} {
		if err := (&Manager{Base: base}).Configured(); err == nil {
			t.Errorf("base %q accepted", base)
		}
	}
}

func TestFailedMountIsClassifiedAndRedacted(t *testing.T) {
	for out, want := range map[string]string{
		"mount error(13): Permission denied password=" + secret: "auth_failed",
		"mount error(2): No such file or directory":             "share_not_found",
		"mount error(95): Operation not supported":              "protocol_refused",
		"mount error(112): Host is down":                        "unreachable",
		"mount error(111): could not connect to 192.0.2.10":       "unreachable",
		"mount.nfs: access denied by server":                    "auth_failed",
		"something else":                                        "mount_failed",
	} {
		m, f, logs := newManager(t)
		f.fail = out
		_, err := m.Mount(context.Background(), "nas1", smbSpec())
		if reason(err) != want {
			t.Errorf("%q: got %v, want %s", out, err, want)
		}
		if strings.Contains(err.Error(), secret) || strings.Contains(logs.String(), secret) {
			t.Errorf("password leaked: %v / %s", err, logs)
		}
		if left, _ := os.ReadDir(m.CredDir); len(left) != 0 {
			t.Errorf("credentials file left after a failure: %v", left)
		}
	}
}

func TestDownNasIsFailingAndRecovers(t *testing.T) {
	m, f, _ := newManager(t)
	if st, _ := m.Check(context.Background(), "nas1"); st.State != StateUnmounted {
		t.Errorf("never mounted: %+v", st)
	}
	if _, err := m.Mount(context.Background(), "nas1", smbSpec()); err != nil {
		t.Fatal(err)
	}
	down := true
	m.Probe = func(context.Context, string) error {
		if down {
			return errors.New("EHOSTDOWN")
		}
		return nil
	}
	st, _ := m.Check(context.Background(), "nas1")
	if st.State != StateFailing || st.Reason != "unreachable" {
		t.Fatalf("down NAS: %+v", st)
	}
	down = false
	if st, _ = m.Check(context.Background(), "nas1"); st.State != StateMounted {
		t.Fatalf("back: %+v", st)
	}
	// The mount vanished (the marker shows): failing, and Mount makes it again.
	delete(f.mounted, filepath.Join(m.Base, "nas1"))
	_ = os.Rename(filepath.Join(m.Base, "hidden-marker"), filepath.Join(m.Base, "nas1", Marker))
	if st, _ = m.Check(context.Background(), "nas1"); st.State != StateFailing || st.Reason != "not_mounted" {
		t.Fatalf("gone: %+v", st)
	}
	if st, err := m.Mount(context.Background(), "nas1", smbSpec()); err != nil || st.State != StateMounted {
		t.Fatalf("recover: %+v %v", st, err)
	}
	if err := m.Unmount(context.Background(), "nas1"); err != nil || len(m.List()) != 0 {
		t.Errorf("unmount: %v %v", err, m.List())
	}
	if _, err := os.Stat(filepath.Join(m.Base, "nas1", Marker)); err != nil {
		t.Errorf("marker missing after unmount: %v", err)
	}
}

func TestMountedInReadsMountinfo(t *testing.T) {
	info := "36 35 98:0 / /data rw - btrfs /dev/x rw\n40 36 0:50 / /data/onemind/net/my\\040nas rw - cifs //n/s rw\n"
	for dir, want := range map[string]bool{"/data/onemind/net/my nas": true, "/data/onemind/net/my": false, "/data/": true} {
		if got, _ := MountedIn(strings.NewReader(info), dir); got != want {
			t.Errorf("%q: %v", dir, got)
		}
	}
}

func TestRoutesRefuseWithoutEchoingTheBody(t *testing.T) {
	m, _, _ := newManager(t)
	mux := http.NewServeMux()
	m.Routes(mux)
	do := func(method, path, body string) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, httptest.NewRequest(method, path, strings.NewReader(body)))
		return rec
	}
	if r := do("PUT", "/v1/netmounts/nas1", `{"protocol":"smb","host":"nas","share":"s","user":"guest","password":"`+secret+`"}`); r.Code != 409 ||
		!strings.Contains(r.Body.String(), "guest_refused") || strings.Contains(r.Body.String(), secret) {
		t.Errorf("guest: %d %s", r.Code, r.Body)
	}
	if r := do("PUT", "/v1/netmounts/nas1", `{"protocol":"smb","password":"`+secret+`","vers":"1.0"}`); r.Code != 400 || strings.Contains(r.Body.String(), secret) {
		t.Errorf("unknown field: %d %s", r.Code, r.Body)
	}
	if r := do("PUT", "/v1/netmounts/nas1", `{"protocol":"nfs","host":"nas","share":"/volume1/x"}`); r.Code != 200 || !strings.Contains(r.Body.String(), `"state":"mounted"`) {
		t.Errorf("nfs: %d %s", r.Code, r.Body)
	}
	if r := do("GET", "/v1/netmounts", ""); r.Code != 200 || !strings.Contains(r.Body.String(), `"available":true`) || !strings.Contains(r.Body.String(), `"id":"nas1"`) {
		t.Errorf("list: %d %s", r.Code, r.Body)
	}
	if r := do("GET", "/v1/netmounts/NAS!", ""); r.Code != 409 || !strings.Contains(r.Body.String(), "invalid_id") {
		t.Errorf("bad id: %d %s", r.Code, r.Body)
	}
	if r := do("DELETE", "/v1/netmounts/nas1", ""); r.Code != 200 {
		t.Errorf("delete: %d %s", r.Code, r.Body)
	}
}
