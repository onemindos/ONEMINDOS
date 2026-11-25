// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"sync"
	"time"
)

// JobSchema is the signed job envelope of contract §12.11 (FABRIC.md §5.4):
//
//	{"schema": "onemind.job/v1", "job_id", "action_id", "kind", "params",
//	 "params_sha256": "sha256:<hex>", "issued_at", "expires_at", "sig"}
//
// sig is Ed25519 (standard base64) over CanonicalJSON of the envelope without
// sig, made with the gateway's job key. On a single-box hub the gateway posts
// jobs to the backup agent's loopback API; across nodes the same envelope
// travels on NATS (fabric stream). The signature is the lock either way: a
// process on the box that can reach the loopback port still cannot make the
// agent restore, browse or reconfigure anything.
const JobSchema = "onemind.job/v1"

// JobSchemaV2 is the envelope for a job sent to one joined machine (D-029,
// N2 groundwork). It adds three signed fields to v1:
//
//	"aud": "node:<node_id>"  the one machine the job is for
//	"kid": "job-<16 hex>"    which gateway key signed it (JobKeyID)
//	"policy_epoch": <int>    a machine refuses a job older than the newest epoch it has seen
//
// A verifier with NodeID set (a joined machine) accepts only v2, addressed to
// itself. A verifier without NodeID (the hub's loopback backup agent) accepts
// only v1: it cannot tell which machine it is, so it never takes a v2 job.
const JobSchemaV2 = "onemind.job/v2"

const (
	jobSkew        = 60 * time.Second
	jobMaxLifetime = 24 * time.Hour
)

var (
	jobIDRe   = regexp.MustCompile(`^job_[A-Za-z0-9]{8,64}$`)
	jobKindRe = regexp.MustCompile(`^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$`)
)

// Job is a verified job. Audience, KeyID and PolicyEpoch are set for v2 only.
type Job struct {
	ID          string
	ActionID    string
	Kind        string
	Params      json.RawMessage
	IssuedAt    time.Time
	ExpiresAt   time.Time
	Audience    string
	KeyID       string
	PolicyEpoch uint64
}

// JobError is a refused envelope. Code is a short slug the gateway shows.
type JobError struct {
	Code string // bad_job | bad_signature | expired | replayed | no_key | wrong_audience | unknown_kid | stale_epoch
	Msg  string
}

func (e *JobError) Error() string { return e.Code + ": " + e.Msg }

func jobErr(code, format string, args ...any) error {
	return &JobError{Code: code, Msg: fmt.Sprintf(format, args...)}
}

// JobVerifier checks envelopes against the gateway's public key and keeps
// a done-list so a captured job cannot be replayed.
type JobVerifier struct {
	PubKeyFile string // PEM "PUBLIC KEY" (PKIX) holding an Ed25519 key
	DonePath   string // JSON {job_id: expires_at}
	Now        func() time.Time

	// NodeID makes this a machine's verifier: only onemind.job/v2 envelopes
	// whose aud is "node:<NodeID>", whose kid is the pinned key's JobKeyID and
	// whose policy_epoch is not below the high-water mark in EpochPath.
	NodeID    string
	EpochPath string // JSON {"kid": k, "policy_epoch": n}; required with NodeID

	mu sync.Mutex
}

// NewNodeJobVerifier is the verifier of a joined machine: the job key it
// pinned at join (fabric.JobPubFile) and its state files in stateDir.
func NewNodeJobVerifier(nodeID, pubKeyFile, stateDir string) *JobVerifier {
	return &JobVerifier{PubKeyFile: pubKeyFile, NodeID: nodeID, Now: time.Now,
		DonePath: filepath.Join(stateDir, "jobs-done.json"), EpochPath: filepath.Join(stateDir, "jobs-epoch.json")}
}

// JobKeyID is the key id of a job public key: "job-" and the first 16 hex
// digits of sha256 over the raw 32-byte key. core/onemind_core/backups/jobs.py
// job_kid makes the same string (shared vector in testdata/job-v2-vector.json).
func JobKeyID(pub ed25519.PublicKey) string {
	sum := sha256.Sum256(pub)
	return "job-" + hex.EncodeToString(sum[:])[:16]
}

