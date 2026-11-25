// SPDX-License-Identifier: Apache-2.0

package smb

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Unit is the Samba service the image ships (onemind-smb.service). It starts
// only while /data/onemind/samba/smb.conf exists, so a box with no approved
// share listens on nothing.
const Unit = "onemind-smb.service"

const (
	firstUID = 20000 // Unix accounts that only exist so Samba can name its users
	smbGID   = 20000
)

// Runner runs a program. stdin may carry a secret: it is never logged and
// never part of an error.
type Runner interface {
	Run(ctx context.Context, stdin string, name string, args ...string) ([]byte, error)
}

// ExecRunner is the real thing.
type ExecRunner struct{}

// Run implements Runner.
func (ExecRunner) Run(ctx context.Context, stdin, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	c := exec.CommandContext(ctx, name, args...)
	if stdin != "" {
		c.Stdin = strings.NewReader(stdin)
	}
	return c.CombinedOutput()
}

// Refusal is a well-formed request the box will not run now (stable Reason).
type Refusal struct{ Reason, Message string }

func (r *Refusal) Error() string { return r.Reason + ": " + r.Message }

// Manager applies the desired list to the box. One call at a time.
type Manager struct {
	P   Paths
	Run Runner
	// Have reports whether a program is installed (default exec.LookPath).
	Have func(string) bool

	mu sync.Mutex
}

func (m *Manager) have(prog string) bool {
	if m.Have != nil {
		return m.Have(prog)
	}
	_, err := exec.LookPath(prog)
	return err == nil
}

func (m *Manager) conf() string    { return filepath.Join(m.P.StateDir, "smb.conf") }
func (m *Manager) desired() string { return filepath.Join(m.P.StateDir, "desired.json") }
func (m *Manager) avahi() string   { return filepath.Join(m.P.StateDir, "avahi.service") }
func (m *Manager) extra(f string) string {
	return filepath.Join(m.P.StateDir, "extrausers", f)
}

// Unavailable says why this box cannot share files, or "".
func (m *Manager) Unavailable() string {
	for _, prog := range []string{"smbd", "smbpasswd", "testparm"} {
		if !m.have(prog) {
			return "Samba is not installed on this box (" + prog + " is missing)"
		}
	}
	return ""
}

// Current is the list the box was last given.
func (m *Manager) Current() []Share {
	b, err := os.ReadFile(m.desired())
	if err != nil {
		return nil
	}
	var l []Share
	if json.Unmarshal(b, &l) != nil {
		return nil
	}
	return l
}

