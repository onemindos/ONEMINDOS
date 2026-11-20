// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"strings"
)

// The content tier (BAK-03, REC-NOMAD-07). An app's manifest may mark large,
// re-downloadable content (offline libraries, map archives, model files) with
// spec.backup.content patterns. The gateway leaves it out of the app's
// snapshots (as excludes) until the owner switches the tier on for that app,
// and the snapshot carries a content=included|excluded tag so a restore can
// say whether the content comes back or is downloaded again.
//
// Before the owner switches it on, the gateway asks for the size with the
// backup.content.size job: the agent walks the app's volumes (read only,
// never following a symlink) and adds up the regular files a pattern matches.

// Content tier values of AppSpec.Content and the snapshot tag.
const (
	ContentIncluded = "included"
	ContentExcluded = "excluded"
)

// ContentSizeApp is one app of a backup.content.size job.
type ContentSizeApp struct {
	ID       string      `json:"id"`
	Volumes  []VolumeRef `json:"volumes"`
	Patterns []string    `json:"patterns"`
}

// ContentSize is what the content of one app weighs on this node.
type ContentSize struct {
	ID    string `json:"id"`
	Bytes int64  `json:"bytes"`
	Files int    `json:"files"`
	// Missing lists volumes whose folder is not on this node (nothing counted).
	Missing []string `json:"missing,omitempty"`
}

func validContentPattern(p string) error {
	if p == "" || strings.HasPrefix(p, "/") || strings.Contains(p, "..") || strings.Contains(p, "**") {
		return fmt.Errorf("content pattern %q must be a relative pattern without '..' or '**'", p)
	}
	if _, err := path.Match(p, ""); err != nil {
		return fmt.Errorf("content pattern %q: %w", p, err)
	}
	return nil
}

// patternMatch reports whether slash path p is matched by one of the
// relative patterns, the way restic reads a relative --exclude: the pattern
// may start at any folder, and a matched folder takes everything inside it.
// Each part of the pattern is a path.Match glob for one path element.
func patternMatch(patterns []string, p string) bool {
	comps := strings.Split(strings.Trim(filepath.ToSlash(p), "/"), "/")
	for _, pat := range patterns {
		parts := strings.Split(path.Clean(pat), "/")
		for end := len(parts); end <= len(comps); end++ {
			ok := true
			for i, part := range parts {
				if m, err := path.Match(part, comps[end-len(parts)+i]); err != nil || !m {
					ok = false
					break
				}
			}
			if ok {
				return true
			}
		}
	}
	return false
}

// ContentSize adds up, per app, the regular files the app's content patterns
// match in its volumes. It only reads.
func (a *Agent) ContentSize(ctx context.Context, apps []ContentSizeApp) ([]ContentSize, error) {
	if len(apps) > 256 {
		return nil, errors.New("at most 256 apps per job")
	}
	for _, app := range apps {
		if !tagValueRe.MatchString(app.ID) {
			return nil, fmt.Errorf("app id %q must be tag-safe", app.ID)
		}
		if len(app.Patterns) == 0 || len(app.Patterns) > 64 {
			return nil, fmt.Errorf("app %q: 1-64 content patterns", app.ID)
		}
		for _, p := range app.Patterns {
			if err := validContentPattern(p); err != nil {
				return nil, err
			}
		}
		for _, v := range app.Volumes {
			if err := v.validate(); err != nil {
				return nil, err
			}
		}
	}
	roots := a.conf().StorageRoots
	out := make([]ContentSize, 0, len(apps))
	for _, app := range apps {
		res := ContentSize{ID: app.ID}
		for _, v := range app.Volumes {
			dir := volumeDir(roots, v)
			if fi, err := os.Lstat(dir); err != nil || !fi.IsDir() {
				res.Missing = append(res.Missing, v.Namespace+"/"+v.Claim)
				continue
			}
			err := filepath.WalkDir(dir, func(p string, d fs.DirEntry, err error) error {
				if err != nil {
					return nil // an unreadable corner is not counted, not fatal
				}
				if err := ctx.Err(); err != nil {
					return err
				}
				if !d.Type().IsRegular() {
					return nil // folders, and symlinks are never followed
				}
				rel, err := filepath.Rel(dir, p)
				if err != nil || !patternMatch(app.Patterns, rel) {
					return nil
				}
				fi, err := d.Info()
				if err != nil {
					return nil
				}
				res.Bytes += fi.Size()
				res.Files++
				return nil
			})
			if err != nil {
				return nil, err
			}
		}
		out = append(out, res)
	}
	return out, nil
}
