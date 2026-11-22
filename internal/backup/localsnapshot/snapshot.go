// SPDX-License-Identifier: Apache-2.0

// Package localsnapshot implements BAK-04's opt-in local version schedule.
// Snapshots share the source disk: restic remains the off-box backup layer.
package localsnapshot

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
)

const DefaultConfig = "/data/onemind/snapshots.json"

type Config struct {
	Source    string `json:"source"`
	Directory string `json:"directory"`
	Hourly    int    `json:"hourly"`
	Daily     int    `json:"daily"`
}

// Load accepts a private administrator-owned configuration, never gateway input.
func Load(path string) (Config, error) {
	var c Config
	if err := protected(filepath.Dir(path)); err != nil {
		return c, err
	}
	fi, err := os.Lstat(path)
	if err != nil {
		return c, err
	}
	if !fi.Mode().IsRegular() || fi.Mode().Perm() != 0600 || !owned(fi) {
		return c, fmt.Errorf("snapshot config must be an owned regular file with mode 0600")
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	err = json.Unmarshal(b, &c)
	if err == nil && (c.Hourly < 1 || c.Hourly > 168 || c.Daily < 1 || c.Daily > 366) {
		err = fmt.Errorf("snapshot retention requires hourly 1..168 and daily 1..366")
	}
	return c, err
}

type Version struct {
	ID      string    `json:"id"`
	Cadence string    `json:"cadence"`
	TakenAt time.Time `json:"taken_at"`
}

type Manager struct {
	Config Config
	Runner storage.Runner
}

var managed = regexp.MustCompile(`^(hourly|daily)-(\d{8}T\d{6}Z)$`)

func (m Manager) command(ctx context.Context, args ...string) (string, error) {
	r := m.Runner
	if r == nil {
		r = storage.ExecRunner{}
	}
	b, code, err := r.Run(ctx, "btrfs", args...)
	if err != nil {
		return "", err
	}
	if code != 0 {
		return "", fmt.Errorf("btrfs %s failed (exit %d)", strings.Join(args[:2], " "), code)
	}
	return string(b), nil
}

func field(text, name string) string {
	for _, line := range strings.Split(text, "\n") {
		k, v, ok := strings.Cut(strings.TrimSpace(line), ":")
		if ok && k == name {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

// Paths must be provisioned beforehand. Never create, convert or format a source.
// Protected ancestors prevent a member swapping a path while btrfs opens it.
func protected(path string) error {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return fmt.Errorf("snapshot paths must be absolute and clean")
	}
	for p := path; ; p = filepath.Dir(p) {
		fi, err := os.Lstat(p)
		if err != nil {
			return err
		}
		if !fi.IsDir() || !owned(fi) || fi.Mode().Perm()&0022 != 0 {
			return fmt.Errorf("snapshot path needs owned, non-writable directory ancestors: %s", p)
		}
		if p == "/" {
			return nil
		}
	}
}

// directoryMode allows 0700, or 0750 so the gateway (group onemind, read-only) can show a member
// the previous versions of their own files. Nobody but root may write, and others get nothing.
func directoryMode(perm os.FileMode) bool {
	return perm == 0700 || perm == 0750
}

func (m Manager) validate(ctx context.Context) (string, error) {
	c := m.Config
	for _, p := range []string{c.Source, c.Directory} {
		if err := protected(p); err != nil {
			return "", err
		}
	}
	if c.Source == "/" || c.Source == c.Directory || strings.HasPrefix(c.Directory, c.Source+"/") || strings.HasPrefix(c.Source, c.Directory+"/") {
		return "", fmt.Errorf("source and snapshot directory must be disjoint")
	}
	fi, _ := os.Stat(c.Directory)
	if !directoryMode(fi.Mode().Perm()) {
		return "", fmt.Errorf("snapshot directory must have mode 0700 or 0750")
	}
	s, err := m.command(ctx, "subvolume", "show", c.Source)
	if err != nil {
		return "", fmt.Errorf("source must already be a btrfs subvolume: %w", err)
	}
	uuid := field(s, "UUID")
	if uuid == "" || uuid == "-" {
		return "", fmt.Errorf("source UUID missing")
	}
	// btrfs snapshots omit nested subvolumes; refusing them avoids silent data loss.
	nested, err := m.command(ctx, "subvolume", "list", "-o", c.Source)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(nested) != "" {
		return "", fmt.Errorf("nested subvolumes need separate snapshot schedules")
	}
	return uuid, nil
}

func (m Manager) list(ctx context.Context, uuid string) ([]Version, error) {
	entries, err := os.ReadDir(m.Config.Directory)
	if err != nil {
		return nil, err
	}
	versions := []Version{}
	for _, e := range entries {
		parts := managed.FindStringSubmatch(e.Name())
		if parts == nil {
			continue
		} // Never prune other tools' or manual snapshots.
		t, err := time.Parse("20060102T150405Z", parts[2])
		if err != nil {
			return nil, err
		}
		if !e.IsDir() {
			return nil, fmt.Errorf("invalid snapshot entry %s", e.Name())
		}
		p := filepath.Join(m.Config.Directory, e.Name())
		s, err := m.command(ctx, "subvolume", "show", p)
		if err != nil {
			return nil, err
		}
		ro, err := m.command(ctx, "property", "get", "-ts", p, "ro")
		if err != nil {
			return nil, err
		}
		if field(s, "Parent UUID") != uuid || strings.TrimSpace(ro) != "ro=true" {
			return nil, fmt.Errorf("snapshot %s has wrong source or is writable", e.Name())
		}
		versions = append(versions, Version{e.Name(), parts[1], t.UTC()})
	}
	sort.Slice(versions, func(i, j int) bool { return versions[i].ID > versions[j].ID })
	return versions, nil
}

func (m Manager) List(ctx context.Context) ([]Version, error) {
	uuid, err := m.validate(ctx)
	if err != nil {
		return nil, err
	}
	return m.list(ctx, uuid)
}

// Tick catches up once per cadence after downtime. Creation must succeed before
// pruning, and only read-only snapshots with this source's Parent UUID qualify.
func (m Manager) Tick(ctx context.Context, now time.Time) error {
	c := m.Config
	if c.Hourly < 1 || c.Hourly > 168 || c.Daily < 1 || c.Daily > 366 {
		return fmt.Errorf("invalid retention")
	}
	uuid, err := m.validate(ctx)
	if err != nil {
		return err
	}
	unlock, err := lock(filepath.Join(c.Directory, ".schedule.lock"))
	if err != nil {
		return err
	}
	defer unlock()
	versions, err := m.list(ctx, uuid)
	if err != nil {
		return err
	}
	now = now.UTC()
	for _, cadence := range []string{"hourly", "daily"} {
		period := now.Truncate(time.Hour)
		if cadence == "daily" {
			period = now.Truncate(24 * time.Hour)
		}
		due := true
		for _, v := range versions {
			if v.Cadence == cadence && !v.TakenAt.Before(period) {
				due = false
			}
		}
		if due {
			// Timestamp actual creation, not the missed schedule's nominal time.
			id := cadence + "-" + now.Format("20060102T150405Z")
			if _, err = m.command(ctx, "subvolume", "snapshot", "-r", c.Source, filepath.Join(c.Directory, id)); err != nil {
				return err
			}
		}
	}
	// Commit the new restore points before any older ones can be deleted.
	if _, err = m.command(ctx, "filesystem", "sync", c.Directory); err != nil {
		return err
	}
	versions, err = m.list(ctx, uuid)
	if err != nil {
		return err
	}
	counts := map[string]int{}
	for _, v := range versions {
		counts[v.Cadence]++
		keep := c.Hourly
		if v.Cadence == "daily" {
			keep = c.Daily
		}
		if counts[v.Cadence] > keep {
			if _, err = m.command(ctx, "subvolume", "delete", filepath.Join(c.Directory, v.ID)); err != nil {
				return err
			}
		}
	}
	return nil
}
