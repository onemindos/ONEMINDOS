// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"
)

// Managed is what the gateway decides and the agent keeps between restarts
// (managed.json in the state directory): the destinations the owner approved
// and the installed apps with their volumes. It replaces the targets and
// apps of agent.json. Credentials never appear here, only the paths of the
// 0600 files the agent wrote them to.
type Managed struct {
	Targets []Target  `json:"targets"`
	Apps    []AppSpec `json:"apps"`
}

const (
	managedName      = "managed.json"
	targetSecretsDir = "target-secrets"
)

func readManaged(stateDir string) (*Managed, error) {
	b, err := os.ReadFile(filepath.Join(stateDir, managedName))
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	var m Managed
	if err := json.Unmarshal(b, &m); err != nil {
		return nil, fmt.Errorf("%s: %w", managedName, err)
	}
	return &m, nil
}

// TargetSpec is a destination as the gateway sends it: no file paths, and
// the secrets in a separate map that is written to files and dropped.
type TargetSpec struct {
	ID         string `json:"id"`
	Kind       string `json:"kind"`
	Name       string `json:"name"`
	Primary    bool   `json:"primary"`
	USBUUID    string `json:"usb_uuid,omitempty"`
	URL        string `json:"url,omitempty"`
	User       string `json:"user,omitempty"`
	AppendOnly bool   `json:"append_only,omitempty"`
	Endpoint   string `json:"endpoint,omitempty"`
	Bucket     string `json:"bucket,omitempty"`
	Prefix     string `json:"prefix,omitempty"`
	Region     string `json:"region,omitempty"`
}

// secretFields are the credential fields a destination kind takes; each is
// stored as <state_dir>/target-secrets/<target-id>.<field> with mode 0600.
// The directory holds nothing else: Configure deletes the files of removed
// destinations from it, so the device key must never live there.
var secretFields = map[string][]string{
	KindUSB:  nil,
	KindNode: {"password", "ca"},
	KindS3:   {"access_key", "secret_key"},
}

// ConfigureRequest is the backup.configure job.
type ConfigureRequest struct {
	Targets []TargetSpec                 `json:"targets"`
	Secrets map[string]map[string]string `json:"secrets,omitempty"`
}

// conf returns the current settings. Targets and apps change when the
// gateway reconfigures the agent; readers that do not hold the agent lock
// go through here.
func (a *Agent) conf() Config {
	a.cfgMu.RLock()
	defer a.cfgMu.RUnlock()
	return a.Cfg
}

// Configure replaces the destinations. It waits for any running job, writes
// new credentials, validates the result and only then saves and applies it.
// Destinations that are no longer listed keep their repositories untouched;
// only the credential files of removed targets are deleted.
func (a *Agent) Configure(req ConfigureRequest) (Config, error) {
	cur := a.conf()
	secretDir := filepath.Join(cur.StateDir, targetSecretsDir)
	var targets []Target
	keep := map[string]bool{}
	for _, s := range req.Targets {
		if !tagValueRe.MatchString(s.ID) {
			return cur, fmt.Errorf("target id %q must be tag-safe", s.ID)
		}
		fields, known := secretFields[s.Kind]
		if !known {
			return cur, fmt.Errorf("target %s: kind must be usb, node or s3", s.ID)
		}
		t := Target{ID: s.ID, Kind: s.Kind, Name: s.Name, Primary: s.Primary, USBUUID: s.USBUUID, URL: s.URL,
			User: s.User, AppendOnly: s.AppendOnly, Endpoint: s.Endpoint, Bucket: s.Bucket, Prefix: s.Prefix, Region: s.Region}
		for _, f := range fields {
			p := filepath.Join(secretDir, s.ID+"."+f)
			keep[p] = true
			switch f {
			case "password":
				t.PasswordFile = p
			case "ca":
				t.CAFile = p
			case "access_key":
				t.AccessKeyFile = p
			case "secret_key":
				t.SecretKeyFile = p
			}
		}
		targets = append(targets, t)
	}
	next := cur
	next.Targets = targets
	// Write the new credentials first so validation and the first run see them.
	for id, kv := range req.Secrets {
		for f, v := range kv {
			p := filepath.Join(secretDir, id+"."+f)
			if !keep[p] {
				return cur, fmt.Errorf("secret %s.%s does not belong to a listed target", id, f)
			}
			if v == "" {
				return cur, fmt.Errorf("secret %s.%s is empty", id, f)
			}
			if err := writeFileAtomic(p, []byte(v+"\n"), 0o600); err != nil {
				return cur, err
			}
		}
	}
	for i := range next.Targets {
		t := &next.Targets[i]
		for _, p := range []string{t.PasswordFile, t.AccessKeyFile, t.SecretKeyFile} {
			if p == "" {
				continue
			}
			if _, err := os.Stat(p); err != nil {
				return cur, fmt.Errorf("target %s: credentials were not provided", t.ID)
			}
		}
		if t.CAFile != "" {
			if _, err := os.Stat(t.CAFile); err != nil {
				t.CAFile = "" // optional: system roots are used
			}
		}
	}
	if err := next.Validate(); err != nil {
		return cur, err
	}
	if err := a.saveManaged(next); err != nil {
		return cur, err
	}
	if entries, err := os.ReadDir(secretDir); err == nil {
		for _, e := range entries {
			if p := filepath.Join(secretDir, e.Name()); !keep[p] {
				_ = os.Remove(p)
			}
		}
	}
	a.cfgMu.Lock()
	a.Cfg.Targets = next.Targets
	a.cfgMu.Unlock()
	return next, nil
}

