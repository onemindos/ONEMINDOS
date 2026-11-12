// SPDX-License-Identifier: Apache-2.0

// Package tuftest builds a small TUF 1.0 repository in memory for tests and
// local dry runs, with the role layout of os/update/CHANNEL.md (root,
// targets, snapshot, timestamp; one ed25519 key each).
//
// The keys are generated per Repo and live only in memory: nothing here ever
// writes a private key to disk. It is NOT the release signer; the release
// pipeline signs with its own keys (os/update/CHANNEL.md).
package tuftest

import (
	"crypto"
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"time"

	"github.com/sigstore/sigstore/pkg/signature"
	"github.com/theupdateframework/go-tuf/v2/metadata"
)

// Expiries of CHANNEL.md.
const (
	TimestampExpiry = 24 * time.Hour
	SnapshotExpiry  = 7 * 24 * time.Hour
	TargetsExpiry   = 30 * 24 * time.Hour
	RootExpiry      = 365 * 24 * time.Hour
)

// Meta is a target's custom metadata (os/update/CHANNEL.md).
type Meta struct {
	Board             string `json:"board"`
	Version           string `json:"version"`
	Compatible        string `json:"compatible"`
	MinFromVersion    string `json:"min_from_version"`
	Security          bool   `json:"security"`
	BuiltFromSnapshot string `json:"built_from_snapshot"`
	SBOM              string `json:"sbom"`
	CVEReport         string `json:"cve_report"`
}

// Repo is an in-memory TUF repository.
type Repo struct {
	Now                time.Time // signing time; expiries count from here
	ConsistentSnapshot bool
	keys               map[string]ed25519.PrivateKey
	root               *metadata.Metadata[metadata.RootType]
	targets            map[string][]byte // path -> content
	meta               map[string]Meta
	// Version counters (bumped by Publish).
	tVer, sVer, tsVer int64
}

// New returns a repo with fresh keys and a version-1 root.
func New(now time.Time) (*Repo, error) {
	r := &Repo{Now: now, keys: map[string]ed25519.PrivateKey{}, targets: map[string][]byte{}, meta: map[string]Meta{}}
	r.root = metadata.Root(now.Add(RootExpiry))
	for _, role := range []string{metadata.ROOT, metadata.TARGETS, metadata.SNAPSHOT, metadata.TIMESTAMP} {
		_, priv, err := ed25519.GenerateKey(nil)
		if err != nil {
			return nil, err
		}
		r.keys[role] = priv
		k, err := metadata.KeyFromPublicKey(priv.Public())
		if err != nil {
			return nil, err
		}
		if err := r.root.Signed.AddKey(k, role); err != nil {
			return nil, err
		}
	}
	return r, nil
}

// AddTarget adds a bundle at <board>/<version>/onemind-<board>-<version>.raucb.
func (r *Repo) AddTarget(m Meta, content []byte) string {
	p := fmt.Sprintf("%s/%s/onemind-%s-%s.raucb", m.Board, m.Version, m.Board, m.Version)
	r.targets[p], r.meta[p] = content, m
	return p
}

// AddRaw adds a target at an arbitrary path with arbitrary custom metadata.
func (r *Repo) AddRaw(p string, m Meta, content []byte) { r.targets[p], r.meta[p] = content, m }

func (r *Repo) sign(role string, s interface {
	Sign(signature.Signer) (*metadata.Signature, error)
}) error {
	sg, err := signature.LoadSigner(r.keys[role], crypto.Hash(0))
	if err != nil {
		return err
	}
	_, err = s.Sign(sg)
	return err
}

// RootJSON returns the signed root (what the image ships).
func (r *Repo) RootJSON() ([]byte, error) {
	r.root.Signed.ConsistentSnapshot = r.ConsistentSnapshot
	r.root.ClearSignatures()
	if err := r.sign(metadata.ROOT, r.root); err != nil {
		return nil, err
	}
	return r.root.ToBytes(true)
}

// Publish writes metadata to dir and targets to dir/targets (hash-prefixed
// names when ConsistentSnapshot), bumping targets/snapshot/timestamp versions.
// tsExpiry overrides the timestamp expiry when non-zero (negative = expired).
func (r *Repo) Publish(dir string, tsExpiry time.Duration) error {
	if tsExpiry == 0 {
		tsExpiry = TimestampExpiry
	}
	r.tVer++
	r.sVer++
	r.tsVer++
	tg := metadata.Targets(r.Now.Add(TargetsExpiry))
	tg.Signed.Version = r.tVer
	for p, b := range r.targets {
		tf, err := metadata.TargetFile().FromBytes(p, b, "sha256")
		if err != nil {
			return err
		}
		cj, err := json.Marshal(r.meta[p])
		if err != nil {
			return err
		}
		raw := json.RawMessage(cj)
		tf.Custom = &raw
		tg.Signed.Targets[p] = tf
		out := filepath.Join(dir, "targets", filepath.FromSlash(p))
		if r.ConsistentSnapshot {
			out = filepath.Join(dir, "targets", filepath.FromSlash(path.Dir(p)), hex.EncodeToString(tf.Hashes["sha256"])+"."+path.Base(p))
		}
		if err := os.MkdirAll(filepath.Dir(out), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(out, b, 0o644); err != nil {
			return err
		}
	}
	if err := r.sign(metadata.TARGETS, tg); err != nil {
		return err
	}
	sn := metadata.Snapshot(r.Now.Add(SnapshotExpiry))
	sn.Signed.Version = r.sVer
	sn.Signed.Meta["targets.json"] = metadata.MetaFile(r.tVer)
	if err := r.sign(metadata.SNAPSHOT, sn); err != nil {
		return err
	}
	ts := metadata.Timestamp(r.Now.Add(tsExpiry))
	ts.Signed.Version = r.tsVer
	ts.Signed.Meta["snapshot.json"] = metadata.MetaFile(r.sVer)
	if err := r.sign(metadata.TIMESTAMP, ts); err != nil {
		return err
	}
	rootJSON, err := r.RootJSON()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	files := map[string][]byte{"1.root.json": rootJSON, "root.json": rootJSON}
	for name, m := range map[string]interface{ ToBytes(bool) ([]byte, error) }{"targets": tg, "snapshot": sn, "timestamp": ts} {
		b, err := m.ToBytes(true)
		if err != nil {
			return err
		}
		files[name+".json"] = b
		if name != "timestamp" {
			files[fmt.Sprintf("%d.%s.json", map[string]int64{"targets": r.tVer, "snapshot": r.sVer}[name], name)] = b
		}
	}
	for n, b := range files {
		if err := os.WriteFile(filepath.Join(dir, n), b, 0o644); err != nil {
			return err
		}
	}
	return nil
}
