// SPDX-License-Identifier: Apache-2.0

// Package verify checks plugin trust independently of packaging and approval.
package verify

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"time"

	"github.com/Masterminds/semver/v3"
	"github.com/theupdateframework/go-tuf/v2/metadata/config"
	"github.com/theupdateframework/go-tuf/v2/metadata/updater"
)

const revocationTarget = "plugins/revocations.json"
const maxRevocations = 1 << 20

var pluginID = regexp.MustCompile(`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`)
var digestID = regexp.MustCompile(`^sha256:[a-f0-9]{64}$`)

type Revocation struct {
	ID       string     `json:"id"`
	Versions string     `json:"versions,omitempty"`
	Digests  []string   `json:"digests,omitempty"`
	Action   string     `json:"action"`
	Tool     string     `json:"tool,omitempty"`
	Reason   string     `json:"reason"`
	Link     string     `json:"link,omitempty"`
	Since    *time.Time `json:"since,omitempty"`
}

type Revocations struct {
	Schema     string       `json:"schema"`
	Version    int64        `json:"version"`
	Expires    time.Time    `json:"expires"`
	Entries    []Revocation `json:"entries"`
	validUntil time.Time
}

// ValidUntil includes the earliest expiry in the authenticated TUF chain.
func (r *Revocations) ValidUntil() time.Time {
	if !r.validUntil.IsZero() && r.validUntil.Before(r.Expires) {
		return r.validUntil
	}
	return r.Expires
}

// TrustedRoot comes from the image/operator trust configuration, never an OCI
// artifact or publisher response. StateDir must be persistent and owner-owned.
type RevocationConfig struct {
	TrustedRoot                       []byte
	MetadataURL, TargetsURL, StateDir string
	HTTPClient                        *http.Client
}

func strictJSON(data []byte, value any) error {
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if err := d.Decode(value); err != nil {
		return err
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("trailing JSON data")
	}
	return nil
}

func parseRevocations(raw []byte, now time.Time) (*Revocations, error) {
	var r Revocations
	if len(raw) > maxRevocations {
		return nil, fmt.Errorf("revocation list too large")
	}
	if err := strictJSON(raw, &r); err != nil {
		return nil, fmt.Errorf("invalid revocation list: %w", err)
	}
	if r.Schema != "onemind.revocations/v1" || r.Version < 1 || !r.Expires.After(now) || r.Entries == nil || len(r.Entries) > 4096 {
		return nil, fmt.Errorf("invalid or expired revocation list")
	}
	for _, e := range r.Entries {
		if len(e.ID) > 59 || !pluginID.MatchString(e.ID) || len(e.Reason) == 0 || len(e.Reason) > 4096 || len(e.Versions) > 512 || len(e.Digests) > 1024 || len(e.Tool) > 128 || len(e.Link) > 2048 {
			return nil, fmt.Errorf("invalid revocation entry")
		}
		switch e.Action {
		case "delist", "disable", "remove":
			if e.Tool != "" {
				return nil, fmt.Errorf("unexpected tool on plugin revocation")
			}
		case "disable-capability":
			if e.Tool == "" {
				return nil, fmt.Errorf("capability revocation requires a tool")
			}
		default:
			return nil, fmt.Errorf("unsupported revocation action")
		}
		if e.Versions != "" {
			if _, err := semver.NewConstraint(e.Versions); err != nil {
				return nil, fmt.Errorf("invalid revocation version constraint")
			}
		}
		for _, digest := range e.Digests {
			if !digestID.MatchString(digest) {
				return nil, fmt.Errorf("invalid revocation digest")
			}
		}
	}
	return &r, nil
}

// Match returns all entries for the id and either its version or exact digest.
// A selector-free entry applies to every version of that id. Callers decide
// whether delisting, disabling a tool or stopping a workload is appropriate.
func (r *Revocations) Match(id, version, digest string) ([]Revocation, error) {
	v, err := semver.StrictNewVersion(version)
	if err != nil || !pluginID.MatchString(id) || len(id) > 59 || !digestID.MatchString(digest) {
		return nil, fmt.Errorf("invalid plugin identity")
	}
	if !r.ValidUntil().After(time.Now()) {
		return nil, fmt.Errorf("revocation list expired")
	}
	var matches []Revocation
	for _, e := range r.Entries {
		if e.ID != id {
			continue
		}
		match := e.Versions == "" && len(e.Digests) == 0
		if e.Versions != "" {
			c, err := semver.NewConstraint(e.Versions)
			if err != nil {
				return nil, err
			}
			match = match || c.Check(v)
		}
		for _, d := range e.Digests {
			match = match || d == digest
		}
		if match {
			matches = append(matches, e)
		}
	}
	return matches, nil
}