// SetApps replaces the app list the gateway manages. Apps from the gateway
// may only name volumes, never host paths.
func (a *Agent) SetApps(apps []AppSpec) error {
	for _, s := range apps {
		if len(s.Paths) > 0 || len(s.SQLite) > 0 {
			return fmt.Errorf("app %q: host paths are not accepted from the gateway, only volumes", s.ID)
		}
	}
	next := a.conf()
	next.Units.Apps = apps
	if err := next.Validate(); err != nil {
		return err
	}
	if err := a.saveManaged(next); err != nil {
		return err
	}
	a.cfgMu.Lock()
	a.Cfg.Units.Apps = apps
	a.cfgMu.Unlock()
	return nil
}

func (a *Agent) saveManaged(c Config) error {
	b, err := json.MarshalIndent(Managed{Targets: c.Targets, Apps: c.Units.Apps}, "", "  ")
	if err != nil {
		return err
	}
	return writeFileAtomic(filepath.Join(c.StateDir, managedName), b, 0o600)
}

// k8sNameRe is a DNS-1123 subdomain (PVC, namespace and PV names).
var k8sNameRe = regexp.MustCompile(`^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$`)

func (v VolumeRef) validate() error {
	for name, s := range map[string]string{"namespace": v.Namespace, "claim": v.Claim, "volume": v.Volume} {
		if !k8sNameRe.MatchString(s) || strings.Contains(s, "_") {
			return fmt.Errorf("volume %s %q is not a Kubernetes name", name, s)
		}
	}
	return nil
}

// suffix is the part of the folder name that survives a new PersistentVolume.
func (v VolumeRef) suffix() string { return "_" + v.Namespace + "_" + v.Claim }

func (f VolumeFile) validate() error {
	if err := f.VolumeRef.validate(); err != nil {
		return err
	}
	p := path.Clean(f.Path)
	if f.Path == "" || path.IsAbs(f.Path) || p != f.Path || p == "." || strings.HasPrefix(p, "../") || p == ".." {
		return fmt.Errorf("volume file path %q must be a clean relative path", f.Path)
	}
	return nil
}

func (s AppSpec) validateVolumes() error {
	for _, v := range s.Volumes {
		if err := v.validate(); err != nil {
			return err
		}
	}
	for _, f := range append(append([]VolumeFile{}, s.Files...), s.VolumeSQLite...) {
		if err := f.validate(); err != nil {
			return err
		}
	}
	for _, e := range s.Excludes {
		if strings.HasPrefix(e, "/") || strings.Contains(e, "..") {
			return fmt.Errorf("exclude %q must be a relative pattern", e)
		}
	}
	return nil
}

// volumeDir finds the volume's folder under the storage roots: the first
// existing real directory <root>/<volume>_<namespace>_<claim>. When none
// exists it returns the path under the first root, so the unit fails with
// "no such file" instead of backing up something else.
func volumeDir(roots []string, v VolumeRef) string {
	name := v.Volume + v.suffix()
	for _, r := range roots {
		p := filepath.Join(r, name)
		if fi, err := os.Lstat(p); err == nil && fi.IsDir() {
			return p
		}
	}
	if len(roots) == 0 {
		return filepath.Join(string(filepath.Separator), "nonexistent-storage-root", name)
	}
	return filepath.Join(roots[0], name)
}

// regularFileInside requires p to be a regular file reached from root
// without any symlink: the resolved path must be exactly root's resolved
// path plus p's relative part. An app controls everything inside its
// volume, so a symlink there would point this root process at host files.
func regularFileInside(root, p string) error {
	rel, err := filepath.Rel(root, p)
	if err != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return fmt.Errorf("%s is not inside %s", p, root)
	}
	realRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return err
	}
	real, err := filepath.EvalSymlinks(p)
	if err != nil {
		return err
	}
	if real != filepath.Join(realRoot, rel) {
		return fmt.Errorf("%s goes through a symlink; refusing to open it", rel)
	}
	fi, err := os.Lstat(real)
	if err != nil {
		return err
	}
	if !fi.Mode().IsRegular() {
		return fmt.Errorf("%s is not a regular file", rel)
	}
	return nil
}

func volumeFilePath(roots []string, f VolumeFile) string {
	return filepath.Join(volumeDir(roots, f.VolumeRef), filepath.FromSlash(f.Path))
}

// managedApp returns the gateway's spec of app id.
func (a *Agent) managedApp(id string) (AppSpec, bool) {
	for _, s := range a.conf().Units.Apps {
		if s.ID == id {
			return s, true
		}
	}
	return AppSpec{}, false
}
