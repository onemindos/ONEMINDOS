// SPDX-License-Identifier: Apache-2.0

package update

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

// The signed Market catalog channel (PLAN gap 6, docs/learning in the PR).
//
// Why: the Market catalog (apps/*) used to ship only inside the read-only OS image, so a new
// app reached a box with the next OS update. Here the catalog is its own small TUF repository
// (own root.json in the image, own keys): a tarball `catalog/catalog-<version>.tar.gz` whose
// length and sha256 are signed in targets.json. The box fetches it into /data, verifies it with
// the same machinery as the OS updater, unpacks it into a private directory and only then swaps
// one symlink. The gateway reads the newest verified catalog and falls back to the image's own.
//
// Layout under StateDir (default /data/onemind/catalog):
//
//	current              symlink -> releases/<version> (swapped atomically)
//	current.json         {"version","sha256","applied_at"} of the active release
//	releases/<version>/  apps/<id>/onemind.app.yaml ... (what the gateway reads)
//	incoming/            verified tarballs, deleted after unpacking
//	tuf/catalog/         go-tuf trusted metadata (rollback and freeze protection)
const (
	catalogTargetDir = "catalog"
	// Hard limits on what a signed bundle may unpack to. A key compromise should not also
	// let the publisher fill the disk of every box.
	catalogMaxBundle = 64 << 20
	catalogMaxFile   = 8 << 20
	catalogMaxTotal  = 256 << 20
	catalogMaxFiles  = 20000
	catalogKeep      = 2 // newest releases kept (the active one and one to fall back to)
)

var (
	catalogNameRE    = regexp.MustCompile(`^catalog-([0-9]+(\.[0-9]+)*)\.tar\.gz$`)
	catalogVersionRE = regexp.MustCompile(`^[0-9]+(\.[0-9]+)*$`)
	catalogEntryRE   = regexp.MustCompile(`^apps/[a-z0-9][a-z0-9-]{0,58}(/[A-Za-z0-9._@+=-]+)+$`)
)

// CatalogActive is current.json.
type CatalogActive struct {
	Version   string `json:"version"`
	SHA256    string `json:"sha256"`
	AppliedAt string `json:"applied_at"`
}

// CatalogResult is what a sync did.
type CatalogResult struct {
	// Decision is "updated" or "up-to-date".
	Decision string `json:"decision"`
	Version  string `json:"version"`
	Apps     int    `json:"apps"`
}

// CatalogStatus reads current.json; a zero value (and no error) means no channel catalog yet,
// so the gateway uses the image's catalog only.
func CatalogStatus(c *Config) (CatalogActive, error) {
	var a CatalogActive
	b, err := os.ReadFile(filepath.Join(c.StateDir, "current.json"))
	if errors.Is(err, os.ErrNotExist) {
		return a, nil
	}
	if err != nil {
		return a, err
	}
	return a, json.Unmarshal(b, &a)
}

