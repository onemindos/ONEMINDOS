// SPDX-License-Identifier: Apache-2.0

package verify

import (
	"crypto"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/sigstore/sigstore/pkg/signature"
	"github.com/theupdateframework/go-tuf/v2/metadata"
)

type signedMetadata interface {
	Sign(signature.Signer) (*metadata.Signature, error)
	ToBytes(bool) ([]byte, error)
}

type testRepo struct {
	t       *testing.T
	dir     string
	keys    map[string]ed25519.PrivateKey
	root    []byte
	version int64
	config  RevocationConfig
}

func (r *testRepo) sign(role string, m signedMetadata) []byte {
	r.t.Helper()
	s, err := signature.LoadSigner(r.keys[role], crypto.Hash(0))
	if err != nil {
		r.t.Fatal(err)
	}
	if _, err = m.Sign(s); err != nil {
		r.t.Fatal(err)
	}
	b, err := m.ToBytes(true)
	if err != nil {
		r.t.Fatal(err)
	}
	return b
}

func (r *testRepo) write(name string, data []byte) {
	r.t.Helper()
	p := filepath.Join(r.dir, name)
	if err := os.MkdirAll(filepath.Dir(p), 0700); err != nil {
		r.t.Fatal(err)
	}
	if err := os.WriteFile(p, data, 0600); err != nil {
		r.t.Fatal(err)
	}
}

func newRepo(t *testing.T) *testRepo {
	t.Helper()
	r := &testRepo{t: t, dir: t.TempDir(), keys: map[string]ed25519.PrivateKey{}}
	root := metadata.Root(time.Now().Add(48 * time.Hour))
	root.Signed.ConsistentSnapshot = false
	for _, role := range []string{"root", "targets", "snapshot", "timestamp", "plugins", "attacker"} {
		_, key, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			t.Fatal(err)
		}
		r.keys[role] = key
		if role != "plugins" && role != "attacker" {
			k, err := metadata.KeyFromPublicKey(key.Public())
			if err != nil {
				t.Fatal(err)
			}
			if err = root.Signed.AddKey(k, role); err != nil {
				t.Fatal(err)
			}
		}
	}
	r.root = r.sign("root", root)
	r.write("metadata/1.root.json", r.root)
	srv := httptest.NewTLSServer(http.FileServer(http.Dir(r.dir)))
	t.Cleanup(srv.Close)
	r.config = RevocationConfig{TrustedRoot: r.root, MetadataURL: srv.URL + "/metadata", TargetsURL: srv.URL + "/targets", StateDir: t.TempDir(), HTTPClient: srv.Client()}
	return r
}

func (r *testRepo) publish(raw []byte, delegated, wrongSigner bool) {
	r.t.Helper()
	r.version++
	expires := time.Now().Add(24 * time.Hour)
	tf, err := metadata.TargetFile().FromBytes(revocationTarget, raw, "sha256")
	if err != nil {
		r.t.Fatal(err)
	}
	targets, plugins := metadata.Targets(expires), metadata.Targets(expires)
	targets.Signed.Version, plugins.Signed.Version = r.version, r.version
	if delegated {
		key, err := metadata.KeyFromPublicKey(r.keys["plugins"].Public())
		if err != nil {
			r.t.Fatal(err)
		}
		id, err := key.ID()
		if err != nil {
			r.t.Fatal(err)
		}
		targets.Signed.Delegations = &metadata.Delegations{Keys: map[string]*metadata.Key{id: key}, Roles: []metadata.DelegatedRole{{Name: "plugins", KeyIDs: []string{id}, Threshold: 1, Terminating: true, Paths: []string{"plugins/*"}}}}
		plugins.Signed.Targets[revocationTarget] = tf
	} else {
		targets.Signed.Targets[revocationTarget] = tf
	}
	snapshot := metadata.Snapshot(expires)
	snapshot.Signed.Version = r.version
	snapshot.Signed.Meta["targets.json"] = metadata.MetaFile(r.version)
	if delegated {
		snapshot.Signed.Meta["plugins.json"] = metadata.MetaFile(r.version)
	}
	timestamp := metadata.Timestamp(expires)
	timestamp.Signed.Version = r.version
	timestamp.Signed.Meta["snapshot.json"] = metadata.MetaFile(r.version)
	pluginSigner := "plugins"
	if wrongSigner {
		pluginSigner = "attacker"
	}
	for role, b := range map[string][]byte{"targets": r.sign("targets", targets), "plugins": r.sign(pluginSigner, plugins), "snapshot": r.sign("snapshot", snapshot), "timestamp": r.sign("timestamp", timestamp)} {
		r.write("metadata/"+role+".json", b)
		r.write(fmt.Sprintf("metadata/%d.%s.json", r.version, role), b)
	}
	r.write("targets/"+revocationTarget, raw)
}

