// SPDX-License-Identifier: Apache-2.0

// Package jobtest signs onemind.job/v2 envelopes the way the gateway does
// (core/onemind_core/backups/jobs.py sign_job_v2), for tests only.
package jobtest

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"os"
	"path/filepath"
	"sync/atomic"
	"time"

	"github.com/onemindos/onemindos/internal/backup"
)

// Signer is a gateway job key.
type Signer struct {
	Priv   ed25519.PrivateKey
	PubPEM []byte
	Kid    string
	n      atomic.Int64
}

// New makes a key and writes its public half to dir/job.pub (as a join pins it).
func New(dir string) (*Signer, string, error) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, "", err
	}
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		return nil, "", err
	}
	s := &Signer{Priv: priv, PubPEM: pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}), Kid: backup.JobKeyID(pub)}
	path := filepath.Join(dir, "job.pub")
	return s, path, os.WriteFile(path, s.PubPEM, 0o644)
}

// Job signs a v2 job of kind for node, issued at now. mut may change the
// envelope before it is signed (to make a bad one).
func (s *Signer) Job(node, kind string, params map[string]any, epoch int, now time.Time, mut func(map[string]any)) ([]byte, string) {
	if params == nil {
		params = map[string]any{}
	}
	pb, _ := json.Marshal(params)
	var pv map[string]any
	_ = json.Unmarshal(pb, &pv)
	pc, err := backup.CanonicalJSON(pv)
	if err != nil {
		panic(err)
	}
	sum := sha256.Sum256(pc)
	nonce := make([]byte, 6)
	_, _ = rand.Read(nonce)
	id := fmt.Sprintf("job_t%06d%s", s.n.Add(1), hex.EncodeToString(nonce))
	env := map[string]any{
		"schema": backup.JobSchemaV2, "job_id": id, "action_id": "act_test", "kind": kind, "params": pv,
		"params_sha256": "sha256:" + hex.EncodeToString(sum[:]),
		"issued_at":     now.UTC().Format(time.RFC3339), "expires_at": now.Add(10 * time.Minute).UTC().Format(time.RFC3339),
		"aud": "node:" + node, "kid": s.Kid, "policy_epoch": epoch,
	}
	if mut != nil {
		mut(env)
	}
	return s.Sign(env), id
}

// Sign signs env over its canonical JSON (without "sig").
func (s *Signer) Sign(env map[string]any) []byte {
	b, _ := json.Marshal(env)
	var m map[string]any
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber()
	if err := d.Decode(&m); err != nil {
		panic(err)
	}
	delete(m, "sig")
	msg, err := backup.CanonicalJSON(m)
	if err != nil {
		panic(err)
	}
	m["sig"] = base64.StdEncoding.EncodeToString(ed25519.Sign(s.Priv, msg))
	out, _ := json.Marshal(m)
	return out
}

// Policy signs an onemind.policy/v1 snapshot for node the way core/onemind_core/fabric_policy.py
// sign_snapshot does.
func (s *Signer) Policy(node string, epoch int, motionLockout, agents bool, revoked []string, allowed []string, now time.Time) []byte {
	if revoked == nil {
		revoked = []string{}
	}
	env := map[string]any{"schema": "onemind.policy/v1", "aud": "node:" + node, "kid": s.Kid, "epoch": epoch,
		"issued_at": now.UTC().Format(time.RFC3339), "stop": map[string]any{"motion_lockout": motionLockout, "agents": agents},
		"revoked_kids": revoked, "allowed_kinds": nil}
	if allowed != nil {
		env["allowed_kinds"] = allowed
	}
	return s.Sign(env)
}
