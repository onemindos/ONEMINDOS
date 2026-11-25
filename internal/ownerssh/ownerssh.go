// SPDX-License-Identifier: Apache-2.0

// Package ownerssh is the box side of the owner's SSH access (P-06: SSH keys and the SSH switch). It runs inside
// `onemindd host serve`, which is sandboxed (no /home, no way to start sshd), so it never touches a key file or
// sshd itself. A change is one text job in /data/onemind/ssh/job; the manager starts onemind-ssh-apply.service,
// a root oneshot that runs `onemind-owner apply-job` (os/rootfs/layers/onemind/usr/lib/onemind/onemind-owner),
// and reads the outcome from /data/onemind/ssh/result. The same script serves the console, so a key added on the
// box and a key added through the gateway end up in the same place and in the same list.
//
// The gateway has already checked the owner's approval and the key; this package checks again, because it is the
// last step before a key can open a shell.
package ownerssh

import (
	"bufio"
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	// ApplyUnit is the oneshot that does the work as root.
	ApplyUnit = "onemind-ssh-apply.service"
	// SSHUnit is sshd.
	SSHUnit = "ssh.service"
	// Tool is the image's owner-shell script.
	Tool = "/usr/lib/onemind/onemind-owner"
	// Sshd is the server binary; without it this box has no SSH to manage.
	Sshd = "/usr/sbin/sshd"
	// MaxKeys bounds the authorised keys: a home box has a handful.
	MaxKeys = 20
	// MaxKeyBytes bounds one public key line (an RSA 8192 key is about 1.6 KB).
	MaxKeyBytes = 8192
	// PublicRule is the firewall file a cloud board ships (os/boards/{cloud,vm-do}): it sends port 22 from any
	// address to the "ssh" chain, so SSH is reachable from the internet there, not only from the LAN and the mesh.
	PublicRule = "/etc/onemind/host.d/10-cloud.nft"
)

var (
	fingerprintRe = regexp.MustCompile(`^SHA256:[A-Za-z0-9+/]{43}$`)
	// ssh-keygen -l prints: "256 SHA256:... comment text (ED25519)"
	listRe = regexp.MustCompile(`^(\d+) (SHA256:[A-Za-z0-9+/]{43})(?: (.*))? \(([A-Za-z0-9-]+)\)$`)
)

// Key is one authorised key as ssh-keygen reports it.
type Key struct {
	Fingerprint string `json:"fingerprint"`
	Type        string `json:"type"`
	Bits        int    `json:"bits"`
	Comment     string `json:"comment"`
}

// State is what the box reports.
type State struct {
	Enabled bool `json:"enabled"` // the owner has not switched SSH off
	Running bool `json:"running"` // sshd is up (it starts only once an owner key exists)
	// Internet is true on a cloud board: its firewall lets port 22 in from any address (PublicRule), still
	// through the rate limit and the off switch. Elsewhere SSH answers the LAN and the mesh only.
	Internet bool  `json:"internet"`
	Keys     []Key `json:"keys"`
}

// Refusal is a well-formed request the box will not run (stable Reason, a sentence for the owner).
type Refusal struct{ Reason, Message string }

func (r *Refusal) Error() string { return r.Reason + ": " + r.Message }

// Runner runs a program and returns its combined output.
type Runner interface {
	Run(ctx context.Context, name string, args ...string) ([]byte, error)
}

// ExecRunner is the real thing.
type ExecRunner struct{}

// Run implements Runner.
func (ExecRunner) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()
	return exec.CommandContext(ctx, name, args...).CombinedOutput()
}

// Manager applies SSH changes. One at a time.
type Manager struct {
	// Dir is the state directory on the data partition (default /data/onemind/ssh).
	Dir string
	Run Runner
	// Have reports whether the sshd binary and the owner-shell tool exist (default os.Stat).
	Have func(string) bool

	mu sync.Mutex
}

func (m *Manager) dir() string {
	if m.Dir != "" {
		return m.Dir
	}
	return "/data/onemind/ssh"
}

func (m *Manager) have(p string) bool {
	if m.Have != nil {
		return m.Have(p)
	}
	_, err := os.Stat(p)
	return err == nil
}

// Unavailable says why this box has no SSH to manage, or "".
func (m *Manager) Unavailable() string {
	if !m.have(Sshd) {
		return "SSH is not installed on this box (sshd is missing)"
	}
	if !m.have(Tool) {
		return "this image has no owner-shell tool"
	}
	return ""
}

// ValidateKey checks one public key line: a plain key (no options such as command= or from=), one line.
func ValidateKey(line string) error {
	switch {
	case line == "" || len(line) > MaxKeyBytes:
		return &Refusal{"invalid_key", "that is not a plain SSH public key"}
	case strings.ContainsAny(line, "\r\n\x00"):
		return &Refusal{"invalid_key", "an SSH public key is one line"}
	case !strings.HasPrefix(line, "ssh-") && !strings.HasPrefix(line, "ecdsa-") && !strings.HasPrefix(line, "sk-"):
		return &Refusal{"invalid_key", "that is not a plain SSH public key (options such as command= are not accepted)"}
	}
	for _, r := range line {
		if r < 0x20 || r == 0x7f {
			return &Refusal{"invalid_key", "an SSH public key has no control characters"}
		}
	}
	return nil
}

// State reads the box: the switch, whether sshd runs and the fingerprints of the authorised keys.
func (m *Manager) State(ctx context.Context) (State, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.stateLocked(ctx)
}

