// SPDX-License-Identifier: Apache-2.0

// Package flatpak is the box side of Flathub desktop apps (issue #1097, D-026, D-027).
//
// Debian 13 packages flatpak, so OneMind builds none of it. This package only drives the `flatpak` program against
// one system installation that lives on /data (so the root can stay read-only and the apps survive a reboot and an
// A/B OS update). It never decides anything: the gateway calls it after an owner approved the install, update or
// removal. Every app is installed with the same sandbox overrides: no host files, no home folder, no door back out
// to the host, and one folder of its own (the "granted folder") that the owner can see in Files.
package flatpak

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	// Installation is the name in /etc/flatpak/installations.d/onemind.conf (Path=/data/onemind/flatpak).
	Installation = "onemind"
	// Remote is the one remote the box adds. Search, install and update use only this one.
	Remote = "flathub"
	// RemoteURL is the .flatpakrepo file, which carries the repository's signing key (flatpak verifies it).
	RemoteURL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
	// DesktopUID is the user of the desktop streaming runtime (apps/_bases/desktop): it must own the granted folder.
	DesktopUID = 1000

	maxResults = 50
)

// idRE is a Flatpak application id: reverse DNS, at least three parts (org.example.App). Anything else never
// reaches a command line.
var idRE = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*){2,}$`)

// ValidID reports whether id may be given to flatpak.
func ValidID(id string) bool { return len(id) <= 255 && idRE.MatchString(id) }

// Refusal is a well-formed request the box will not run (stable Reason).
type Refusal struct{ Reason, Message string }

func (r *Refusal) Error() string { return r.Reason + ": " + r.Message }

// App is one Flathub or installed application.
type App struct {
	ID      string `json:"app_id"`
	Name    string `json:"name"`
	Summary string `json:"summary"`
	Version string `json:"version"`
	// Installed apps only:
	Installed       bool   `json:"installed"`
	UpdateAvailable bool   `json:"update_available"`
	Folder          string `json:"folder,omitempty"` // the granted folder, as the runtime sees it
}

// Runner runs `flatpak <args>` as root against the box's installation, and makes an app's granted folder.
// Both happen in a transient systemd unit, never in the host service itself: that service is deliberately
// capability-less (no CAP_CHOWN, no @privileged system calls), so anything that needs a capability runs in a unit
// that is given exactly that capability and nothing else.
type Runner interface {
	Run(ctx context.Context, args ...string) ([]byte, error)
	// Prepare makes <appDir> (root, 0755, so the runtime and the Files service can walk through it) and <folder> in
	// it (the runtime's user, 0755). It follows no symbolic link.
	Prepare(ctx context.Context, appDir, folder string) error
}

// SystemdRunner runs flatpak and the folder step in transient systemd units. The argument lists are fixed here and
// in Manager: no caller text becomes an option. The units are hardened beyond the host service's own hardening
// where the work allows (flatpak needs namespaces and a normal capability set for ostree and bwrap, so those are
// left, and the kernel, clock, hostname, devices, realtime and personality are closed).
type SystemdRunner struct{ Dir, FilesDir string }

// prepareScript is the whole folder step. $1 is the app's folder under FilesDir, $2 the granted folder in it.
const prepareScript = `set -eu
if [ -L "$1" ] || [ -L "$2" ]; then echo "refusing a symbolic link" >&2; exit 1; fi
install -d -o 0 -g 0 -m 0755 "$1"
install -d -o ` + "1000 -g 1000" + ` -m 0755 "$2"`

func (s SystemdRunner) common() []string {
	return []string{"--quiet", "--wait", "--pipe", "--collect", "--service-type=exec",
		"-p", "ProtectSystem=strict", "-p", "PrivateTmp=yes", "-p", "ProtectHome=yes", "-p", "PrivateDevices=yes",
		"-p", "ProtectKernelTunables=yes", "-p", "ProtectKernelModules=yes", "-p", "ProtectKernelLogs=yes",
		"-p", "ProtectControlGroups=yes", "-p", "ProtectClock=yes", "-p", "ProtectHostname=yes",
		"-p", "RestrictRealtime=yes", "-p", "LockPersonality=yes", "-p", "SystemCallArchitectures=native",
		"-p", "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK"}
}

// flatpakArgs is the systemd-run command line for one flatpak call.
func (s SystemdRunner) flatpakArgs(args ...string) []string {
	pre := append(s.common(),
		"-p", "CapabilityBoundingSet=~CAP_SYS_MODULE CAP_SYS_BOOT CAP_SYS_TIME CAP_SYS_RAWIO CAP_SYS_PTRACE CAP_SYSLOG CAP_AUDIT_CONTROL CAP_MAC_ADMIN CAP_MAC_OVERRIDE CAP_WAKE_ALARM",
		"-p", "ReadWritePaths="+s.Dir, "-p", "Environment=HOME="+s.Dir+"/home",
		"--", "/usr/bin/flatpak")
	return append(pre, args...)
}

// prepareArgs is the systemd-run command line for the folder step: no network, and only the three capabilities
// that making a folder for another user needs.
func (s SystemdRunner) prepareArgs(appDir, folder string) []string {
	pre := append(s.common(),
		"-p", "CapabilityBoundingSet=CAP_CHOWN CAP_FOWNER CAP_DAC_OVERRIDE", "-p", "PrivateNetwork=yes",
		"-p", "RestrictNamespaces=yes", "-p", "ReadWritePaths="+s.FilesDir,
		"--", "/bin/sh", "-c", prepareScript, "sh", appDir, folder)
	return pre
}

func (s SystemdRunner) systemdRun(ctx context.Context, args []string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 20*time.Minute)
	defer cancel()
	c := exec.CommandContext(ctx, "/usr/bin/systemd-run", args...)
	var out bytes.Buffer
	c.Stdout, c.Stderr = &out, &out
	err := c.Run()
	return out.Bytes(), err
}

// Run implements Runner.
func (s SystemdRunner) Run(ctx context.Context, args ...string) ([]byte, error) {
	return s.systemdRun(ctx, s.flatpakArgs(args...))
}

// Prepare implements Runner.
func (s SystemdRunner) Prepare(ctx context.Context, appDir, folder string) error {
	if out, err := s.systemdRun(ctx, s.prepareArgs(appDir, folder)); err != nil {
		return fail("prepare folder", out, err)
	}
	return nil
}

// Manager drives flatpak. One mutating call at a time.
type Manager struct {
	Run        Runner
	FilesDir   string // /data/onemind/desktop-apps: one granted folder per app
	SessionDir string // /data/onemind/desktop-session: the launch file the streaming runtime reads
	URL        string // the remote's .flatpakrepo (default RemoteURL; a test points it at a local repo)
	// Have reports whether a program is installed (default exec.LookPath).
	Have func(string) bool
	// Now is the clock for the update cache (default time.Now).
	Now func() time.Time

	mu    sync.Mutex
	umu   sync.Mutex // guards the update cache
	upd   map[string]bool
	updAt time.Time
}

// updateTTL is how long the answer to "which apps have an update" is kept: asking the remote costs a network call
// in a unit of its own, and the dashboard polls. Install, update and remove forget it at once.
const updateTTL = 10 * time.Minute

// updateAskTimeout bounds one ask of the remote; updateFailTTL is how long a failed ask is remembered.
const (
	updateAskTimeout = 30 * time.Second
	updateFailTTL    = time.Minute
)

// NewDefault is the box's manager.
func NewDefault() *Manager {
	const dir, files, session = "/data/onemind/flatpak", "/data/onemind/desktop-apps", "/data/onemind/desktop-session"
	return &Manager{Run: SystemdRunner{Dir: dir, FilesDir: files}, FilesDir: files, SessionDir: session}
}

func (m *Manager) have(p string) bool {
	if m.Have != nil {
		return m.Have(p)
	}
	_, err := exec.LookPath(p)
	return err == nil
}

// Unavailable says why this box cannot run desktop apps, or "".
func (m *Manager) Unavailable() string {
	for _, p := range []string{"flatpak", "systemd-run"} {
		if !m.have(p) {
			return "Flatpak is not installed on this box (" + p + " is missing)"
		}
	}
	return ""
}

// Folder is an app's granted folder.
func (m *Manager) Folder(id string) string { return filepath.Join(m.FilesDir, id, "files") }

func (m *Manager) fp(ctx context.Context, args ...string) ([]byte, error) {
	return m.Run.Run(ctx, append([]string{"--installation=" + Installation}, args...)...)
}

// SandboxArgs are the overrides every app gets: the granted folder is the only place it reaches on the host.
//
// --nofilesystem=host:reset clears every filesystem permission the app's manifest or an earlier layer gave
// (xdg-documents, xdg-download, /media, /mnt, ~/.config/x and so on); a plain --nofilesystem=host removes only that
// one exact grant. It needs Flatpak 1.14 or newer (Debian 13 ships 1.16; the exact first version is UNVERIFIED).
// The folder is granted after it. A full session or system bus is a door to the host whatever --no-talk-name says,
// so both sockets are removed, with the other agents an app could reach the host's secrets or printers through.
func SandboxArgs(folder string) []string {
	return []string{"--nofilesystem=host:reset", "--nofilesystem=host", "--nofilesystem=host-os", "--nofilesystem=host-etc", "--nofilesystem=home",
		"--nosocket=session-bus", "--nosocket=system-bus", "--nosocket=ssh-auth", "--nosocket=pcsc", "--nosocket=cups", "--nosocket=gpg-agent",
		"--no-talk-name=org.freedesktop.Flatpak", "--no-talk-name=org.freedesktop.systemd1",
		"--nodevice=all", "--filesystem=" + folder + ":rw"}
}

func (m *Manager) ready(id string) error {
	if why := m.Unavailable(); why != "" {
		return &Refusal{"flatpak_not_installed", why}
	}
	if !ValidID(id) {
		return &Refusal{"invalid_app", "that is not a Flatpak application id (for example md.obsidian.Obsidian)"}
	}
	return nil
}

func fail(what string, out []byte, err error) error {
	tail := strings.TrimSpace(string(out))
	if len(tail) > 300 {
		tail = tail[len(tail)-300:]
	}
	return fmt.Errorf("flatpak %s: %w: %s", what, err, tail)
}

// ensureRemote adds the Flathub remote once.
func (m *Manager) ensureRemote(ctx context.Context) error {
	url := m.URL
	if url == "" {
		url = RemoteURL
	}
	if out, err := m.fp(ctx, "remote-add", "--if-not-exists", Remote, url); err != nil {
		return fail("remote-add", out, err)
	}
	return nil
}

// Search lists apps of the remote whose id, name or summary contains q (at least two characters).
func (m *Manager) Search(ctx context.Context, q string) ([]App, error) {
	q = strings.ToLower(strings.TrimSpace(q))
	if len(q) < 2 || len(q) > 64 {
		return nil, &Refusal{"bad_query", "search for at least two characters"}
	}
	if why := m.Unavailable(); why != "" {
		return nil, &Refusal{"flatpak_not_installed", why}
	}
	if err := m.ensureRemote(ctx); err != nil {
		return nil, err
	}
	out, err := m.fp(ctx, "remote-ls", "--app", "--columns=application,name,description,version", Remote)
	if err != nil {
		return nil, fail("remote-ls", out, err)
	}
	have := map[string]bool{}
	if inst, err := m.Installed(ctx); err == nil {
		for _, a := range inst {
			have[a.ID] = true
		}
	}
	var hits []App
	for _, line := range strings.Split(string(out), "\n") {
		f := strings.Split(line, "\t")
		if len(f) < 2 || !ValidID(strings.TrimSpace(f[0])) {
			continue
		}
		a := App{ID: strings.TrimSpace(f[0]), Name: strings.TrimSpace(f[1]), Installed: have[strings.TrimSpace(f[0])]}
		if len(f) > 2 {
			a.Summary = strings.TrimSpace(f[2])
		}
		if len(f) > 3 {
			a.Version = strings.TrimSpace(f[3])
		}
		if strings.Contains(strings.ToLower(a.ID+" "+a.Name+" "+a.Summary), q) {
			hits = append(hits, a)
		}
	}
	rank := func(a App) int { // name starts with q, then name contains q, then the rest
		n := strings.ToLower(a.Name)
		if strings.HasPrefix(n, q) {
			return 0
		}
		if strings.Contains(n, q) {
			return 1
		}
		return 2
	}
	sort.SliceStable(hits, func(i, j int) bool { return rank(hits[i]) < rank(hits[j]) })
	if len(hits) > maxResults {
		hits = hits[:maxResults]
	}
	return hits, nil
}

func (m *Manager) now() time.Time {
	if m.Now != nil {
		return m.Now()
	}
	return time.Now()
}

func (m *Manager) forgetUpdates() {
	m.umu.Lock()
	m.upd, m.updAt = nil, time.Time{}
	m.umu.Unlock()
}

// updates is the set of application and runtime ids the remote has a newer build of, kept for updateTTL. A failed
// ask gives an empty set, kept for updateFailTTL.
func (m *Manager) updates(ctx context.Context) map[string]bool {
	m.umu.Lock()
	defer m.umu.Unlock()
	if m.upd != nil && m.now().Sub(m.updAt) < updateTTL {
		return m.upd
	}
	// No --app: runtimes are listed too, so a security update of a runtime alone shows up.
	// A short limit of its own: with no network this must not hold every caller for the 20-minute unit timeout.
	actx, cancel := context.WithTimeout(ctx, updateAskTimeout)
	defer cancel()
	o, err := m.fp(actx, "remote-ls", "--updates", "--columns=application", Remote)
	if err != nil {
		// Remember the failure briefly, so a box that is offline answers at once instead of waiting again.
		m.upd, m.updAt = map[string]bool{}, m.now().Add(updateFailTTL-updateTTL)
		return m.upd
	}
	upd := map[string]bool{}
	for _, l := range strings.Fields(string(o)) {
		upd[l] = true
	}
	m.upd, m.updAt = upd, m.now()
	return upd
}

// Installed lists the installed apps (not runtimes). An app has an update when the remote has a newer build of it or
// of its runtime ("flatpak update <app>" brings its runtime along).
func (m *Manager) Installed(ctx context.Context) ([]App, error) {
	out, err := m.fp(ctx, "list", "--app", "--columns=application,name,version,runtime")
	if err != nil {
		return nil, fail("list", out, err)
	}
	upd := m.updates(ctx)
	apps := []App{}
	for _, line := range strings.Split(string(out), "\n") {
		f := strings.Split(line, "\t")
		if len(f) < 2 || !ValidID(strings.TrimSpace(f[0])) {
			continue
		}
		a := App{ID: strings.TrimSpace(f[0]), Name: strings.TrimSpace(f[1]), Installed: true}
		a.Folder = m.Folder(a.ID)
		a.UpdateAvailable = upd[a.ID]
		if len(f) > 2 {
			a.Version = strings.TrimSpace(f[2])
		}
		if len(f) > 3 {
			rt, _, _ := strings.Cut(strings.TrimSpace(f[3]), "/")
			a.UpdateAvailable = a.UpdateAvailable || (rt != "" && upd[rt])
		}
		apps = append(apps, a)
	}
	return apps, nil
}

// cleanup removes runtimes nothing uses any more, so they do not pile up on /data. It is best effort.
func (m *Manager) cleanup(ctx context.Context) {
	_, _ = m.fp(ctx, "uninstall", "--unused", "--noninteractive", "--assumeyes")
}

func (m *Manager) isInstalled(ctx context.Context, id string) (bool, error) {
	apps, err := m.Installed(ctx)
	for _, a := range apps {
		if a.ID == id {
			return true, err
		}
	}
	return false, err
}

// sandbox makes the granted folder (in a unit that may chown, see Runner.Prepare) and writes the overrides.
func (m *Manager) sandbox(ctx context.Context, id string) error {
	if err := m.Run.Prepare(ctx, filepath.Join(m.FilesDir, id), m.Folder(id)); err != nil {
		return err
	}
	if out, err := m.fp(ctx, append([]string{"override"}, append(SandboxArgs(m.Folder(id)), id)...)...); err != nil {
		return fail("override", out, err)
	}
	return nil
}

// Install installs id from the remote and sandboxes it. An app whose sandbox could not be written is removed again:
// an app is never left installed with the permissions its own manifest asked for.
func (m *Manager) Install(ctx context.Context, id string) error {
	if err := m.ready(id); err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	defer m.forgetUpdates()
	if err := m.ensureRemote(ctx); err != nil {
		return err
	}
	if out, err := m.fp(ctx, "install", "--noninteractive", "--assumeyes", Remote, id); err != nil {
		return fail("install", out, err)
	}
	if err := m.sandbox(ctx, id); err != nil {
		_, _ = m.fp(ctx, "uninstall", "--noninteractive", "--assumeyes", id)
		m.cleanup(ctx)
		return fmt.Errorf("sandbox for %s, app removed again: %w", id, err)
	}
	return nil
}

// Update updates one installed app and writes its sandbox again.
func (m *Manager) Update(ctx context.Context, id string) error {
	if err := m.ready(id); err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	defer m.forgetUpdates()
	if ok, _ := m.isInstalled(ctx, id); !ok {
		return &Refusal{"not_installed", id + " is not installed"}
	}
	if out, err := m.fp(ctx, "update", "--noninteractive", "--assumeyes", id); err != nil {
		return fail("update", out, err)
	}
	m.cleanup(ctx)
	return m.sandbox(ctx, id)
}

// Remove uninstalls an app. Its granted folder stays: it holds the owner's own files (notes, documents).
func (m *Manager) Remove(ctx context.Context, id string) error {
	if err := m.ready(id); err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	defer m.forgetUpdates()
	if ok, _ := m.isInstalled(ctx, id); !ok {
		return &Refusal{"not_installed", id + " is not installed"}
	}
	if out, err := m.fp(ctx, "uninstall", "--noninteractive", "--assumeyes", id); err != nil {
		return fail("uninstall", out, err)
	}
	m.cleanup(ctx)
	return nil
}

// Launch tells the streaming runtime which app to run: onemind-desktop-session (apps/_bases/desktop) reads this
// file, and runs `flatpak run` for it on the session's own screen. The write is atomic.
func (m *Manager) Launch(ctx context.Context, id string) error {
	if err := m.ready(id); err != nil {
		return err
	}
	if ok, _ := m.isInstalled(ctx, id); !ok {
		return &Refusal{"not_installed", id + " is not installed"}
	}
	if err := os.MkdirAll(m.SessionDir, 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(m.SessionDir, ".launch-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.WriteString(id + "\n"); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Chmod(tmp.Name(), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), filepath.Join(m.SessionDir, "launch"))
}

// IsRefusal unwraps a *Refusal.
func IsRefusal(err error) (*Refusal, bool) {
	var r *Refusal
	return r, errors.As(err, &r)
}
