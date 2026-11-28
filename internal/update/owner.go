// SPDX-License-Identifier: Apache-2.0

package update

import (
	"bufio"
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// OwnerFile is the owner's update settings (REL-02, #154): policy and window
// only, in update.conf's key = value format, kept in the state directory under
// /data because /etc/onemind/update.conf ships read-only with the image
// (CHANNEL.md §4: "owner changes are stored where the updater keeps writable
// state"). The host service writes it after the owner approved the change
// (os.update.settings); the updater and the heartbeat read it on every cycle,
// so a change counts from the next check without a restart.
const OwnerFile = "owner.conf"

// Settings sources.
const (
	SourceImage = "image" // the image's update.conf (default: notify, ask first; Z-02, founder 2026-11-28)
	SourceOwner = "owner" // the owner's choice, approved through the gateway
)

// OwnerPath is the owner settings file of this config.
func OwnerPath(c *Config) string { return filepath.Join(c.StateDir, OwnerFile) }

// OwnerSettings are what the owner may change.
type OwnerSettings struct {
	Policy Policy
	Window Window
}

// ParsePolicy accepts auto, notify or off.
func ParsePolicy(s string) (Policy, error) {
	switch p := Policy(s); p {
	case PolicyAuto, PolicyNotify, PolicyOff:
		return p, nil
	}
	return "", fmt.Errorf("policy must be auto, notify or off, got %q", s)
}

// ReadOwner reads the owner settings file. A missing file is (nil, nil): the
// image's settings apply. Both keys are required, so a half-written or
// hand-edited file never mixes the owner's policy with the image's window.
func ReadOwner(c *Config) (*OwnerSettings, error) {
	b, err := os.ReadFile(OwnerPath(c))
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	kv := map[string]string{}
	sc := bufio.NewScanner(bytes.NewReader(b))
	for n := 1; sc.Scan(); n++ {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			return nil, fmt.Errorf("%s line %d: want key = value", OwnerFile, n)
		}
		k = strings.TrimSpace(k)
		if k != "policy" && k != "window" {
			return nil, fmt.Errorf("%s line %d: only policy and window may be set here, not %q", OwnerFile, n, k)
		}
		if _, dup := kv[k]; dup {
			return nil, fmt.Errorf("%s line %d: %s set twice", OwnerFile, n, k)
		}
		kv[k] = strings.TrimSpace(v)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if kv["policy"] == "" || kv["window"] == "" {
		return nil, fmt.Errorf("%s: policy and window are both required", OwnerFile)
	}
	p, err := ParsePolicy(kv["policy"])
	if err != nil {
		return nil, fmt.Errorf("%s: %w", OwnerFile, err)
	}
	w, err := ParseWindow(kv["window"])
	if err != nil {
		return nil, fmt.Errorf("%s: window: %w", OwnerFile, err)
	}
	return &OwnerSettings{Policy: p, Window: w}, nil
}

// WriteOwner stores the owner settings durably: temp file, fsync, rename,
// fsync of the directory, so a power cut leaves the old file or the new one,
// never an empty one.
func WriteOwner(c *Config, s OwnerSettings) error {
	if _, err := ParsePolicy(string(s.Policy)); err != nil {
		return err
	}
	if err := os.MkdirAll(c.StateDir, 0o755); err != nil {
		return err
	}
	// The directory may predate this file with a looser mode: only root writes here.
	if err := os.Chmod(c.StateDir, 0o755); err != nil {
		return err
	}
	body := fmt.Sprintf("# Owner update settings (REL-02). Written by the host service after the owner approved\n"+
		"# os.update.settings; overrides policy and window of %s.\npolicy=%s\nwindow=%s\n", DefaultConfigPath, s.Policy, s.Window)
	path := OwnerPath(c)
	// CreateTemp opens a fresh random name with O_EXCL, so a planted file or symlink is never followed.
	f, err := os.CreateTemp(c.StateDir, OwnerFile+".tmp-*")
	if err != nil {
		return err
	}
	tmp := f.Name()
	ok := false
	defer func() {
		if !ok {
			os.Remove(tmp)
		}
	}()
	if err := f.Chmod(0o644); err != nil {
		f.Close()
		return err
	}
	if _, err := f.WriteString(body); err != nil {
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
	if err := os.Rename(tmp, path); err != nil {
		return err
	}
	ok = true
	d, err := os.Open(c.StateDir)
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}

// Effective returns the settings in force and where they come from: the
// owner's file when it is present and valid, else the image's. An unreadable
// or invalid owner file falls back to the image (ask first: notify) and
// is returned as err, so the caller logs it and the heartbeat reports it.
func (c *Config) Effective() (Policy, Window, string, error) {
	o, err := ReadOwner(c)
	if err != nil || o == nil {
		return c.Policy, c.Window, SourceImage, err
	}
	return o.Policy, o.Window, SourceOwner, nil
}
