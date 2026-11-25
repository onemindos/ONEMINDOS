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

// Runner runs `flatpak <args>` as root against the box's installation.
type Runner interface {
	Run(ctx context.Context, args ...string) ([]byte, error)
}

// SystemdRunner runs flatpak in a transient systemd unit. The host service is sandboxed tightly (no namespaces, no
// extra capabilities), which ostree checkouts need; so each call gets a unit of its own that can write only the
// two folders on /data it needs. The argument list is fixed here and in Manager: no caller text becomes an option.
type SystemdRunner struct{ Dir, FilesDir, SessionDir string }

// Run implements Runner.
func (s SystemdRunner) Run(ctx context.Context, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 20*time.Minute)
	defer cancel()
	pre := []string{"--quiet", "--wait", "--pipe", "--collect", "--service-type=exec",
		"-p", "ProtectSystem=strict", "-p", "PrivateTmp=yes", "-p", "ProtectHome=yes",
		"-p", "ReadWritePaths=" + s.Dir + " " + s.FilesDir, "-p", "Environment=HOME=" + s.Dir + "/home",
		"--", "/usr/bin/flatpak"}
	c := exec.CommandContext(ctx, "/usr/bin/systemd-run", append(pre, args...)...)
	var out bytes.Buffer
	c.Stdout, c.Stderr = &out, &out
	err := c.Run()
	return out.Bytes(), err
}

// Manager drives flatpak. One mutating call at a time.
type Manager struct {
	Run        Runner
	FilesDir   string // /data/onemind/desktop-apps: one granted folder per app
	SessionDir string // /data/onemind/desktop-session: the launch file the streaming runtime reads
	URL        string // the remote's .flatpakrepo (default RemoteURL; a test points it at a local repo)
	// Have reports whether a program is installed (default exec.LookPath); Chown is os.Chown by default.
	Have  func(string) bool
	Chown func(path string, uid, gid int) error

	mu sync.Mutex
}

// NewDefault is the box's manager.
func NewDefault() *Manager {
	const dir, files, session = "/data/onemind/flatpak", "/data/onemind/desktop-apps", "/data/onemind/desktop-session"
	return &Manager{Run: SystemdRunner{Dir: dir, FilesDir: files, SessionDir: session}, FilesDir: files, SessionDir: session}
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
// org.freedesktop.Flatpak is the portal that runs commands on the host, so it is closed too.
func SandboxArgs(folder string) []string {
	return []string{"--nofilesystem=host", "--nofilesystem=host-os", "--nofilesystem=host-etc", "--nofilesystem=home",
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

// Installed lists the installed apps (not runtimes), with whether the remote has an update for each.
func (m *Manager) Installed(ctx context.Context) ([]App, error) {
	out, err := m.fp(ctx, "list", "--app", "--columns=application,name,version")
	if err != nil {
		return nil, fail("list", out, err)
	}
	upd := map[string]bool{}
	if o, err := m.fp(ctx, "remote-ls", "--app", "--updates", "--columns=application", Remote); err == nil {
		for _, l := range strings.Fields(string(o)) {
			upd[l] = true
		}
	}
	apps := []App{}
	for _, line := range strings.Split(string(out), "\n") {
		f := strings.Split(line, "\t")
		if len(f) < 2 || !ValidID(strings.TrimSpace(f[0])) {
			continue
		}
		a := App{ID: strings.TrimSpace(f[0]), Name: strings.TrimSpace(f[1]), Installed: true}
		a.UpdateAvailable, a.Folder = upd[a.ID], m.Folder(a.ID)
		if len(f) > 2 {
			a.Version = strings.TrimSpace(f[2])
		}
		apps = append(apps, a)
	}
	return apps, nil
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

// sandbox makes the granted folder and writes the overrides. The folder belongs to the runtime's user.
func (m *Manager) sandbox(ctx context.Context, id string) error {
	folder := m.Folder(id)
	if err := os.MkdirAll(folder, 0o750); err != nil {
		return err
	}
	chown := m.Chown
	if chown == nil {
		chown = os.Chown
	}
	if err := chown(folder, DesktopUID, DesktopUID); err != nil {
		return err
	}
	if out, err := m.fp(ctx, append([]string{"override"}, append(SandboxArgs(folder), id)...)...); err != nil {
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
	if err := m.ensureRemote(ctx); err != nil {
		return err
	}
	if out, err := m.fp(ctx, "install", "--noninteractive", "--assumeyes", Remote, id); err != nil {
		return fail("install", out, err)
	}
	if err := m.sandbox(ctx, id); err != nil {
		_, _ = m.fp(ctx, "uninstall", "--noninteractive", "--assumeyes", id)
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
	if ok, _ := m.isInstalled(ctx, id); !ok {
		return &Refusal{"not_installed", id + " is not installed"}
	}
	if out, err := m.fp(ctx, "update", "--noninteractive", "--assumeyes", id); err != nil {
		return fail("update", out, err)
	}
	return m.sandbox(ctx, id)
}

// Remove uninstalls an app. Its granted folder stays: it holds the owner's own files (notes, documents).
func (m *Manager) Remove(ctx context.Context, id string) error {
	if err := m.ready(id); err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if ok, _ := m.isInstalled(ctx, id); !ok {
		return &Refusal{"not_installed", id + " is not installed"}
	}
	if out, err := m.fp(ctx, "uninstall", "--noninteractive", "--assumeyes", id); err != nil {
		return fail("uninstall", out, err)
	}
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