// SyncCatalog checks the catalog channel and, if a newer verified catalog exists, installs it.
// Nothing is activated unless the TUF metadata verified, the tarball matched its signed length
// and sha256, every entry passed the unpack rules and the version is newer than the active one.
func SyncCatalog(ctx context.Context, c *Config, hc *http.Client, now time.Time) (*CatalogResult, error) {
	if c.Channel != ChannelCatalog {
		return nil, fmt.Errorf("not a catalog config (channel %q)", c.Channel)
	}
	if err := os.MkdirAll(c.StateDir, 0o755); err != nil {
		return nil, err
	}
	idx, err := fetchIndex(c, hc, time.Time{})
	if err != nil {
		return nil, err
	}
	best, bestV := pickCatalog(idx)
	active, err := CatalogStatus(c)
	if err != nil {
		return nil, fmt.Errorf("current.json: %w", err)
	}
	if best == nil {
		return nil, errors.New("the catalog channel lists no catalog bundle")
	}
	if active.Version != "" {
		cmp, err := compareVersions(bestV, active.Version)
		if err != nil {
			return nil, err
		}
		if cmp <= 0 { // same or older: rollback to an old signed catalog is refused
			return &CatalogResult{Decision: "up-to-date", Version: active.Version}, nil
		}
	}
	if best.Length <= 0 || best.Length > catalogMaxBundle {
		return nil, fmt.Errorf("catalog %s: signed length %d is outside 1..%d bytes", bestV, best.Length, catalogMaxBundle)
	}
	incoming := filepath.Join(c.StateDir, "incoming")
	file, err := download(ctx, hc, downloadURL(c, idx, best), incoming, best, nil)
	if err != nil {
		return nil, err
	}
	defer os.Remove(file)
	releases := filepath.Join(c.StateDir, "releases")
	if err := os.MkdirAll(releases, 0o755); err != nil {
		return nil, err
	}
	stage, err := os.MkdirTemp(releases, ".unpack-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(stage) // no-op after the rename
	n, err := unpackCatalog(file, stage)
	if err != nil {
		return nil, fmt.Errorf("catalog %s refused: %w", bestV, err)
	}
	final := filepath.Join(releases, bestV)
	if err := os.RemoveAll(final); err != nil {
		return nil, err
	}
	if err := os.Rename(stage, final); err != nil {
		return nil, err
	}
	if err := swapSymlink(filepath.Join(c.StateDir, "current"), filepath.Join("releases", bestV)); err != nil {
		return nil, err
	}
	rec, _ := json.Marshal(CatalogActive{Version: bestV, SHA256: best.Hashes["sha256"], AppliedAt: now.UTC().Format(time.RFC3339)})
	if err := writeFileAtomic(filepath.Join(c.StateDir, "current.json"), rec); err != nil {
		return nil, err
	}
	pruneReleases(releases, bestV)
	return &CatalogResult{Decision: "updated", Version: bestV, Apps: n}, nil
}

// pickCatalog returns the newest `catalog/catalog-<version>.tar.gz` target whose signed custom
// metadata version agrees with its file name (the name alone is not trusted).
func pickCatalog(idx *Index) (*Target, string) {
	var best *Target
	var bestV string
	for i := range idx.Targets {
		t := &idx.Targets[i]
		if path.Dir(t.Path) != catalogTargetDir {
			continue
		}
		m := catalogNameRE.FindStringSubmatch(path.Base(t.Path))
		if m == nil || t.Meta.Version != m[1] || t.Hashes["sha256"] == "" {
			continue
		}
		if best != nil {
			if cmp, err := compareVersions(m[1], bestV); err != nil || cmp <= 0 {
				continue
			}
		}
		best, bestV = t, m[1]
	}
	return best, bestV
}

// unpackCatalog extracts the verified tarball into dir and returns how many apps it holds.
// Only regular files under apps/<id>/ are allowed: no links, devices, absolute or .. paths,
// no oversize files, no duplicates. The tarball is already signed; these rules bound the damage
// of a signing mistake and keep the unpacker simple to audit.
func unpackCatalog(file, dir string) (int, error) {
	f, err := os.Open(file)
	if err != nil {
		return 0, err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return 0, err
	}
	tr := tar.NewReader(gz)
	seen := map[string]bool{}
	apps := map[string]bool{}
	var total int64
	for {
		h, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return 0, err
		}
		name := strings.TrimSuffix(h.Name, "/")
		if h.Typeflag == tar.TypeDir {
			if name != "apps" && !strings.HasPrefix(name, "apps/") || path.Clean(name) != name {
				return 0, fmt.Errorf("directory %q is outside apps/", h.Name)
			}
			continue
		}
		if h.Typeflag != tar.TypeReg {
			return 0, fmt.Errorf("%q is not a regular file", h.Name)
		}
		if !catalogEntryRE.MatchString(h.Name) || path.Clean(h.Name) != h.Name {
			return 0, fmt.Errorf("file name %q is not allowed", h.Name)
		}
		if seen[h.Name] {
			return 0, fmt.Errorf("duplicate entry %q", h.Name)
		}
		if seen[h.Name] = true; len(seen) > catalogMaxFiles {
			return 0, errors.New("too many files")
		}
		if h.Size < 0 || h.Size > catalogMaxFile {
			return 0, fmt.Errorf("%q is too large", h.Name)
		}
		if total += h.Size; total > catalogMaxTotal {
			return 0, errors.New("unpacked size is too large")
		}
		dst := filepath.Join(dir, filepath.FromSlash(h.Name))
		if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
			return 0, err
		}
		out, err := os.OpenFile(dst, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
		if err != nil {
			return 0, err
		}
		n, err := io.Copy(out, io.LimitReader(tr, h.Size+1))
		if cerr := out.Close(); err == nil {
			err = cerr
		}
		if err != nil {
			return 0, err
		}
		if n != h.Size {
			return 0, fmt.Errorf("%q is larger than its header says", h.Name)
		}
		if parts := strings.Split(h.Name, "/"); len(parts) == 3 && parts[2] == "onemind.app.yaml" {
			apps[parts[1]] = true
		}
	}
	if len(apps) == 0 {
		return 0, errors.New("no app (apps/<id>/onemind.app.yaml) inside")
	}
	for _, id := range sortedKeys(seen) { // every app folder must carry its manifest
		if id2 := strings.Split(id, "/")[1]; !apps[id2] {
			return 0, fmt.Errorf("apps/%s has no onemind.app.yaml", id2)
		}
	}
	return len(apps), nil
}

func sortedKeys(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// swapSymlink points link at target atomically (rename over the old link).
func swapSymlink(link, target string) error {
	tmp := link + ".new"
	_ = os.Remove(tmp)
	if err := os.Symlink(target, tmp); err != nil {
		return err
	}
	return os.Rename(tmp, link)
}

func writeFileAtomic(p string, b []byte) error {
	tmp := p + ".new"
	if err := os.WriteFile(tmp, b, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, p)
}

// pruneReleases keeps the active release and the newest others, up to catalogKeep in all.
func pruneReleases(dir, active string) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	var olds []string
	for _, e := range ents {
		if e.IsDir() && e.Name() != active && catalogVersionRE.MatchString(e.Name()) {
			olds = append(olds, e.Name())
		}
	}
	sort.Slice(olds, func(i, j int) bool { c, _ := compareVersions(olds[i], olds[j]); return c > 0 })
	for i, name := range olds {
		if i >= catalogKeep-1 {
			_ = os.RemoveAll(filepath.Join(dir, name))
		}
	}
}
