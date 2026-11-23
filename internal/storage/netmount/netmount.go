// SPDX-License-Identifier: Apache-2.0

// Package netmount mounts a NAS share (SMB3 or NFSv4) on the hub so Files can
// show it as a `net:<id>` location (issue #718, nas-mount-engine).
//
// The gateway decides; this package only does what an owner approved. It gets
// the whole mount (host, share, user, password) in one call over the storage
// socket, and keeps none of it: the password goes into a 0600 credentials
// file on tmpfs that mount.cifs reads and that is deleted before the call
// returns, so it is never in argv (ps, /proc/*/cmdline), in a log line or in
// an error. Rules it keeps whatever the caller sends:
//
//   - SMB is always vers=3 (SMB 3.0 or later; SMB1 is never offered), with a
//     user and password: guest and anonymous access are refused.
//   - NFS is always vers=4 (no v2/v3 fallback).
//   - Admin and hidden shares (C$, ADMIN$) and NAS system exports (/, /etc,
//     /proc ...) are refused; the mount point is always <Base>/<id>.
//   - Every mount is first made read-only and read, then made with the access
//     asked for.
//   - A mount point holds a marker file while nothing is mounted on it. A
//     mount point with anything else in it is refused (data written there
//     while the NAS was away would hide under the mount), and the gateway
//     refuses to touch a `net:` root whose marker it can see.
//   - Check reads the mount with a timeout: a NAS that went away is `failing`,
//     and the same mount reads as `mounted` again when it is back. Mounts are
//     `soft`, so a dead server answers with an error instead of hanging.
package netmount

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Protocols.
const (
	SMB = "smb"
	NFS = "nfs"
)

// States a mount reports.
const (
	StateMounted   = "mounted"
	StateFailing   = "failing"
	StateUnmounted = "unmounted"
)

// Marker is the file a mount point holds while nothing is mounted on it.
const Marker = ".onemind-not-mounted"

// Defaults for the storage service (cmd/onemindd).
const (
	DefaultCredDir = "/run/onemind/netmount"
	ProbeTimeout   = 5 * time.Second
)

// Spec is one mount as the gateway sends it. Host, Share, User and Password
// come from the owner's sealed input; they are never logged.
type Spec struct {
	Protocol string `json:"protocol"`
	Host     string `json:"host"`
	Share    string `json:"share"`
	User     string `json:"user,omitempty"`
	Password string `json:"password,omitempty"`
	Access   string `json:"access,omitempty"` // ro (default) | rw
}

// String never shows the host, share, user or password.
func (s Spec) String() string { return "netmount.Spec{" + s.Protocol + " " + s.access() + "}" }

// GoString keeps %#v from printing the fields.
func (s Spec) GoString() string { return s.String() }

// LogValue keeps slog from printing the fields.
func (s Spec) LogValue() slog.Value {
	return slog.GroupValue(slog.String("protocol", s.Protocol), slog.String("access", s.access()))
}

func (s Spec) access() string {
	if s.Access == "" {
		return "ro"
	}
	return s.Access
}

// Refusal is a request this package will not carry out: a stable reason for
// code and a sentence for the owner. It never quotes the request.
type Refusal struct{ Reason, Message string }

func (r *Refusal) Error() string { return r.Reason + ": " + r.Message }

func refuse(reason, msg string) error { return &Refusal{Reason: reason, Message: msg} }

// Status is what GET and PUT answer for one mount.
type Status struct {
	ID       string    `json:"id"`
	State    string    `json:"state"`
	Protocol string    `json:"protocol,omitempty"`
	Access   string    `json:"access,omitempty"`
	Reason   string    `json:"reason,omitempty"`
	Message  string    `json:"message,omitempty"`
	Since    time.Time `json:"since"`
}