func httpsBase(s string) bool {
	u, err := url.Parse(s)
	return err == nil && u.Scheme == "https" && u.Host != "" && u.User == nil && u.RawQuery == "" && u.Fragment == ""
}

// FetchRevocations verifies the TUF chain and requires the plugins delegation
// itself to authorize this exact target. Metadata and body-version floors are
// retained across checks; missing, expired or rolled-back data fails closed.
func FetchRevocations(c RevocationConfig) (*Revocations, error) {
	if !httpsBase(c.MetadataURL) || !httpsBase(c.TargetsURL) || c.StateDir == "" || len(c.TrustedRoot) == 0 || len(c.TrustedRoot) > 512000 {
		return nil, fmt.Errorf("trusted root, HTTPS repository URLs and persistent state are required")
	}
	if err := os.MkdirAll(c.StateDir, 0700); err != nil {
		return nil, err
	}
	unlock, err := lockRevocations(c.StateDir)
	if err != nil {
		return nil, err
	}
	defer unlock()
	uc, err := config.New(c.MetadataURL, c.TrustedRoot)
	if err != nil {
		return nil, err
	}
	uc.RemoteTargetsURL = c.TargetsURL
	uc.LocalMetadataDir = filepath.Join(c.StateDir, "metadata")
	uc.LocalTargetsDir = filepath.Join(c.StateDir, "targets")
	uc.TargetsMaxLength = maxRevocations
	client := http.Client{Timeout: 20 * time.Second}
	if c.HTTPClient != nil {
		client = *c.HTTPClient
	}
	client.Timeout = 20 * time.Second
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return fmt.Errorf("TUF redirects refused") }
	if err = uc.SetDefaultFetcherHTTPClient(&client); err != nil {
		return nil, err
	}
	u, err := updater.New(uc)
	if err != nil {
		return nil, err
	}
	if err = u.Refresh(); err != nil {
		return nil, fmt.Errorf("plugin TUF refresh: %w", err)
	}
	target, err := u.GetTargetInfo(revocationTarget)
	if err != nil {
		return nil, fmt.Errorf("revocation target: %w", err)
	}
	role := u.GetTrustedMetadataSet().Targets["plugins"]
	if role == nil || role.Signed.Targets[revocationTarget] != target {
		return nil, fmt.Errorf("revocations require the plugins delegation")
	}
	if target.Length < 1 || target.Length > maxRevocations || len(target.Hashes["sha256"]) != sha256.Size {
		return nil, fmt.Errorf("invalid revocation target bounds or hash")
	}
	_, raw, err := u.DownloadTarget(target, filepath.Join(uc.LocalTargetsDir, "revocations.json"), "")
	if err != nil {
		return nil, fmt.Errorf("revocation download: %w", err)
	}
	r, err := parseRevocations(raw, time.Now())
	if err != nil {
		return nil, err
	}
	tm := u.GetTrustedMetadataSet()
	r.validUntil = r.Expires
	for _, expires := range []time.Time{tm.Root.Signed.Expires, tm.Timestamp.Signed.Expires, tm.Snapshot.Signed.Expires} {
		if expires.Before(r.validUntil) {
			r.validUntil = expires
		}
	}
	for _, role := range tm.Targets {
		if role.Signed.Expires.Before(r.validUntil) {
			r.validUntil = role.Signed.Expires
		}
	}
	if !r.ValidUntil().After(time.Now()) {
		return nil, fmt.Errorf("revocation trust metadata expired during fetch")
	}
	if err = persistFloor(c.StateDir, r.Version, raw); err != nil {
		return nil, err
	}
	return r, nil
}

func persistFloor(dir string, version int64, raw []byte) error {
	type floor struct {
		Version int64  `json:"version"`
		SHA256  string `json:"sha256"`
	}
	sum := sha256.Sum256(raw)
	next := floor{version, hex.EncodeToString(sum[:])}
	path := filepath.Join(dir, "revocations-floor.json")
	f, err := os.Open(path)
	if err == nil {
		data, readErr := io.ReadAll(io.LimitReader(f, 4097))
		f.Close()
		var old floor
		if readErr != nil || len(data) > 4096 || strictJSON(data, &old) != nil || old.Version < 1 || !digestID.MatchString("sha256:"+old.SHA256) {
			return fmt.Errorf("invalid persisted revocation floor")
		}
		if next.Version < old.Version || (next.Version == old.Version && next.SHA256 != old.SHA256) {
			return fmt.Errorf("revocation rollback or equivocation refused")
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	data, err := json.Marshal(next)
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, ".revocations-floor-")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err = tmp.Write(data); err == nil {
		err = tmp.Sync()
	}
	closeErr := tmp.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err = os.Rename(tmp.Name(), path); err != nil {
		return err
	}
	d, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}
