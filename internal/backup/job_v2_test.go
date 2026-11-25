// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// The v2 envelope (D-029, N2 groundwork): a machine accepts a job only when it
// is signed by the key it pinned at join, addressed to its own node id, not
// older than the newest policy epoch it has seen, and not seen before.

type v2Vector struct {
	SeedHex   string         `json:"seed_hex"`
	PublicPEM string         `json:"public_pem"`
	Kid       string         `json:"kid"`
	Now       string         `json:"now"`
	Envelope  map[string]any `json:"envelope"`
}

func loadV2Vector(t *testing.T) v2Vector {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("testdata", "job-v2-vector.json"))
	if err != nil {
		t.Fatal(err)
	}
	var v v2Vector
	if err := json.Unmarshal(b, &v); err != nil {
		t.Fatal(err)
	}
	return v
}

// v2Signer signs v2 envelopes the way core/onemind_core/backups/jobs.py sign_job_v2 does.
type v2Signer struct {
	*testSigner
	kid string
}

func newV2Signer(t *testing.T, dir string, now time.Time) *v2Signer {
	s := newTestSigner(t, dir, now)
	return &v2Signer{testSigner: s, kid: JobKeyID(s.priv.Public().(ed25519.PublicKey))}
}

func (s *v2Signer) job(t *testing.T, node string, epoch int, mut func(map[string]any)) []byte {
	t.Helper()
	env := s.envelope(t, "update.apply", map[string]any{"version": "1.2.3", "node_id": node})
	env["schema"], env["aud"], env["kid"], env["policy_epoch"] = JobSchemaV2, "node:"+node, s.kid, epoch
	if mut != nil {
		mut(env)
	}
	return s.sign(t, env)
}

func nodeVerifier(dir, pub, node string, clock *time.Time) *JobVerifier {
	v := NewNodeJobVerifier(node, pub, filepath.Join(dir, "state-"+node))
	v.Now = func() time.Time { return *clock }
	return v
}

// The vector Python signed is accepted on machine nodea and refused on nodeb.
func TestJobV2VectorFromPython(t *testing.T) {
	vec := loadV2Vector(t)
	seed, err := hex.DecodeString(vec.SeedHex)
	if err != nil {
		t.Fatal(err)
	}
	pub := ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
	if got := JobKeyID(pub); got != vec.Kid {
		t.Fatalf("JobKeyID = %s, Python job_kid = %s", got, vec.Kid)
	}
	parsed, err := ParseJobPublicKey([]byte(vec.PublicPEM))
	if err != nil || !parsed.Equal(pub) {
		t.Fatalf("public PEM: %v", err)
	}
	dir := t.TempDir()
	pubFile := filepath.Join(dir, "job.pub")
	if err := os.WriteFile(pubFile, []byte(vec.PublicPEM), 0o644); err != nil {
		t.Fatal(err)
	}
	now, _ := time.Parse(time.RFC3339, vec.Now)
	body, _ := json.Marshal(vec.Envelope)

	if _, err := nodeVerifier(dir, pubFile, "nodeb", &now).Verify(body); jobCode(err) != "wrong_audience" {
		t.Fatalf("a job for nodea on nodeb: %v", err)
	}
	j, err := nodeVerifier(dir, pubFile, "nodea", &now).Verify(body)
	if err != nil {
		t.Fatalf("nodea: %v", err)
	}
	if j.Audience != "node:nodea" || j.KeyID != vec.Kid || j.PolicyEpoch != 7 || j.Kind != "update.apply" || j.ActionID != "act_1" {
		t.Fatalf("job: %+v", j)
	}
	// The hub's loopback verifier (no node id) takes v1 only.
	hub := &JobVerifier{PubKeyFile: pubFile, DonePath: filepath.Join(dir, "hub-done.json"), Now: func() time.Time { return now }}
	if _, err := hub.Verify(body); jobCode(err) != "bad_job" {
		t.Fatalf("v2 on the hub verifier: %v", err)
	}
}

