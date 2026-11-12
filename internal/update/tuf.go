// SPDX-License-Identifier: Apache-2.0

package update

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/theupdateframework/go-tuf/v2/metadata"
	"github.com/theupdateframework/go-tuf/v2/metadata/config"
	"github.com/theupdateframework/go-tuf/v2/metadata/fetcher"
	"github.com/theupdateframework/go-tuf/v2/metadata/updater"
)

// TargetMeta is the custom metadata of a release target (os/update/CHANNEL.md).
type TargetMeta struct {
	Board          string `json:"board"`
	Version        string `json:"version"`
	Compatible     string `json:"compatible"`
	MinFromVersion string `json:"min_from_version"`
	Security       bool   `json:"security"`
	// Kept opaque: the box only reports them; their shape belongs to the pipeline.
	BuiltFromSnapshot json.RawMessage `json:"built_from_snapshot,omitempty"`
	SBOM              json.RawMessage `json:"sbom,omitempty"`
	CVEReport         json.RawMessage `json:"cve_report,omitempty"`
}

// Target is one TUF-verified release bundle.
type Target struct {
	Path   string
	Length int64
	Hashes map[string]string // algorithm -> lowercase hex, from signed targets metadata
	Meta   TargetMeta
}

// Index is the verified content of a channel.
type Index struct {
	Targets            []Target
	ConsistentSnapshot bool
	TargetsExpires     time.Time
}

// fetchIndex runs the TUF client workflow (spec 1.0 §5) against the channel:
// root rotation from the image-shipped root, then timestamp, snapshot and
// targets, each checked for signatures, thresholds, versions (rollback) and
// expiry. refTime, when non-zero, replaces "now" (tests only).
func fetchIndex(c *Config, hc *http.Client, refTime time.Time) (*Index, error) {
	rootPath := filepath.Join(c.TUFRootDir, c.Channel, "root.json")
	root, err := os.ReadFile(rootPath)
	if err != nil {
		return nil, fmt.Errorf("trusted root: %w", err)
	}
	ucfg, err := config.New(c.URL, root)
	if err != nil {
		return nil, err
	}
	// The cache keeps the last trusted timestamp/snapshot/targets, which is
	// what gives rollback protection across checks. We always start from the
	// image's root and let the client walk N.root.json rotations, so a planted
	// root.json in /data cannot become the trust anchor.
	ucfg.LocalMetadataDir = filepath.Join(c.StateDir, "tuf", c.Channel)
	ucfg.LocalTargetsDir = filepath.Join(c.StateDir, "tuf", c.Channel, "targets-unused")
	f := fetcher.NewDefaultFetcher() // one try per request; the daemon retries next cycle
	f.SetHTTPClient(hc)
	ucfg.Fetcher = f
	up, err := updater.New(ucfg)
	if err != nil {
		return nil, err
	}
	if !refTime.IsZero() {
		up.UnsafeSetRefTime(refTime)
	}
	if err := up.Refresh(); err != nil {
		return nil, fmt.Errorf("tuf refresh: %w", err)
	}
	tm := up.GetTrustedMetadataSet()
	idx := &Index{ConsistentSnapshot: tm.Root.Signed.ConsistentSnapshot}
	if t := tm.Targets[metadata.TARGETS]; t != nil {
		idx.TargetsExpires = t.Signed.Expires
	}
	for p, tf := range up.GetTopLevelTargets() {
		t := Target{Path: p, Length: tf.Length, Hashes: map[string]string{}}
		for alg, h := range tf.Hashes {
			t.Hashes[alg] = hex.EncodeToString(h)
		}
		if tf.Custom != nil {
			if err := json.Unmarshal(*tf.Custom, &t.Meta); err != nil {
				return nil, fmt.Errorf("target %s: custom metadata: %w", p, err)
			}
		}
		idx.Targets = append(idx.Targets, t)
	}
	sort.Slice(idx.Targets, func(i, j int) bool { return idx.Targets[i].Path < idx.Targets[j].Path })
	return idx, nil
}

// Box is what this machine is and runs.
type Box struct {
	Board, Compatible, Version string
	// Marker is the gate's trial marker (<gate_dir>/pending, "<slot> <version>").
	MarkerPresent bool
	MarkerVersion string
}

// TrialPending: the gate is deciding on the booted slot (marker version = booted version).
func (b Box) TrialPending() bool { return b.MarkerPresent && b.MarkerVersion == b.Version }

// Skip records why a target was not chosen (for the decision log).
type Skip struct{ Path, Why string }

// Select returns the newest target this box may install, or nil.
func Select(c *Config, idx *Index, box Box, bad BadReleases) (*Target, []Skip) {
	var best *Target
	var skips []Skip
	for i := range idx.Targets {
		t := &idx.Targets[i]
		if why := applicable(c, t, box, bad); why != "" {
			skips = append(skips, Skip{t.Path, why})
			continue
		}
		if best == nil {
			best = t
		} else if cmp, _ := compareVersions(t.Meta.Version, best.Meta.Version); cmp > 0 {
			best = t
		}
	}
	return best, skips
}

func applicable(c *Config, t *Target, box Box, bad BadReleases) string {
	m := t.Meta
	switch {
	case !strings.HasSuffix(t.Path, ".raucb"):
		return "not a RAUC bundle"
	case m.Board != box.Board:
		return fmt.Sprintf("board %q != %q", m.Board, box.Board)
	case m.Compatible != box.Compatible:
		return fmt.Sprintf("compatible %q != %q", m.Compatible, box.Compatible)
	case t.Path != fmt.Sprintf("%s/%s/onemind-%s-%s.raucb", m.Board, m.Version, m.Board, m.Version):
		return "path does not match board/version metadata"
	case c.Channel == ChannelSecurity && !m.Security:
		return "not marked security on the security channel"
	}
	if cmp, err := compareVersions(m.Version, box.Version); err != nil {
		return err.Error()
	} else if cmp <= 0 {
		return "not newer than " + box.Version
	}
	if m.MinFromVersion != "" {
		if cmp, err := compareVersions(m.MinFromVersion, box.Version); err != nil {
			return "min_from_version: " + err.Error()
		} else if cmp > 0 {
			return "needs at least " + m.MinFromVersion
		}
	}
	if why := bad.Excluded(m.Version); why != "" {
		return why
	}
	return ""
}

// downloadURL is where the bundle for t is fetched from.
func downloadURL(c *Config, idx *Index, t *Target) string {
	name := path.Base(t.Path)
	sha := t.Hashes["sha256"]
	if strings.Contains(c.TargetsURL, "{") {
		return strings.NewReplacer("{path}", t.Path, "{board}", t.Meta.Board, "{version}", t.Meta.Version,
			"{name}", name, "{sha256}", sha).Replace(c.TargetsURL)
	}
	rel := t.Path
	if idx.ConsistentSnapshot && sha != "" { // TUF spec 5.7.3: <dir>/<hash>.<name>
		rel = path.Join(path.Dir(t.Path), sha+"."+name)
	}
	return strings.TrimRight(c.TargetsURL, "/") + "/" + rel
}
