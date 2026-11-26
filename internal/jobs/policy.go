// SPDX-License-Identifier: Apache-2.0

package jobs

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/onemindos/onemindos/internal/backup"
)

// The signed stop and revoke snapshot (D-029 "machines enforce a signed stop
// and revoke snapshot while offline"; core/onemind_core/fabric_policy.py).
//
// The gateway signs one onemind.policy/v1 note per machine whenever the
// answer changes; the hub keeps the newest per machine. Before every job pull
// the intake reads it (PolicyGetSubject), checks the signature with the job
// key pinned at join, and keeps the newest one on disk, so it holds across a
// power cut and while the machine is cut off. Every verified job is then
// checked against it. The note can only ever add a "no".

// PolicySchema is the snapshot envelope.
const PolicySchema = "onemind.policy/v1"

// ActuatePrefixes are the first words of job kinds that move or switch
// something in the world: refused while a stop is on (fabric_policy.py
// ACTUATE_PREFIXES).
var ActuatePrefixes = []string{"physical", "robot", "actuator", "relay", "motion"}

// PolicyGetSubject is where node nodeID reads its newest snapshot
// (core/onemind_core/natsconf.py policy_get_subject).
func PolicyGetSubject(nodeID string) string { return "onemind.node." + nodeID + ".policyget" }

// Policy is a verified snapshot.
type Policy struct {
	Epoch uint64 `json:"epoch"`
	Stop  struct {
		MotionLockout bool `json:"motion_lockout"`
		Agents        bool `json:"agents"`
	} `json:"stop"`
	RevokedKids  []string  `json:"revoked_kids"`
	AllowedKinds *[]string `json:"allowed_kinds"`
	IssuedAt     string    `json:"issued_at"`
}

// PolicyStore keeps this machine's newest verified snapshot (Path, 0600).
type PolicyStore struct {
	Path       string
	NodeID     string
	PubKeyFile string

	mu  sync.Mutex
	cur *Policy
}

// Current is the newest snapshot, or nil before the first.
func (s *PolicyStore) Current() *Policy {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cur == nil {
		if b, err := os.ReadFile(s.Path); err == nil {
			if p, err := s.verify(b); err == nil {
				s.cur = p
			}
		}
	}
	return s.cur
}

// current is Current on a possibly nil store.
func (s *PolicyStore) current() *Policy {
	if s == nil {
		return nil
	}
	return s.Current()
}

// Apply verifies body and keeps it when its epoch is newer than the one held.
// It reports whether the held snapshot changed. An older or equal epoch is
// ignored (a snapshot never goes back).
func (s *PolicyStore) Apply(body []byte) (bool, error) {
	p, err := s.verify(body)
	if err != nil {
		return false, err
	}
	cur := s.Current()
	s.mu.Lock()
	defer s.mu.Unlock()
	if cur != nil && p.Epoch <= cur.Epoch {
		return false, nil
	}
	if err := os.MkdirAll(filepath.Dir(s.Path), 0o700); err != nil {
		return false, err
	}
	tmp := s.Path + ".tmp"
	if err := os.WriteFile(tmp, body, 0o600); err != nil {
		return false, err
	}
	if f, err := os.Open(tmp); err == nil {
		_ = f.Sync()
		f.Close()
	}
	if err := os.Rename(tmp, s.Path); err != nil {
		return false, err
	}
	if d, err := os.Open(filepath.Dir(s.Path)); err == nil {
		_ = d.Sync()
		d.Close()
	}
	s.cur = p
	return true, nil
}

func (s *PolicyStore) verify(body []byte) (*Policy, error) {
	d := json.NewDecoder(bytes.NewReader(body))
	d.UseNumber()
	var env map[string]any
	if err := d.Decode(&env); err != nil {
		return nil, fmt.Errorf("policy: %w", err)
	}
	sig, err := base64.StdEncoding.DecodeString(fmt.Sprint(env["sig"]))
	if err != nil || len(sig) != ed25519.SignatureSize {
		return nil, errors.New("policy: sig must be a base64 Ed25519 signature")
	}
	delete(env, "sig")
	msg, err := backup.CanonicalJSON(env)
	if err != nil {
		return nil, fmt.Errorf("policy: %w", err)
	}
	pub, err := backup.LoadJobPublicKey(s.PubKeyFile)
	if err != nil {
		return nil, fmt.Errorf("policy: %w", err)
	}
	str := func(k string) string { v, _ := env[k].(string); return v }
	switch {
	case str("kid") != backup.JobKeyID(pub):
		return nil, errors.New("policy: not signed by the key this machine pinned at join")
	case !ed25519.Verify(pub, msg, sig):
		return nil, errors.New("policy: signature does not verify")
	case str("schema") != PolicySchema:
		return nil, errors.New("policy: schema must be " + PolicySchema)
	case str("aud") != "node:"+s.NodeID:
		return nil, fmt.Errorf("policy: for %q, this machine is node:%s", str("aud"), s.NodeID)
	}
	n, ok := env["epoch"].(json.Number)
	if !ok {
		return nil, errors.New("policy: epoch must be a number")
	}
	var p Policy
	if p.Epoch, err = strconv.ParseUint(n.String(), 10, 63); err != nil || p.Epoch == 0 {
		return nil, errors.New("policy: epoch must be a positive integer")
	}
	b, _ := json.Marshal(env)
	if err := json.Unmarshal(b, &p); err != nil {
		return nil, fmt.Errorf("policy: %w", err)
	}
	if _, err := time.Parse(time.RFC3339, p.IssuedAt); err != nil {
		return nil, errors.New("policy: issued_at must be RFC 3339")
	}
	return &p, nil
}

// Check returns why the snapshot refuses job j, or "" when it may run.
func (p *Policy) Check(j backup.Job) string {
	if p == nil {
		return ""
	}
	switch {
	case j.PolicyEpoch < p.Epoch:
		return "stale_epoch"
	case contains(p.RevokedKids, j.KeyID):
		return "revoked_key"
	case p.AllowedKinds != nil && !contains(*p.AllowedKinds, j.Kind):
		return "kind_not_allowed"
	case (p.Stop.MotionLockout || p.Stop.Agents) && actuates(j.Kind):
		return "stopped"
	}
	return ""
}

func actuates(kind string) bool {
	first, _, _ := strings.Cut(kind, ".")
	return contains(ActuatePrefixes, first)
}

func contains(xs []string, x string) bool {
	for _, v := range xs {
		if v == x {
			return true
		}
	}
	return false
}