var (
	idRE    = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,39}$`)
	labelRE = regexp.MustCompile(`^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$`)
	userRE  = regexp.MustCompile(`^([A-Za-z0-9][A-Za-z0-9._-]{0,63}\\)?[A-Za-z0-9._@-]{1,64}$`)
	// An SMB share name and optional folder: no separators, wildcards or option syntax.
	smbPartRE = regexp.MustCompile(`^[^\\/:*?"<>|,=\x00-\x1f\x7f]{1,80}$`)
	nfsPartRE = regexp.MustCompile(`^[A-Za-z0-9._@+ -]{1,255}$`)
	guests    = map[string]bool{"guest": true, "anonymous": true, "nobody": true}
	// NAS system exports (exact, or anything below): never a Files location.
	systemExports = []string{"/etc", "/proc", "/sys", "/dev", "/boot", "/root", "/run", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/var/lib", "/var/run"}
	// Hub folders a mount base may never be.
	systemBases = []string{"/", "/etc", "/proc", "/sys", "/dev", "/boot", "/root", "/run", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/var", "/tmp", "/home", "/data"}
)

// ValidID reports whether id can name a mount (and its folder).
func ValidID(id string) bool { return idRE.MatchString(id) }

func validHost(h string) error {
	if ip := net.ParseIP(h); ip != nil {
		if ip.To4() == nil {
			return refuse("ipv6_literal", "Use the NAS's name instead of an IPv6 address.")
		}
		if ip.IsUnspecified() || ip.IsMulticast() || ip.IsLoopback() {
			return refuse("invalid_host", "That address cannot be a NAS.")
		}
		return nil
	}
	if len(h) > 253 || h == "" {
		return refuse("invalid_host", "The NAS name is not a valid host name.")
	}
	for _, l := range strings.Split(h, ".") {
		if !labelRE.MatchString(l) {
			return refuse("invalid_host", "The NAS name is not a valid host name.")
		}
	}
	if strings.EqualFold(h, "localhost") {
		return refuse("invalid_host", "That address cannot be a NAS.")
	}
	return nil
}

// Validate checks a spec without touching anything.
func (s Spec) Validate() error {
	if err := validHost(s.Host); err != nil {
		return err
	}
	if a := s.access(); a != "ro" && a != "rw" {
		return refuse("invalid_access", "Access must be ro or rw.")
	}
	switch s.Protocol {
	case SMB:
		parts := strings.Split(strings.Trim(s.Share, "/"), "/")
		for _, p := range parts {
			if !smbPartRE.MatchString(p) || p == "." || p == ".." || strings.TrimSpace(p) == "" {
				return refuse("invalid_share", "The share name is not valid.")
			}
		}
		if strings.HasSuffix(parts[0], "$") {
			return refuse("system_share", "Admin and hidden shares (names ending in $) are never mounted.")
		}
		if s.User == "" || s.Password == "" || guests[strings.ToLower(userPart(s.User))] {
			return refuse("guest_refused", "A NAS share needs its own user and password; guest access is refused.")
		}
		if !userRE.MatchString(s.User) {
			return refuse("invalid_user", "The user name is not valid.")
		}
		if len(s.Password) > 256 || strings.ContainsAny(s.Password, "\x00\r\n") {
			return refuse("invalid_password", "The password may not contain line breaks and is at most 256 characters.")
		}
	case NFS:
		if s.User != "" || s.Password != "" {
			return refuse("nfs_no_credentials", "NFS shares use the hub's address, not a user and password.")
		}
		if !strings.HasPrefix(s.Share, "/") || s.Share == "/" {
			return refuse("system_share", "Name an export folder on the NAS, not its root.")
		}
		for _, p := range strings.Split(strings.Trim(s.Share, "/"), "/") {
			if !nfsPartRE.MatchString(p) || p == "." || p == ".." {
				return refuse("invalid_share", "The export path is not valid.")
			}
		}
		clean := filepath.Clean(s.Share)
		for _, sys := range systemExports {
			if clean == sys || strings.HasPrefix(clean, sys+"/") {
				return refuse("system_share", "System folders of the NAS are never mounted.")
			}
		}
	default:
		return refuse("invalid_protocol", "The protocol must be smb or nfs.")
	}
	return nil
}

func userPart(u string) string {
	if i := strings.LastIndex(u, `\`); i >= 0 {
		return u[i+1:]
	}
	return u
}

// Runner runs one program and returns its combined output. A non-zero exit
// is not an error; err means it could not run or ctx ended.
type Runner interface {
	Exec(ctx context.Context, name string, args ...string) (out []byte, exit int, err error)
}

// ExecRunner runs real programs with LC_ALL=C and an empty environment
// otherwise, so no PASSWD or USER variable reaches mount.cifs.
type ExecRunner struct{}

// Exec implements Runner.
func (ExecRunner) Exec(ctx context.Context, name string, args ...string) ([]byte, int, error) {
	var buf bytes.Buffer
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout, cmd.Stderr = &buf, &buf
	cmd.Env = []string{"LC_ALL=C", "PATH=/usr/sbin:/usr/bin:/sbin:/bin"}
	err := cmd.Run()
	if ctx.Err() != nil {
		return buf.Bytes(), -1, ctx.Err()
	}
	var ee *exec.ExitError
	if errors.As(err, &ee) {
		return buf.Bytes(), ee.ExitCode(), nil
	}
	if err != nil {
		return nil, -1, err
	}
	return buf.Bytes(), 0, nil
}

// Manager mounts and checks NAS shares. Zero fields get the real defaults.
type Manager struct {
	Base     string // mount points are <Base>/<id>
	CredDir  string // tmpfs folder for the short-lived credentials files
	UID, GID int    // owner of SMB files on the hub (the gateway's user); -1 leaves cifs's default
	Run      Runner
	Log      *slog.Logger
	// Seams for tests; nil means the real system.
	IsTmpfs   func(dir string) (bool, error)
	IsMounted func(dir string) (bool, error)
	Probe     func(ctx context.Context, dir string) error
	LookPath  func(string) (string, error)
	Now       func() time.Time

	op     sync.Mutex // one Mount or Unmount at a time
	mu     sync.Mutex // guards mounts
	mounts map[string]*Status
}

func (m *Manager) now() time.Time {
	if m.Now != nil {
		return m.Now().UTC()
	}
	return time.Now().UTC()
}

func (m *Manager) log() *slog.Logger {
	if m.Log != nil {
		return m.Log
	}
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func (m *Manager) run() Runner {
	if m.Run != nil {
		return m.Run
	}
	return ExecRunner{}
}

func (m *Manager) credDir() string {
	if m.CredDir != "" {
		return m.CredDir
	}
	return DefaultCredDir
}

// Configured refuses a base that is a hub system folder or not absolute.
func (m *Manager) Configured() error {
	b := filepath.Clean(m.Base)
	if m.Base == "" || !filepath.IsAbs(m.Base) {
		return refuse("not_configured", "No folder for network mounts is set on this hub.")
	}
	for _, sys := range systemBases {
		if b == sys {
			return refuse("system_path", "Network mounts never go on a system folder of the hub.")
		}
	}
	return nil
}

// Unavailable says why this hub cannot mount a protocol ("" when it can).
func (m *Manager) Unavailable(protocol string) string {
	if err := m.Configured(); err != nil {
		return err.(*Refusal).Message
	}
	look := m.LookPath
	if look == nil {
		look = exec.LookPath
	}
	tool, pkg := "mount.cifs", "cifs-utils"
	if protocol == NFS {
		tool, pkg = "mount.nfs", "nfs-common"
	}
	if _, err := look(tool); err != nil {
		if _, err2 := look(filepath.Join("/usr/sbin", tool)); err2 != nil {
			return pkg + " is not installed on this hub"
		}
	}
	return ""
}

func (m *Manager) dir(id string) string { return filepath.Join(m.Base, id) }

func (m *Manager) set(id string, st Status) Status {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.mounts == nil {
		m.mounts = map[string]*Status{}
	}
	if old := m.mounts[id]; old != nil && old.State == st.State && old.Reason == st.Reason {
		st.Since = old.Since
	}
	m.mounts[id] = &st
	return st
}

// List is every mount this service made or was told about since it started.
func (m *Manager) List() []Status {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]Status, 0, len(m.mounts))
	for _, st := range m.mounts {
		out = append(out, *st)
	}
	return out
}

// prepare makes the mount point and its marker, and refuses a mount point
// with anything else in it.
func (m *Manager) prepare(dir string) error {
	if err := os.MkdirAll(m.Base, 0o755); err != nil {
		return fmt.Errorf("mount base: %w", err)
	}
	if fi, err := os.Lstat(dir); err == nil && !fi.IsDir() {
		return refuse("mountpoint_not_empty", "The mount point is not a folder; nothing was mounted.")
	}
	if err := os.Mkdir(dir, 0o755); err != nil && !errors.Is(err, os.ErrExist) {
		return fmt.Errorf("mount point: %w", err)
	}
	ents, err := os.ReadDir(dir)
	if err != nil {
		return fmt.Errorf("mount point: %w", err)
	}
	for _, e := range ents {
		if e.Name() != Marker {
			return refuse("mountpoint_not_empty",
				"Files were written into the mount point while the NAS was not mounted; move them away before mounting.")
		}
	}
	if len(ents) == 0 {
		if err := os.WriteFile(filepath.Join(dir, Marker), []byte("nothing is mounted here\n"), 0o444); err != nil {
			return fmt.Errorf("marker: %w", err)
		}
	}
	return nil
}

func (m *Manager) mounted(dir string) (bool, error) {
	if m.IsMounted != nil {
		return m.IsMounted(dir)
	}
	f, err := os.Open("/proc/self/mountinfo")
	if err != nil {
		return false, err
	}
	defer f.Close()
	return MountedIn(f, dir)
}

// MountedIn reports whether dir is a mount point in a mountinfo listing.
func MountedIn(r io.Reader, dir string) (bool, error) {
	b, err := io.ReadAll(io.LimitReader(r, 8<<20))
	if err != nil {
		return false, err
	}
	want := filepath.Clean(dir)
	for _, line := range strings.Split(string(b), "\n") {
		f := strings.Fields(line)
		if len(f) > 4 && unescape(f[4]) == want {
			return true, nil
		}
	}
	return false, nil
}

// unescape undoes mountinfo's octal escapes (\040 for a space).
func unescape(s string) string {
	if !strings.Contains(s, `\`) {
		return s
	}
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		if s[i] == '\\' && i+4 <= len(s) {
			if n, err := strconv.ParseUint(s[i+1:i+4], 8, 8); err == nil {
				b.WriteByte(byte(n))
				i += 3
				continue
			}
		}
		b.WriteByte(s[i])
	}
	return b.String()
}

// probe reads the mount point within ProbeTimeout. A read stuck on a dead
// server counts as failing; the stuck goroutine ends when the soft mount
// gives up.
func (m *Manager) probe(ctx context.Context, dir string) error {
	if m.Probe != nil {
		return m.Probe(ctx, dir)
	}
	ctx, cancel := context.WithTimeout(ctx, ProbeTimeout)
	defer cancel()
	done := make(chan error, 1)
	go func() {
		f, err := os.Open(dir)
		if err == nil {
			_, err = f.Readdirnames(1)
			f.Close()
			if errors.Is(err, io.EOF) {
				err = nil
			}
		}
		done <- err
	}()
	select {
	case err := <-done:
		return err
	case <-ctx.Done():
		return errors.New("the NAS did not answer in time")
	}
}

// healthy is "mounted, the marker hidden, and readable".
func (m *Manager) healthy(ctx context.Context, dir string) (string, string) {
	ok, err := m.mounted(dir)
	if err != nil || !ok {
		return "not_mounted", "The share is not mounted."
	}
	if _, err := os.Lstat(filepath.Join(dir, Marker)); err == nil {
		return "not_mounted", "The mount point still shows its marker; the share is not mounted."
	}
	if err := m.probe(ctx, dir); err != nil {
		return "unreachable", "The NAS does not answer; Files shows this location as failing until it is back."
	}
	return "", ""
}

// Check reads one mount and reports its state.
func (m *Manager) Check(ctx context.Context, id string) (Status, error) {
	if !ValidID(id) {
		return Status{}, refuse("invalid_id", "That is not a mount id.")
	}
	m.mu.Lock()
	prev := m.mounts[id]
	m.mu.Unlock()
	st := Status{ID: id, State: StateMounted, Since: m.now()}
	if prev != nil {
		st.Protocol, st.Access = prev.Protocol, prev.Access
	}
	if reason, msg := m.healthy(ctx, m.dir(id)); reason != "" {
		st.State, st.Reason, st.Message = StateFailing, reason, msg
		if prev == nil {
			st.State = StateUnmounted
		}
	}
	if st.State != StateMounted && (prev == nil || prev.State != st.State) {
		m.log().Warn("network mount not healthy", "id", id, "reason", st.Reason)
	}
	return m.set(id, st), nil
}

// Mount makes sure the share is mounted at <Base>/<id>: a read-only test
// mount that must be readable first, then the mount with the access asked
// for. A mount that is already healthy is left alone; a dead one is
// detached and made again.
func (m *Manager) Mount(ctx context.Context, id string, s Spec) (Status, error) {
	if !ValidID(id) {
		return Status{}, refuse("invalid_id", "That is not a mount id.")
	}
	if err := s.Validate(); err != nil {
		return Status{}, err
	}
	if why := m.Unavailable(s.Protocol); why != "" {
		return Status{}, refuse("client_missing", why)
	}
	m.op.Lock()
	defer m.op.Unlock()
	dir := m.dir(id)
	if ok, _ := m.mounted(dir); ok {
		if reason, _ := m.healthy(ctx, dir); reason == "" {
			return m.set(id, Status{ID: id, State: StateMounted, Protocol: s.Protocol, Access: s.access(), Since: m.now()}), nil
		}
		m.umount(ctx, dir, true)
	}
	if err := m.prepare(dir); err != nil {
		return Status{}, err
	}
	cred := ""
	if s.Protocol == SMB {
		f, err := m.writeCreds(s)
		if err != nil {
			return Status{}, err
		}
		defer os.Remove(f)
		cred = f
	}
	if err := m.mountOnce(ctx, dir, s, cred, "ro"); err != nil {
		return Status{}, err
	}
	if reason, msg := m.healthy(ctx, dir); reason != "" {
		m.umount(ctx, dir, true)
		return Status{}, refuse("test_failed", msg)
	}
	if s.access() == "rw" {
		m.umount(ctx, dir, false)
		if err := m.mountOnce(ctx, dir, s, cred, "rw"); err != nil {
			return Status{}, err
		}
		if reason, msg := m.healthy(ctx, dir); reason != "" {
			m.umount(ctx, dir, true)
			return Status{}, refuse("test_failed", msg)
		}
	}
	m.log().Info("network share mounted", "id", id, "spec", s)
	return m.set(id, Status{ID: id, State: StateMounted, Protocol: s.Protocol, Access: s.access(), Since: m.now()}), nil
}

// writeCreds writes mount.cifs's credentials file: 0600, on tmpfs, a fresh
// random name, removed by the caller as soon as the mount call returns.
func (m *Manager) writeCreds(s Spec) (string, error) {
	dir := m.credDir()
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", fmt.Errorf("credentials folder: %w", err)
	}
	isTmpfs := m.IsTmpfs
	if isTmpfs == nil {
		isTmpfs = onTmpfs
	}
	if ok, err := isTmpfs(dir); err != nil || !ok {
		return "", refuse("creds_not_tmpfs", "The hub keeps NAS passwords only in memory, and its credentials folder is not in memory.")
	}
	var rnd [12]byte
	if _, err := rand.Read(rnd[:]); err != nil {
		return "", err
	}
	path := filepath.Join(dir, "cred-"+hex.EncodeToString(rnd[:]))
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return "", fmt.Errorf("credentials file: %w", err)
	}
	body := "username=" + userPart(s.User) + "\npassword=" + s.Password + "\n"
	if i := strings.LastIndex(s.User, `\`); i > 0 {
		body += "domain=" + s.User[:i] + "\n"
	}
	_, werr := f.WriteString(body)
	cerr := f.Close()
	if werr != nil || cerr != nil {
		os.Remove(path)
		return "", errors.New("credentials file could not be written")
	}
	return path, nil
}

// Args is the mount command line for a spec: never a password.
func (m *Manager) Args(dir string, s Spec, cred, access string) []string {
	opts := []string{access, "nosuid", "nodev", "noexec", "soft"}
	if s.Protocol == SMB {
		opts = append(opts, "vers=3", "sec=ntlmssp", "credentials="+cred, "echo_interval=10")
		if m.UID >= 0 && m.GID >= 0 {
			opts = append(opts, "uid="+strconv.Itoa(m.UID), "gid="+strconv.Itoa(m.GID),
				"forceuid", "forcegid", "file_mode=0660", "dir_mode=0770")
		}
		return []string{"-t", "cifs", "//" + s.Host + "/" + strings.Trim(s.Share, "/"), dir, "-o", strings.Join(opts, ",")}
	}
	opts = append(opts, "vers=4", "timeo=50", "retrans=2")
	return []string{"-t", "nfs", s.Host + ":" + filepath.Clean(s.Share), dir, "-o", strings.Join(opts, ",")}
}

func (m *Manager) mountOnce(ctx context.Context, dir string, s Spec, cred, access string) error {
	ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	out, code, err := m.run().Exec(ctx, "mount", m.Args(dir, s, cred, access)...)
	if err == nil && code == 0 {
		return nil
	}
	text := redact(string(out), s)
	m.log().Warn("network mount failed", "exit", code, "output", tail(text, 300))
	return classify(text)
}

func (m *Manager) umount(ctx context.Context, dir string, lazy bool) {
	args := []string{dir}
	if lazy {
		args = []string{"-l", dir}
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if out, code, err := m.run().Exec(ctx, "umount", args...); err != nil || code != 0 {
		m.log().Warn("umount failed", "exit", code, "output", tail(string(out), 200))
	}
}

// Unmount detaches a mount (lazily when the NAS is gone) and forgets it.
// The empty mount point and its marker stay.
func (m *Manager) Unmount(ctx context.Context, id string) error {
	if !ValidID(id) {
		return refuse("invalid_id", "That is not a mount id.")
	}
	m.op.Lock()
	defer m.op.Unlock()
	dir := m.dir(id)
	if ok, _ := m.mounted(dir); ok {
		m.umount(ctx, dir, true)
		if still, _ := m.mounted(dir); still {
			return errors.New("the share is still mounted")
		}
	}
	m.mu.Lock()
	delete(m.mounts, id)
	m.mu.Unlock()
	return nil
}

// redact takes every secret field out of program output before it is logged.
func redact(s string, sp Spec) string {
	for _, v := range []string{sp.Password, sp.User, sp.Host, sp.Share} {
		if len(v) >= 2 {
			s = strings.ReplaceAll(s, v, "[sealed]")
		}
	}
	return s
}

func tail(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) > n {
		s = "…" + s[len(s)-n:]
	}
	return s
}

// classify turns mount's output into a reason the owner can act on.
func classify(out string) error {
	o := strings.ToLower(out)
	switch {
	case strings.Contains(o, "permission denied") || strings.Contains(o, "logon failure") || strings.Contains(o, "access denied") || strings.Contains(o, "error(13)"):
		return refuse("auth_failed", "The NAS refused the user name or password.")
	case strings.Contains(o, "no such file") || strings.Contains(o, "error(2)") || strings.Contains(o, "bad network name"):
		return refuse("share_not_found", "The NAS has no share or export by that name.")
	case strings.Contains(o, "not supported") || strings.Contains(o, "error(95)") || strings.Contains(o, "protocol"):
		return refuse("protocol_refused", "The NAS does not offer SMB 3 or NFS 4; older versions are refused.")
	case strings.Contains(o, "host is down") || strings.Contains(o, "no route") || strings.Contains(o, "refused") ||
		strings.Contains(o, "timed out") || strings.Contains(o, "unreachable") || strings.Contains(o, "error(112)") ||
		strings.Contains(o, "could not connect") || strings.Contains(o, "error(111)") ||
		strings.Contains(o, "could not resolve") || strings.Contains(o, "resolve address"):
		return refuse("unreachable", "The NAS cannot be reached from the hub.")
	}
	return refuse("mount_failed", "The NAS share could not be mounted; see the hub's journal.")
}
