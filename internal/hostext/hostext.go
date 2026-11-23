// SPDX-License-Identifier: Apache-2.0

// Package hostext installs host extensions: plugin socket E3 (Foundation Report ch. 9, issue #186).
// A host extension is a systemd system extension (sysext: files under /usr) or configuration
// extension (confext: files under /etc) shipped as a signed disk image. The read-only OneMind image
// never changes; systemd overlays the extension on top and removes it again on refresh.
//
// Stage copies an image into a quarantine folder on /data, refuses anything that is not a raw
// verity-signed disk image (no directory trees), verifies the signature against the OneMind key set,
// checks the extension-release ID and level against the host, and only then moves the image into
// /var/lib/extensions or /var/lib/confexts and runs a refresh under a signed-only image policy.
// Remove deletes the image and refreshes, so nothing it added stays in /usr or /etc.
package hostext

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strings"
)

// Kind is the extension kind.
type Kind string

const (
	Sysext  Kind = "sysext"
	Confext Kind = "confext"
)

// ImagePolicy is passed to systemd on every refresh and read: only signed images may be used.
// Same string systemd itself applies to initrd extensions (systemd-sysext(8), --image-policy).
const ImagePolicy = "root=signed+absent:usr=signed+absent"

var (
	ErrExists   = errors.New("an extension with that name is already installed: remove it first")
	ErrNotFound = errors.New("no such extension")
	validName   = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`)
)

// RefusedError says why an image was not installed. Code is stable for scripts and --json.
type RefusedError struct{ Code, Reason string }

func (e *RefusedError) Error() string { return "refused (" + e.Code + "): " + e.Reason }

func refuse(code, f string, a ...any) error { return &RefusedError{code, fmt.Sprintf(f, a...)} }

// Config says where things live; the zero value of each field takes the box default.
type Config struct {
	Quarantine string   // staging folder on the data partition
	SysextDir  string   // /var/lib/extensions
	ConfextDir string   // /var/lib/confexts
	KeyDirs    []string // the OneMind key set, in the read-only image
	OSRelease  []string // host os-release, first readable wins
	Arch       string   // systemd architecture identifier (x86-64, arm64)
	// ReadRelease returns an image's extension-release fields; Run runs a host tool.
	ReadRelease func(ctx context.Context, image string, k Kind, name string) (map[string]string, error)
	Run         func(ctx context.Context, name string, args ...string) error
}

// Manager stages, lists and removes host extensions.
type Manager struct{ Config }

// Extension is one installed (or listed) image.
type Extension struct {
	Kind   Kind   `json:"kind"`
	Name   string `json:"name"`
	Size   int64  `json:"size_bytes"`
	Status string `json:"status"` // "verified", or why systemd would not be allowed to use it
	*Verified
}

// New fills in the box defaults.
func New(c Config) *Manager {
	def := func(s *string, v string) {
		if *s == "" {
			*s = v
		}
	}
	def(&c.Quarantine, "/data/onemind/hostext/quarantine")
	def(&c.SysextDir, "/var/lib/extensions")
	def(&c.ConfextDir, "/var/lib/confexts")
	def(&c.Arch, map[string]string{"amd64": "x86-64", "arm64": "arm64"}[runtime.GOARCH])
	if len(c.KeyDirs) == 0 {
		c.KeyDirs = []string{"/usr/lib/verity.d"}
	}
	if len(c.OSRelease) == 0 {
		c.OSRelease = []string{"/etc/os-release", "/usr/lib/os-release"}
	}
	if c.ReadRelease == nil {
		c.ReadRelease = DissectRelease
	}
	if c.Run == nil {
		c.Run = runTool
	}
	return &Manager{c}
}

func (m *Manager) dir(k Kind) string {
	if k == Confext {
		return m.ConfextDir
	}
	return m.SysextDir
}

func tool(k Kind) string { return "systemd-" + string(k) }

// DissectRelease reads the extension-release file out of a signed image with systemd-dissect,
// under the signed-only policy, so the kernel verifies the image while it is read.
func DissectRelease(ctx context.Context, image string, k Kind, name string) (map[string]string, error) {
	p := "/usr/lib/extension-release.d/extension-release." + name
	if k == Confext {
		p = "/etc/extension-release.d/extension-release." + name
	}
	out, err := exec.CommandContext(ctx, "systemd-dissect", "--image-policy="+ImagePolicy, "--copy-from", image, p, "-").Output()
	if err != nil {
		return nil, refuse("no_release", "cannot read %s from the image: %v", p, err)
	}
	return parseOSRelease(out), nil
}

func runTool(ctx context.Context, name string, args ...string) error {
	out, err := exec.CommandContext(ctx, name, args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("%s %s: %w: %s", name, strings.Join(args, " "), err, bytes.TrimSpace(out))
	}
	return nil
}

func (m *Manager) refresh(ctx context.Context, k Kind) error {
	return m.Run(ctx, tool(k), "refresh", "--image-policy="+ImagePolicy)
}

// copyFile copies src (never through a symlink: the opened file must be the one Lstat saw) into
// a new file dst, synced to disk.
func copyFile(src, dst string, mode os.FileMode) (err error) {
	lst, err := os.Lstat(src)
	if err != nil {
		return err
	}
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if st, err := in.Stat(); err != nil || !lst.Mode().IsRegular() || !os.SameFile(lst, st) {
		return refuse("not_image", "%s is not a regular file", filepath.Base(src))
	}
	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
	if err != nil {
		return err
	}
	defer func() {
		if cerr := out.Close(); err == nil {
			err = cerr
		}
	}()
	if _, err = io.Copy(out, in); err != nil {
		return err
	}
	return out.Sync()
}

// Stage verifies the image at src and, only if every check passes, installs it.
func (m *Manager) Stage(ctx context.Context, src string, k Kind) (*Extension, error) {
	base := filepath.Base(src)
	name, ok := strings.CutSuffix(base, ".raw")
	if !ok || !validName.MatchString(name) {
		return nil, refuse("bad_name", "%q: the file must be NAME.raw, NAME of letters, digits, '.', '_' and '-'", base)
	}
	st, err := os.Lstat(src)
	if err != nil {
		return nil, err
	}
	if !st.Mode().IsRegular() {
		return nil, refuse("not_image", "%s is a %s: only signed .raw disk images are accepted, never directories or links", base, st.Mode().Type())
	}
	final := filepath.Join(m.dir(k), base)
	if _, err := os.Lstat(final); err == nil {
		return nil, ErrExists
	}
	// Work on a private copy, so the bytes checked are the bytes installed.
	if err := os.MkdirAll(m.Quarantine, 0o700); err != nil {
		return nil, err
	}
	qdir, err := os.MkdirTemp(m.Quarantine, "stage-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(qdir)
	q := filepath.Join(qdir, base)
	if err := copyFile(src, q, 0o600); err != nil {
		return nil, err
	}
	keys, err := LoadKeys(m.KeyDirs)
	if err != nil {
		return nil, err
	}
	v, err := VerifyImage(q, m.Arch, keys)
	if err != nil {
		return nil, err
	}
	host, err := readHostRelease(m.OSRelease)
	if err != nil {
		return nil, fmt.Errorf("host os-release: %w", err)
	}
	rel, err := m.ReadRelease(ctx, q, k, name)
	if err != nil {
		return nil, err
	}
	if err := checkRelease(rel, host, k, m.Arch); err != nil {
		return nil, err
	}
	if err := os.MkdirAll(m.dir(k), 0o755); err != nil {
		return nil, err
	}
	tmp := filepath.Join(m.dir(k), "."+base+".staging")
	os.Remove(tmp)
	if err := copyFile(q, tmp, 0o644); err != nil {
		return nil, err
	}
	defer os.Remove(tmp)
	if err := os.Link(tmp, final); err != nil { // fails if a same-named image appeared meanwhile
		if os.IsExist(err) {
			return nil, ErrExists
		}
		return nil, err
	}
	if err := m.refresh(ctx, k); err != nil {
		os.Remove(final)
		_ = m.refresh(ctx, k)
		return nil, err
	}
	fi, _ := os.Stat(final)
	return &Extension{Kind: k, Name: name, Size: fi.Size(), Status: "verified", Verified: v}, nil
}

// List reports every entry systemd would look at in the two folders, verifying each image again.
func (m *Manager) List(ctx context.Context) ([]Extension, error) {
	keys, err := LoadKeys(m.KeyDirs)
	if err != nil {
		return nil, err
	}
	var out []Extension
	for _, k := range []Kind{Sysext, Confext} {
		es, err := os.ReadDir(m.dir(k))
		if err != nil && !os.IsNotExist(err) {
			return nil, err
		}
		for _, e := range es {
			if strings.HasPrefix(e.Name(), ".") && strings.HasSuffix(e.Name(), ".staging") {
				continue // Stage's own temporary copy
			}
			x := Extension{Kind: k, Name: strings.TrimSuffix(e.Name(), ".raw")}
			fi, err := os.Lstat(filepath.Join(m.dir(k), e.Name()))
			switch {
			case err != nil:
				x.Status = err.Error()
			case !fi.Mode().IsRegular() || !strings.HasSuffix(e.Name(), ".raw"):
				x.Status = "refused (not_image): not a signed .raw image; remove it by hand"
			default:
				x.Size = fi.Size()
				if x.Verified, err = VerifyImage(filepath.Join(m.dir(k), e.Name()), m.Arch, keys); err != nil {
					x.Status = err.Error()
				} else {
					x.Status = "verified"
				}
			}
			out = append(out, x)
		}
	}
	sort.SliceStable(out, func(i, j int) bool {
		return out[i].Kind < out[j].Kind || out[i].Kind == out[j].Kind && out[i].Name < out[j].Name
	})
	return out, nil
}

// Remove deletes an installed image and refreshes, so its files leave /usr or /etc.
func (m *Manager) Remove(ctx context.Context, name string, k Kind) error {
	name = strings.TrimSuffix(name, ".raw")
	if !validName.MatchString(name) {
		return refuse("bad_name", "%q is not an extension name", name)
	}
	p := filepath.Join(m.dir(k), name+".raw")
	st, err := os.Lstat(p)
	if os.IsNotExist(err) {
		return ErrNotFound
	}
	if err != nil {
		return err
	}
	if !st.Mode().IsRegular() {
		return refuse("not_image", "%s is not an image this tool installed", p)
	}
	if err := os.Remove(p); err != nil {
		return err
	}
	return m.refresh(ctx, k)
}
