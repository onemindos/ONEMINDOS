// SPDX-License-Identifier: Apache-2.0

package netmount

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

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
	// A test mount that cannot be released is never stacked under the rw mount.
	m2, f2, _ := newManager(t)
	stuck := true
	m2.IsMounted = func(d string) (bool, error) { return f2.mounted[d] || (stuck && len(f2.argv) > 1), nil }
	if _, err := m2.Mount(context.Background(), "nas2", s); reason(err) != "busy" {
		t.Errorf("stuck test mount: %v", err)
	}
	for _, a := range f2.argv {
		if a[0] == "mount" && strings.HasPrefix(a[6], "rw") {
			t.Errorf("rw mount stacked on a stuck test mount: %v", a)
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
		"mount error(111): could not connect to 192.0.2.10":     "unreachable",
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

// A PUT that changes what is mounted (share, user or access) detaches the
// mount in place and mounts the new spec; one that repeats it changes nothing.
func TestMountConvergesOnTheApprovedSpec(t *testing.T) {
	m, f, _ := newManager(t)
	ctx := context.Background()
	rw := smbSpec()
	rw.Access = "rw"
	if _, err := m.Mount(ctx, "nas1", rw); err != nil {
		t.Fatal(err)
	}
	lastMount := func() string {
		for i := len(f.argv) - 1; i >= 0; i-- {
			if f.argv[i][0] == "mount" {
				return strings.Join(f.argv[i], " ")
			}
		}
		return ""
	}
	// Narrowed to ro on another share: the rw mount of family goes, other is mounted ro.
	ro := smbSpec()
	ro.Share, ro.Access = "other", "ro"
	n := len(f.argv)
	st, err := m.Mount(ctx, "nas1", ro)
	if err != nil || st.State != StateMounted || st.Access != "ro" {
		t.Fatalf("narrow: %+v %v", st, err)
	}
	ran := f.argv[n:]
	if len(ran) == 0 || ran[0][0] != "umount" || ran[0][1] == "-l" {
		t.Fatalf("the rw mount was not detached first: %v", ran)
	}
	if got := lastMount(); !strings.Contains(got, "//nas.example/other ") || !strings.Contains(got, " -o ro,") {
		t.Fatalf("the new spec was not mounted ro: %q", got)
	}
	for _, a := range ran {
		if a[0] == "mount" && strings.HasPrefix(a[6], "rw") {
			t.Errorf("a rw mount after narrowing to ro: %v", a)
		}
	}
	// The same share with the access narrowed (rw -> ro) remounts too.
	if _, err := m.Mount(ctx, "nas1", rw); err != nil {
		t.Fatal(err)
	}
	n = len(f.argv)
	if _, err := m.Mount(ctx, "nas1", smbSpec()); err != nil || len(f.argv) == n || !strings.Contains(lastMount(), " -o ro,") {
		t.Fatalf("rw -> ro on the same share: ran %v (%v)", f.argv[n:], err)
	}
	// Another user for the same share remounts; a new password alone does not.
	n = len(f.argv)
	other := smbSpec()
	other.User = "sam"
	if _, err := m.Mount(ctx, "nas1", other); err != nil || len(f.argv) == n {
		t.Fatalf("new user: ran %v (%v)", f.argv[n:], err)
	}
	n = len(f.argv)
	other.Password = "a-new-" + secret
	if _, err := m.Mount(ctx, "nas1", other); err != nil || len(f.argv) != n {
		t.Fatalf("new password alone ran %v (%v)", f.argv[n:], err)
	}
	// A mount this service did not make (it restarted) is made again.
	m2, _, _ := newManager(t)
	m2.Base, m2.Run = m.Base, f
	m2.IsMounted = m.IsMounted
	n = len(f.argv)
	if _, err := m2.Mount(ctx, "nas1", other); err != nil || len(f.argv) == n {
		t.Fatalf("unknown mount in place: ran %v (%v)", f.argv[n:], err)
	}
}

// A mount in place that cannot be released is never covered by the new one,
// and the list says the mount is failing.
func TestMountNeverStacksOnAMountItCannotRelease(t *testing.T) {
	m, f, _ := newManager(t)
	ctx := context.Background()
	rw := smbSpec()
	rw.Access = "rw"
	if _, err := m.Mount(ctx, "nas1", rw); err != nil {
		t.Fatal(err)
	}
	dir := filepath.Join(m.Base, "nas1")
	m.IsMounted = func(d string) (bool, error) { return d == dir, nil } // umount never takes it off
	n := len(f.argv)
	ro := smbSpec()
	if _, err := m.Mount(ctx, "nas1", ro); reason(err) != "busy" {
		t.Fatalf("stuck mount in place: %v", err)
	}
	for _, a := range f.argv[n:] {
		if a[0] == "mount" {
			t.Errorf("mounted over a mount that could not be released: %v", a)
		}
	}
	if l := m.List(); len(l) != 1 || l[0].State != StateFailing || l[0].Reason != "busy" {
		t.Errorf("list after a busy remount: %+v", l)
	}
}

// Reading an id that was never mounted records nothing.
func TestCheckOfAnUnknownIDRecordsNothing(t *testing.T) {
	m, _, _ := newManager(t)
	for i := 0; i < 3; i++ {
		st, err := m.Check(context.Background(), "stray")
		if err != nil || st.State != StateUnmounted || st.Reason != "" {
			t.Fatalf("read %d of a never-mounted id: %+v %v", i, st, err)
		}
	}
	if l := m.List(); len(l) != 0 {
		t.Fatalf("a stray read is in the list: %+v", l)
	}
	// A Check that races an Unmount never brings the mount back.
	if _, err := m.Mount(context.Background(), "nas1", smbSpec()); err != nil {
		t.Fatal(err)
	}
	m.Probe = func(context.Context, string) error {
		_ = m.Unmount(context.Background(), "nas1")
		return errors.New("EHOSTDOWN")
	}
	if _, err := m.Check(context.Background(), "nas1"); err != nil {
		t.Fatal(err)
	}
	if l := m.List(); len(l) != 0 {
		t.Fatalf("a Check after Unmount put the mount back: %+v", l)
	}
}