// Apply makes the box share exactly list. The new config is checked with
// testparm before anything live changes; an empty list stops Samba and removes
// its config, so nothing is left listening.
func (m *Manager) Apply(ctx context.Context, list []Share) error {
	if err := Validate(list); err != nil {
		return &Refusal{"invalid_shares", err.Error()}
	}
	if why := m.Unavailable(); why != "" {
		return &Refusal{"smb_not_installed", why}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, d := range []string{"private", "state", "cache", "extrausers"} {
		mode := os.FileMode(0o755)
		if d == "private" {
			mode = 0o700
		}
		if err := os.MkdirAll(filepath.Join(m.P.StateDir, d), mode); err != nil {
			return err
		}
	}
	if len(list) == 0 {
		return m.stopAll(ctx)
	}
	conf := RenderConf(list, m.P)
	tmp := m.conf() + ".new"
	if err := os.WriteFile(tmp, []byte(conf), 0o644); err != nil {
		return err
	}
	defer os.Remove(tmp)
	if out, err := m.Run.Run(ctx, "", "testparm", "-s", "--suppress-prompt", tmp); err != nil {
		return &Refusal{"config_rejected", "Samba rejected the configuration: " + tail(out)}
	}
	if err := m.writeUsers(Users(list)); err != nil {
		return err
	}
	if err := writeAtomic(m.avahi(), []byte(RenderAvahi(list)), 0o644); err != nil {
		return err
	}
	// Accounts of people who no longer share anything lose their Samba password.
	for _, gone := range missing(Users(m.Current()), Users(list)) {
		_, _ = m.Run.Run(ctx, "", "pdbedit", "-s", m.conf(), "-x", "-u", gone)
	}
	b, _ := json.Marshal(list)
	if err := writeAtomic(m.desired(), b, 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp, m.conf()); err != nil {
		return err
	}
	if out, err := m.Run.Run(ctx, "", "systemctl", "reload-or-restart", Unit); err != nil {
		return fmt.Errorf("starting Samba: %w: %s", err, tail(out))
	}
	return nil
}

func (m *Manager) stopAll(ctx context.Context) error {
	for _, gone := range Users(m.Current()) {
		_, _ = m.Run.Run(ctx, "", "pdbedit", "-s", m.conf(), "-x", "-u", gone)
	}
	if out, err := m.Run.Run(ctx, "", "systemctl", "stop", Unit); err != nil {
		return fmt.Errorf("stopping Samba: %w: %s", err, tail(out))
	}
	for _, f := range []string{m.conf(), m.avahi(), m.desired()} {
		if err := os.Remove(f); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	}
	return nil
}

// SetPassword sets the SMB password of a person who has a share. The password
// goes to smbpasswd on stdin only: not in an argument, a log or an error.
func (m *Manager) SetPassword(ctx context.Context, user, password string) error {
	if len(password) < 8 || len(password) > 128 || strings.ContainsAny(password, "\x00\r\n") {
		return &Refusal{"bad_password", "an SMB password is 8 to 128 characters on one line"}
	}
	if why := m.Unavailable(); why != "" {
		return &Refusal{"smb_not_installed", why}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	known := false
	for _, u := range Users(m.Current()) {
		known = known || u == user
	}
	if !known {
		return &Refusal{"unknown_user", "no approved share belongs to " + user}
	}
	if _, err := m.Run.Run(ctx, password+"\n"+password+"\n", "smbpasswd", "-c", m.conf(), "-a", "-s", user); err != nil {
		return errors.New("smbpasswd could not set the password")
	}
	return nil
}

// writeUsers keeps /data/onemind/samba/extrausers (libnss-extrausers) listing
// one locked Unix account per Samba user. Known accounts keep their uid.
func (m *Manager) writeUsers(users []string) error {
	have := map[string]int{}
	if f, err := os.Open(m.extra("passwd")); err == nil {
		sc := bufio.NewScanner(f)
		for sc.Scan() {
			p := strings.Split(sc.Text(), ":")
			if len(p) > 2 {
				if n, err := strconv.Atoi(p[2]); err == nil {
					have[p[0]] = n
				}
			}
		}
		f.Close()
	}
	// The owner's console password (admin, onemind-owner password) lives in this same shadow file; only the SMB
	// accounts are ours to rewrite. Every shadow line for a name that was not an SMB account is kept as it is.
	var keep bytes.Buffer
	if b, err := os.ReadFile(m.extra("shadow")); err == nil {
		for _, l := range strings.Split(string(b), "\n") {
			if name, _, ok := strings.Cut(l, ":"); ok && name != "" {
				if _, smbAccount := have[name]; !smbAccount {
					keep.WriteString(l + "\n")
				}
			}
		}
	}
	next := firstUID
	for _, n := range have {
		if n >= next {
			next = n + 1
		}
	}
	var pw, sh bytes.Buffer
	sh.Write(keep.Bytes())
	for _, u := range users {
		id, ok := have[u]
		if !ok {
			id, next = next, next+1
		}
		fmt.Fprintf(&pw, "%s:x:%d:%d:OneMind SMB account:/nonexistent:/usr/sbin/nologin\n", u, id, smbGID)
		fmt.Fprintf(&sh, "%s:!:19000:0:99999:7:::\n", u)
	}
	if err := writeAtomic(m.extra("passwd"), pw.Bytes(), 0o644); err != nil {
		return err
	}
	if err := writeAtomic(m.extra("shadow"), sh.Bytes(), 0o640); err != nil {
		return err
	}
	// unix_chkpwd (sudo, su) runs as group shadow; best effort, a dev machine may have no such group.
	if g, err := user.LookupGroup("shadow"); err == nil {
		if gid, err := strconv.Atoi(g.Gid); err == nil {
			_ = os.Chown(m.extra("shadow"), -1, gid)
		}
	}
	return writeAtomic(m.extra("group"), []byte(fmt.Sprintf("onemind-smb:x:%d:\n", smbGID)), 0o644)
}

func missing(old, cur []string) []string {
	keep := map[string]bool{}
	for _, u := range cur {
		keep[u] = true
	}
	var out []string
	for _, u := range old {
		if !keep[u] {
			out = append(out, u)
		}
	}
	return out
}

func tail(b []byte) string {
	s := strings.TrimSpace(string(b))
	if len(s) > 300 {
		s = s[len(s)-300:]
	}
	return s
}

// writeAtomic: temp file, fsync, rename, so a power cut leaves the old file or the new one.
func writeAtomic(path string, b []byte, mode os.FileMode) error {
	f, err := os.CreateTemp(filepath.Dir(path), ".tmp-*")
	if err != nil {
		return err
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, err := f.Write(b); err != nil {
		f.Close()
		return err
	}
	if err := f.Chmod(mode); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