func TestJobV2Refusals(t *testing.T) {
	dir := t.TempDir()
	now := time.Date(2026, 11, 25, 12, 0, 0, 0, time.UTC)
	clock := now
	s := newV2Signer(t, dir, now)
	a := nodeVerifier(dir, s.pub, "nodea", &clock)
	b := nodeVerifier(dir, s.pub, "nodeb", &clock)

	// Signed for machine A: B refuses it, A takes it once, and a replay is refused.
	forA := s.job(t, "nodea", 3, nil)
	if _, err := b.Verify(forA); jobCode(err) != "wrong_audience" {
		t.Fatalf("A's job on B: %v", err)
	}
	if _, err := a.Verify(forA); err != nil {
		t.Fatalf("A's job on A: %v", err)
	}
	if _, err := a.Verify(forA); jobCode(err) != "replayed" {
		t.Fatalf("replay: %v", err)
	}
	// A fresh verifier over the same state files (a restart) still refuses the replay.
	if _, err := nodeVerifier(dir, s.pub, "nodea", &clock).Verify(forA); jobCode(err) != "replayed" {
		t.Fatalf("replay after restart: %v", err)
	}

	// Unknown kid: a different key, and the right key with a kid it does not have.
	other := newV2Signer(t, t.TempDir(), now)
	if _, err := a.Verify(other.job(t, "nodea", 3, nil)); jobCode(err) != "unknown_kid" {
		t.Fatalf("other key: %v", err)
	}
	if _, err := a.Verify(s.job(t, "nodea", 3, func(e map[string]any) { e["kid"] = "job-0000000000000000" })); jobCode(err) != "unknown_kid" {
		t.Fatalf("wrong kid: %v", err)
	}
	// The other key claiming the pinned kid still fails the signature.
	if _, err := a.Verify(other.job(t, "nodea", 3, func(e map[string]any) { e["kid"] = s.kid })); jobCode(err) != "bad_signature" {
		t.Fatalf("forged kid: %v", err)
	}

	// Epoch: A has seen 3. 3 again is fine, 2 is refused, 5 raises the mark so 4 is then refused.
	if _, err := a.Verify(s.job(t, "nodea", 3, nil)); err != nil {
		t.Fatalf("same epoch: %v", err)
	}
	if _, err := a.Verify(s.job(t, "nodea", 2, nil)); jobCode(err) != "stale_epoch" {
		t.Fatalf("old epoch: %v", err)
	}
	if _, err := a.Verify(s.job(t, "nodea", 5, nil)); err != nil {
		t.Fatalf("newer epoch: %v", err)
	}
	if _, err := nodeVerifier(dir, s.pub, "nodea", &clock).Verify(s.job(t, "nodea", 4, nil)); jobCode(err) != "stale_epoch" {
		t.Fatalf("epoch below the mark after restart: %v", err)
	}
	// B's mark is its own: epoch 1 is still new there.
	if _, err := b.Verify(s.job(t, "nodeb", 1, nil)); err != nil {
		t.Fatalf("B, epoch 1: %v", err)
	}

	// The mark belongs to the key: after a re-join under a new key (another box, or a rotated key),
	// that key's epochs count on their own, and the old key's jobs are refused as unknown.
	newKey := newV2Signer(t, t.TempDir(), now)
	newKey.n = 1000 // job ids apart from s's (the test signer counts them)
	a2 := nodeVerifier(dir, newKey.pub, "nodea", &clock)
	if _, err := a2.Verify(newKey.job(t, "nodea", 1, nil)); err != nil {
		t.Fatalf("epoch 1 under a new key: %v", err)
	}
	if _, err := a2.Verify(s.job(t, "nodea", 9, nil)); jobCode(err) != "unknown_kid" {
		t.Fatalf("old key after re-join: %v", err)
	}
	if _, err := a2.Verify(newKey.job(t, "nodea", 0, nil)); jobCode(err) != "stale_epoch" {
		t.Fatalf("new key, older epoch: %v", err)
	}

	// A machine refuses v1, and malformed v2 fields.
	if _, err := a.Verify(s.testSigner.job(t, "update.apply", map[string]any{})); jobCode(err) != "bad_job" {
		t.Fatalf("v1 on a machine: %v", err)
	}
	for name, mut := range map[string]func(map[string]any){
		"no aud":         func(e map[string]any) { delete(e, "aud") },
		"aud prefix":     func(e map[string]any) { e["aud"] = "nodea" },
		"epoch negative": func(e map[string]any) { e["policy_epoch"] = -1 },
		"epoch string":   func(e map[string]any) { e["policy_epoch"] = "9" },
		"no epoch":       func(e map[string]any) { delete(e, "policy_epoch") },
	} {
		code := jobCode(func() error { _, err := a.Verify(s.job(t, "nodea", 9, mut)); return err }())
		if code != "wrong_audience" && code != "bad_job" {
			t.Errorf("%s: code %q", name, code)
		}
	}
	// aud changed after signing breaks the signature (it is signed).
	var m map[string]any
	_ = json.Unmarshal(s.job(t, "nodeb", 9, nil), &m)
	m["aud"] = "node:nodea"
	tampered, _ := json.Marshal(m)
	if _, err := a.Verify(tampered); jobCode(err) != "bad_signature" {
		t.Fatalf("aud rewritten: %v", err)
	}
	// No epoch file configured on a machine verifier: refused, never unchecked.
	bad := &JobVerifier{PubKeyFile: s.pub, DonePath: filepath.Join(dir, "x.json"), NodeID: "nodea", Now: a.Now}
	if _, err := bad.Verify(s.job(t, "nodea", 9, nil)); jobCode(err) != "no_key" {
		t.Fatalf("no epoch path: %v", err)
	}
}