func listBytes(t *testing.T, version int64, expires time.Time, entries ...Revocation) []byte {
	t.Helper()
	if entries == nil {
		entries = []Revocation{}
	}
	b, err := json.Marshal(Revocations{Schema: "onemind.revocations/v1", Version: version, Expires: expires, Entries: entries})
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestSignedDelegatedRevocationsAndPersistentFloor(t *testing.T) {
	r := newRepo(t)
	expires := time.Now().Add(time.Hour)
	raw := listBytes(t, 5, expires.Add(72*time.Hour), Revocation{ID: "hello", Versions: "<=1.2.0", Action: "disable", Reason: "unsafe"})
	r.publish(raw, true, false)
	for range 2 {
		list, err := FetchRevocations(r.config)
		if err != nil || list.Version != 5 {
			t.Fatalf("valid signed list: %v %v", list, err)
		}
		if !list.ValidUntil().Before(list.Expires) {
			t.Fatal("TUF metadata expiry was lost")
		}
		matches, err := list.Match("hello", "1.1.0", "sha256:"+strings.Repeat("a", 64))
		if err != nil || len(matches) != 1 || matches[0].Action != "disable" {
			t.Fatalf("match: %v %v", matches, err)
		}
	}
	// New, valid TUF versions cannot roll back the list's own version or
	// replace an already seen version with different bytes.
	for _, bad := range [][]byte{listBytes(t, 4, expires), listBytes(t, 5, expires)} {
		r.publish(bad, true, false)
		if _, err := FetchRevocations(r.config); err == nil || !strings.Contains(err.Error(), "rollback or equivocation") {
			t.Fatalf("floor bypass: %v", err)
		}
	}
	r.publish(listBytes(t, 6, expires), true, false)
	if _, err := FetchRevocations(r.config); err != nil {
		t.Fatal(err)
	}
}

func TestRootRotationCannotBeRolledBack(t *testing.T) {
	r := newRepo(t)
	expires := time.Now().Add(72 * time.Hour)
	entry := Revocation{ID: "hello", Action: "remove", Reason: "publisher revoked"}
	r.publish(listBytes(t, 1, expires, entry), true, false)
	if _, err := FetchRevocations(r.config); err != nil {
		t.Fatal(err)
	}
	// The owner rotates targets, snapshot and timestamp keys in root v2.
	old := map[string]ed25519.PrivateKey{}
	for k, v := range r.keys {
		old[k] = v
	}
	root2 := metadata.Root(time.Now().Add(48 * time.Hour))
	root2.Signed.Version = 2
	root2.Signed.ConsistentSnapshot = false
	for _, role := range []string{"root", "targets", "snapshot", "timestamp"} {
		if role != "root" {
			_, key, err := ed25519.GenerateKey(rand.Reader)
			if err != nil {
				t.Fatal(err)
			}
			r.keys[role] = key
		}
		k, err := metadata.KeyFromPublicKey(r.keys[role].Public())
		if err != nil {
			t.Fatal(err)
		}
		if err = root2.Signed.AddKey(k, role); err != nil {
			t.Fatal(err)
		}
	}
	r.write("metadata/2.root.json", r.sign("root", root2))
	r.publish(listBytes(t, 2, expires, entry), true, false)
	if _, err := FetchRevocations(r.config); err != nil {
		t.Fatalf("rotation not followed: %v", err)
	}
	// The mirror hides 2.root.json and re-signs with the retired keys and a
	// delegated attacker key, publishing a higher list with nothing revoked.
	if err := os.Remove(filepath.Join(r.dir, "metadata/2.root.json")); err != nil {
		t.Fatal(err)
	}
	r.keys = old
	r.publish(listBytes(t, 3, expires), true, false)
	if list, err := FetchRevocations(r.config); err == nil {
		t.Fatalf("root rollback accepted an un-revoke: %+v", list)
	}
	// A corrupt cached root fails closed instead of falling back.
	if err := os.WriteFile(filepath.Join(r.config.StateDir, "metadata", "root.json"), []byte("{"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := FetchRevocations(r.config); err == nil {
		t.Fatal("corrupt cached root accepted")
	}
}

func TestStartingRootPrefersNewerCachedRoot(t *testing.T) {
	r := newRepo(t)
	cached := filepath.Join(t.TempDir(), "root.json")
	got, err := startingRoot(r.root, cached)
	if err != nil || string(got) != string(r.root) {
		t.Fatalf("bootstrap: %v", err)
	}
	root2 := metadata.Root(time.Now().Add(time.Hour))
	root2.Signed.Version = 2
	b := r.sign("root", root2)
	if err = os.WriteFile(cached, b, 0600); err != nil {
		t.Fatal(err)
	}
	if got, err = startingRoot(r.root, cached); err != nil || string(got) != string(b) {
		t.Fatalf("cached root not preferred: %v", err)
	}
	// A newer operator root replaces an older cache.
	if got, err = startingRoot(b, filepath.Join(r.dir, "metadata/1.root.json")); err != nil || string(got) != string(b) {
		t.Fatalf("operator root with higher version lost: %v", err)
	}
}

func TestRevocationTrustFailures(t *testing.T) {
	for _, name := range []string{"wrong signer", "not delegated", "expired", "tampered target", "timestamp rollback", "expired timestamp", "corrupt floor"} {
		t.Run(name, func(t *testing.T) {
			r := newRepo(t)
			expires := time.Now().Add(time.Hour)
			if name == "expired" {
				expires = time.Now().Add(-time.Hour)
			}
			raw := listBytes(t, 1, expires)
			r.publish(raw, name != "not delegated", name == "wrong signer")
			if name == "expired timestamp" {
				ts := metadata.Timestamp(time.Now().Add(-time.Hour))
				ts.Signed.Meta["snapshot.json"] = metadata.MetaFile(r.version)
				r.write("metadata/timestamp.json", r.sign("timestamp", ts))
			}
			if name == "tampered target" {
				r.write("targets/"+revocationTarget, append(raw, ' '))
			}
			if name == "corrupt floor" {
				if err := os.WriteFile(filepath.Join(r.config.StateDir, "revocations-floor.json"), []byte("broken"), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if name == "timestamp rollback" {
				old, err := os.ReadFile(filepath.Join(r.dir, "metadata/timestamp.json"))
				if err != nil {
					t.Fatal(err)
				}
				r.publish(listBytes(t, 2, expires), true, false)
				if _, err = FetchRevocations(r.config); err != nil {
					t.Fatal(err)
				}
				r.write("metadata/timestamp.json", old)
			}
			if _, err := FetchRevocations(r.config); err == nil {
				t.Fatal("untrusted/stale revocations accepted")
			}
		})
	}
}

func TestRevocationSelectorsAndInvalidEntries(t *testing.T) {
	expires := time.Now().Add(time.Hour)
	digest := "sha256:" + strings.Repeat("a", 64)
	raw := listBytes(t, 1, expires, Revocation{ID: "hello", Digests: []string{digest}, Action: "remove", Reason: "unsafe"}, Revocation{ID: "hello", Versions: "2.0.0", Action: "disable-capability", Tool: "write", Reason: "unsafe"})
	r, err := parseRevocations(raw, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		id, version, digest string
		count               int
	}{{"hello", "1.0.0", digest, 1}, {"hello", "2.0.0", digest, 2}, {"other", "2.0.0", digest, 0}, {"hello", "1.0.0", "sha256:" + strings.Repeat("b", 64), 0}} {
		m, err := r.Match(tc.id, tc.version, tc.digest)
		if err != nil || len(m) != tc.count {
			t.Fatalf("%+v: %v %v", tc, m, err)
		}
	}
	// Prereleases must not slip past a version range: Masterminds leaves them
	// out of ranges that do not name a prerelease.
	pre, err := parseRevocations(listBytes(t, 1, expires, Revocation{ID: "hello", Versions: "<=1.2.0", Action: "remove", Reason: "unsafe"}), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	for v, want := range map[string]int{"1.1.0": 1, "1.1.0-rc.1": 1, "1.2.0-0": 1, "1.2.0-rc.2+build.5": 1, "1.2.1-rc.1": 0, "2.0.0-beta.1": 0, "1.2.1": 0} {
		if m, err := pre.Match("hello", v, digest); err != nil || len(m) != want {
			t.Fatalf("version %s: %d matches, want %d (%v)", v, len(m), want, err)
		}
	}
	for _, entry := range []Revocation{{ID: "hello", Action: "unknown", Reason: "x"}, {ID: "hello", Action: "disable-capability", Reason: "x"}, {ID: "hello", Action: "disable", Reason: "x", Versions: "invalid!"}, {ID: "hello", Action: "disable", Reason: "x", Digests: []string{"latest"}}} {
		if _, err := parseRevocations(listBytes(t, 1, expires, entry), time.Now()); err == nil {
			t.Fatalf("invalid entry accepted: %+v", entry)
		}
	}
	r.validUntil = time.Now().Add(-time.Second)
	if _, err := r.Match("hello", "1.0.0", digest); err == nil {
		t.Fatal("expired chain reused")
	}
}