func (m *Manager) stateLocked(ctx context.Context) (State, error) {
	_, offErr := os.Stat(filepath.Join(m.dir(), "disabled"))
	st := State{Enabled: offErr != nil, Internet: m.have(PublicRule)}
	out, _ := m.Run.Run(ctx, "systemctl", "is-active", SSHUnit)
	st.Running = strings.TrimSpace(string(out)) == "active"
	raw, err := os.ReadFile(filepath.Join(m.dir(), "keys.list"))
	if os.IsNotExist(err) {
		// Nothing has published the list yet (a fresh box): ask the apply unit to, with no job.
		if _, err := m.Run.Run(ctx, "systemctl", "start", ApplyUnit); err != nil {
			return st, fmt.Errorf("ssh state: %w", err)
		}
		raw, err = os.ReadFile(filepath.Join(m.dir(), "keys.list"))
	}
	if err != nil && !os.IsNotExist(err) {
		return st, fmt.Errorf("ssh state: %w", err)
	}
	st.Keys = ParseKeys(raw)
	return st, nil
}

// ParseKeys reads `ssh-keygen -l -f authorized_keys` output.
func ParseKeys(raw []byte) []Key {
	keys := []Key{}
	sc := bufio.NewScanner(bytes.NewReader(raw))
	for sc.Scan() {
		m := listRe.FindStringSubmatch(strings.TrimSpace(sc.Text()))
		if m == nil {
			continue
		}
		bits, _ := strconv.Atoi(m[1])
		keys = append(keys, Key{Fingerprint: m[2], Bits: bits, Comment: m[3], Type: strings.ToLower(m[4])})
	}
	return keys
}

// AddKey authorises one public key for the owner account.
func (m *Manager) AddKey(ctx context.Context, line string) error {
	if err := ValidateKey(line); err != nil {
		return err
	}
	if why := m.Unavailable(); why != "" {
		return &Refusal{"ssh_not_installed", why}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	st, err := m.stateLocked(ctx)
	if err != nil {
		return err
	}
	if len(st.Keys) >= MaxKeys {
		return &Refusal{"too_many_keys", fmt.Sprintf("this box allows at most %d SSH keys", MaxKeys)}
	}
	return m.job(ctx, "key-add", line)
}

// RemoveKey takes one key out by its SHA256 fingerprint.
func (m *Manager) RemoveKey(ctx context.Context, fingerprint string) error {
	if !fingerprintRe.MatchString(fingerprint) {
		return &Refusal{"invalid_fingerprint", "that is not an SSH key fingerprint (SHA256:...)"}
	}
	if why := m.Unavailable(); why != "" {
		return &Refusal{"ssh_not_installed", why}
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.job(ctx, "key-rm", fingerprint)
}

// SetEnabled switches SSH on or off. Off stops sshd and keeps it off after a reboot.
func (m *Manager) SetEnabled(ctx context.Context, on bool) error {
	if why := m.Unavailable(); why != "" {
		return &Refusal{"ssh_not_installed", why}
	}
	arg := "off"
	if on {
		arg = "on"
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.job(ctx, "ssh", arg)
}

// job files one job, runs the apply unit and turns its result file into nil or a Refusal.
func (m *Manager) job(ctx context.Context, op, arg string) error {
	if err := os.MkdirAll(m.dir(), 0o700); err != nil {
		return fmt.Errorf("ssh job: %w", err)
	}
	result := filepath.Join(m.dir(), "result")
	_ = os.Remove(result)
	tmp, err := os.CreateTemp(m.dir(), ".job.")
	if err != nil {
		return fmt.Errorf("ssh job: %w", err)
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.WriteString(op + "\n" + arg + "\n"); err != nil {
		tmp.Close()
		return fmt.Errorf("ssh job: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("ssh job: %w", err)
	}
	if err := os.Rename(tmp.Name(), filepath.Join(m.dir(), "job")); err != nil {
		return fmt.Errorf("ssh job: %w", err)
	}
	if _, err := m.Run.Run(ctx, "systemctl", "start", ApplyUnit); err != nil {
		return fmt.Errorf("ssh job: starting %s: %w", ApplyUnit, err)
	}
	raw, err := os.ReadFile(result)
	if err != nil {
		return fmt.Errorf("ssh job: no result: %w", err)
	}
	return parseResult(string(raw))
}

// parseResult reads "rc=N\nmessage\n". Exit codes of onemind-owner: 0 done, 2 not a valid key or fingerprint,
// 3 a symlink is in the owner's home, 4 no such key.
func parseResult(s string) error {
	lines := strings.SplitN(strings.TrimSpace(s), "\n", 2)
	rc, ok := strings.CutPrefix(lines[0], "rc=")
	if !ok {
		return fmt.Errorf("ssh job: unreadable result")
	}
	msg := ""
	if len(lines) > 1 {
		msg = strings.TrimPrefix(strings.TrimSpace(lines[1]), "onemind-owner: ")
	}
	switch rc {
	case "0":
		return nil
	case "2":
		return &Refusal{"invalid_key", "the box did not accept that key"}
	case "3":
		return &Refusal{"unsafe_home", "the owner's home holds a link where a key file should be; nothing was changed"}
	case "4":
		return &Refusal{"no_such_key", "that key is not on this box any more"}
	}
	// Do not echo msg: it is a program's output. The journal has it.
	_ = msg
	return fmt.Errorf("ssh job: onemind-owner exited %s", rc)
}