// Verify checks one envelope and records its id. The key file is read on
// every call, so replacing it takes effect without a restart.
func (v *JobVerifier) Verify(body []byte) (Job, error) {
	raw, err := decodeUseNumber(body)
	if err != nil {
		return Job{}, jobErr("bad_job", "%v", err)
	}
	env, ok := raw.(map[string]any)
	if !ok {
		return Job{}, jobErr("bad_job", "envelope must be a JSON object")
	}
	sigText, _ := env["sig"].(string)
	sig, err := base64.StdEncoding.DecodeString(sigText)
	if err != nil || len(sig) != ed25519.SignatureSize {
		return Job{}, jobErr("bad_signature", "sig must be a base64 Ed25519 signature")
	}
	delete(env, "sig")
	msg, err := CanonicalJSON(env)
	if err != nil {
		return Job{}, jobErr("bad_job", "%v", err)
	}
	pub, err := LoadJobPublicKey(v.PubKeyFile)
	if err != nil {
		return Job{}, jobErr("no_key", "%v", err)
	}
	str := func(k string) string { s, _ := env[k].(string); return s }
	if v.NodeID != "" && str("schema") == JobSchemaV2 && str("kid") != JobKeyID(pub) {
		// Before the signature, so the answer says which key is missing rather than "bad signature".
		return Job{}, jobErr("unknown_kid", "kid %q is not the job key this machine pinned at join", str("kid"))
	}
	if !ed25519.Verify(pub, msg, sig) {
		return Job{}, jobErr("bad_signature", "signature does not verify with the gateway job key")
	}

	j := Job{ID: str("job_id"), ActionID: str("action_id"), Kind: str("kind")}
	switch {
	case v.NodeID == "" && str("schema") != JobSchema:
		return Job{}, jobErr("bad_job", "schema must be %s", JobSchema)
	case v.NodeID != "" && str("schema") != JobSchemaV2:
		return Job{}, jobErr("bad_job", "a joined machine accepts only %s", JobSchemaV2)
	case v.NodeID != "":
		if v.EpochPath == "" {
			return Job{}, jobErr("no_key", "no policy epoch file configured")
		}
		j.Audience, j.KeyID = str("aud"), str("kid")
		if j.Audience != "node:"+v.NodeID {
			return Job{}, jobErr("wrong_audience", "the job is for %q, this machine is node:%s", j.Audience, v.NodeID)
		}
		n, ok := env["policy_epoch"].(json.Number)
		if !ok {
			return Job{}, jobErr("bad_job", "policy_epoch must be a number")
		}
		if j.PolicyEpoch, err = strconv.ParseUint(n.String(), 10, 63); err != nil {
			return Job{}, jobErr("bad_job", "policy_epoch must be a non-negative integer")
		}
	}
	if !jobIDRe.MatchString(j.ID) {
		return Job{}, jobErr("bad_job", "job_id is malformed")
	}
	if !jobKindRe.MatchString(j.Kind) {
		return Job{}, jobErr("bad_job", "kind is malformed")
	}
	params, ok := env["params"].(map[string]any)
	if !ok {
		return Job{}, jobErr("bad_job", "params must be an object")
	}
	pc, err := CanonicalJSON(params)
	if err != nil {
		return Job{}, jobErr("bad_job", "%v", err)
	}
	sum := sha256.Sum256(pc)
	if str("params_sha256") != "sha256:"+hex.EncodeToString(sum[:]) {
		return Job{}, jobErr("bad_job", "params_sha256 does not match params")
	}
	j.Params = pc
	if j.IssuedAt, err = time.Parse(time.RFC3339, str("issued_at")); err != nil {
		return Job{}, jobErr("bad_job", "issued_at: %v", err)
	}
	if j.ExpiresAt, err = time.Parse(time.RFC3339, str("expires_at")); err != nil {
		return Job{}, jobErr("bad_job", "expires_at: %v", err)
	}
	now := v.Now()
	switch {
	case !j.ExpiresAt.After(j.IssuedAt) || j.ExpiresAt.Sub(j.IssuedAt) > jobMaxLifetime:
		return Job{}, jobErr("bad_job", "a job must expire after it is issued and within 24 hours")
	case j.IssuedAt.After(now.Add(jobSkew)):
		return Job{}, jobErr("expired", "issued_at is in the future (clock skew over 60 s)")
	case !now.Before(j.ExpiresAt.Add(jobSkew)):
		return Job{}, jobErr("expired", "the job expired at %s", j.ExpiresAt.UTC().Format(time.RFC3339))
	}
	if err := v.remember(j, now); err != nil {
		return Job{}, err
	}
	return j, nil
}

