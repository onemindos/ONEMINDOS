// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// canonicalVector is the same object and bytes as
// core/tests/test_backups_jobs.py::test_canonical_matches_go_vector.
const canonicalVectorIn = `{"z":1,"a":[true,null,-7,"x"],"m":{"b":"Café ☃ 😀","a":"tab\tnl\nq\"bs\\ctl\u0001del\u007f/slash<>&"},"é":0}`
const canonicalVectorOut = `{"a":[true,null,-7,"x"],"m":{"a":"tab\tnl\nq\"bs\\ctl\u0001del\u007f/slash<>&","b":"Caf\u00e9 \u2603 \ud83d\ude00"},"z":1,"\u00e9":0}`

func TestCanonicalJSONMatchesPython(t *testing.T) {
	v, err := decodeUseNumber([]byte(canonicalVectorIn))
	if err != nil {
		t.Fatal(err)
	}
	got, err := CanonicalJSON(v)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != canonicalVectorOut {
		t.Fatalf("canonical\n got %s\nwant %s", got, canonicalVectorOut)
	}
	if _, err := CanonicalJSON(json.Number("1.5")); err == nil {
		t.Fatal("a float must be refused")
	}
}

// testSigner signs jobs the way the gateway does (core/onemind_core/backups/jobs.py).
type testSigner struct {
	priv ed25519.PrivateKey
	pub  string // PEM file
	now  time.Time
	n    int
}

func newTestSigner(t *testing.T, dir string, now time.Time) *testSigner {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		t.Fatal(err)
	}
	p := filepath.Join(dir, "job.pub")
	if err := os.WriteFile(p, pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}), 0o644); err != nil {
		t.Fatal(err)
	}
	return &testSigner{priv: priv, pub: p, now: now}
}

func (s *testSigner) envelope(t *testing.T, kind string, params any) map[string]any {
	t.Helper()
	s.n++
	pb, _ := json.Marshal(params)
	pv, err := decodeUseNumber(pb)
	if err != nil {
		t.Fatal(err)
	}
	pc, err := CanonicalJSON(pv)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(pc)
	return map[string]any{
		"schema": JobSchema, "job_id": "job_test" + hex.EncodeToString([]byte{byte(s.n), byte(s.n >> 8)}) + "aaaa",
		"action_id": "act-1", "kind": kind, "params": pv, "params_sha256": "sha256:" + hex.EncodeToString(sum[:]),
		"issued_at": s.now.UTC().Format(time.RFC3339), "expires_at": s.now.Add(10 * time.Minute).UTC().Format(time.RFC3339),
	}
}

func (s *testSigner) sign(t *testing.T, env map[string]any) []byte {
	t.Helper()
	b, _ := json.Marshal(env)
	v, _ := decodeUseNumber(b)
	m := v.(map[string]any)
	delete(m, "sig")
	msg, err := CanonicalJSON(m)
	if err != nil {
		t.Fatal(err)
	}
	m["sig"] = base64.StdEncoding.EncodeToString(ed25519.Sign(s.priv, msg))
	out, _ := json.Marshal(m)
	return out
}

func (s *testSigner) job(t *testing.T, kind string, params any) []byte {
	return s.sign(t, s.envelope(t, kind, params))
}

func jobCode(err error) string {
	var je *JobError
	if errors.As(err, &je) {
		return je.Code
	}
	return ""
}

func TestJobVerifier(t *testing.T) {
	dir := t.TempDir()
	now := time.Date(2026, 11, 12, 10, 0, 0, 0, time.UTC)
	s := newTestSigner(t, dir, now)
	clock := now
	v := &JobVerifier{PubKeyFile: s.pub, DonePath: filepath.Join(dir, "done.json"), Now: func() time.Time { return clock }}

	body := s.job(t, KindStatus, map[string]any{"path": "/srv/Café/ü.txt"})
	j, err := v.Verify(body)
	if err != nil || j.Kind != KindStatus || j.ActionID != "act-1" {
		t.Fatalf("verify: %+v %v", j, err)
	}
	if _, err := v.Verify(body); jobCode(err) != "replayed" {
		t.Fatalf("replay: %v", err)
	}

	env := s.envelope(t, KindRun, map[string]any{"reason": "manual"})
	signed := s.sign(t, env)
	var m map[string]any
	_ = json.Unmarshal(signed, &m)
	m["kind"] = KindRestore // changed after signing
	tampered, _ := json.Marshal(m)
	if _, err := v.Verify(tampered); jobCode(err) != "bad_signature" {
		t.Fatalf("tampered: %v", err)
	}

	env = s.envelope(t, KindRun, map[string]any{"reason": "manual"})
	env["params_sha256"] = "sha256:" + hex.EncodeToString(make([]byte, 32))
	if _, err := v.Verify(s.sign(t, env)); jobCode(err) != "bad_job" {
		t.Fatalf("params hash: %v", err)
	}

	env = s.envelope(t, KindRun, map[string]any{"reason": "manual"})
	clock = now.Add(10*time.Minute + 30*time.Second) // within the 60 s skew
	if _, err := v.Verify(s.sign(t, env)); err != nil {
		t.Fatalf("within skew: %v", err)
	}
	env = s.envelope(t, KindRun, map[string]any{"reason": "manual"})
	clock = now.Add(12 * time.Minute)
	if _, err := v.Verify(s.sign(t, env)); jobCode(err) != "expired" {
		t.Fatalf("expired: %v", err)
	}

	other := newTestSigner(t, t.TempDir(), now)
	clock = now
	if _, err := v.Verify(other.job(t, KindStatus, map[string]any{})); jobCode(err) != "bad_signature" {
		t.Fatalf("other key: %v", err)
	}
	if _, err := (&JobVerifier{DonePath: v.DonePath, Now: v.Now}).Verify(body); jobCode(err) != "no_key" {
		t.Fatalf("no key: %v", err)
	}
}
