// SPDX-License-Identifier: Apache-2.0

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
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// Marker is the file a mount point holds while nothing is mounted on it.
const Marker = ".onemind-not-mounted"

// Defaults for the storage service (cmd/onemindd).
const (
	DefaultCredDir = "/run/onemind/netmount"
	ProbeTimeout   = 5 * time.Second
)

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

// source is the mount source for a spec: //host/share or host:/export.
func source(s Spec) string {
	if s.Protocol == SMB {
		return "//" + s.Host + "/" + strings.Trim(s.Share, "/")
	}
	return s.Host + ":" + filepath.Clean(s.Share)
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
		return []string{"-t", "cifs", source(s), dir, "-o", strings.Join(opts, ",")}
	}
	opts = append(opts, "vers=4", "timeo=50", "retrans=2")
	return []string{"-t", "nfs", source(s), dir, "-o", strings.Join(opts, ",")}
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