// remember adds the job id to the done-list (refusing a seen id) and drops
// entries whose job can no longer pass the expiry check anyway. On a machine
// it also refuses an epoch below the high-water mark and then raises the mark.
func (v *JobVerifier) remember(j Job, now time.Time) error {
	v.mu.Lock()
	defer v.mu.Unlock()
	var mark uint64
	if v.NodeID != "" {
		var err error
		if mark, err = readEpoch(v.EpochPath, j.KeyID); err != nil {
			return jobErr("bad_job", "policy epoch file: %v", err)
		}
		if j.PolicyEpoch < mark {
			return jobErr("stale_epoch", "policy_epoch %d is older than %d, the newest this machine has seen", j.PolicyEpoch, mark)
		}
	}
	done := map[string]time.Time{}
	if b, err := os.ReadFile(v.DonePath); err == nil {
		if err := json.Unmarshal(b, &done); err != nil {
			return jobErr("bad_job", "done-list unreadable: %v", err)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return jobErr("bad_job", "done-list: %v", err)
	}
	if _, seen := done[j.ID]; seen {
		return jobErr("replayed", "job %s was already received", j.ID)
	}
	for id, exp := range done {
		if now.After(exp.Add(jobSkew + time.Hour)) {
			delete(done, id)
		}
	}
	done[j.ID] = j.ExpiresAt
	b, err := json.Marshal(done)
	if err != nil {
		return err
	}
	// The done-list first: a crash between the two writes leaves the mark lower (less strict), never
	// a job that can run twice.
	if err := writeFileAtomic(v.DonePath, b, 0o600); err != nil {
		return err
	}
	if v.NodeID != "" && (j.PolicyEpoch > mark || mark == 0) {
		eb, _ := json.Marshal(epochMark{KeyID: j.KeyID, PolicyEpoch: &j.PolicyEpoch})
		return writeFileAtomic(v.EpochPath, eb, 0o600)
	}
	return nil
}

// epochMark is the EpochPath file: the newest policy epoch accepted, and under which job key.
type epochMark struct {
	KeyID       string  `json:"kid"`
	PolicyEpoch *uint64 `json:"policy_epoch"`
}

// readEpoch is the high-water mark in path for the job key kid. A missing file, or a mark kept under
// another key (the machine re-joined, to another box or after a key change), is 0: each key's epochs
// are its own count.
func readEpoch(path, kid string) (uint64, error) {
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	var st epochMark
	if err := json.Unmarshal(b, &st); err != nil || st.PolicyEpoch == nil {
		return 0, fmt.Errorf("%s: not {\"kid\": k, \"policy_epoch\": n}", filepath.Base(path))
	}
	if st.KeyID != kid {
		return 0, nil
	}
	return *st.PolicyEpoch, nil
}

// LoadJobPublicKey reads an Ed25519 public key from a PEM file.
func LoadJobPublicKey(path string) (ed25519.PublicKey, error) {
	if path == "" {
		return nil, errors.New("no job public key configured (job_pubkey_file)")
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	pub, err := ParseJobPublicKey(b)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return pub, nil
}

// ParseJobPublicKey reads an Ed25519 public key from PEM ("PUBLIC KEY", PKIX).
func ParseJobPublicKey(b []byte) (ed25519.PublicKey, error) {
	blk, _ := pem.Decode(b)
	if blk == nil || blk.Type != "PUBLIC KEY" {
		return nil, errors.New("not a PEM public key")
	}
	k, err := x509.ParsePKIXPublicKey(blk.Bytes)
	if err != nil {
		return nil, err
	}
	pub, ok := k.(ed25519.PublicKey)
	if !ok {
		return nil, errors.New("not an Ed25519 key")
	}
	return pub, nil
}

// writeFileAtomic writes data to a temp file beside path and renames it over.
func writeFileAtomic(path string, data []byte, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".tmp-*")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if err := f.Chmod(mode); err != nil {
		f.Close()
		return err
	}
	if _, err := f.Write(data); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	if err := os.Rename(f.Name(), path); err != nil {
		return err
	}
	// The rename itself survives a power cut only once the directory is on disk.
	if d, err := os.Open(filepath.Dir(path)); err == nil {
		_ = d.Sync()
		d.Close()
	}
	return nil
}
