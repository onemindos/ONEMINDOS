// SPDX-License-Identifier: Apache-2.0

package jobs

import (
	"crypto/ed25519"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/jobs/jobtest"
)

// The gateway's snapshot (core/tests/test_fabric_policy.py writes testdata/policy-vector.json with the
// job v2 vector's test key) verifies here byte for byte.
func TestPolicyVectorFromPython(t *testing.T) {
	var v struct {
		NodeID   string         `json:"node_id"`
		Envelope map[string]any `json:"envelope"`
	}
	raw, _ := os.ReadFile(filepath.Join("testdata", "policy-vector.json"))
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatal(err)
	}
	var jv struct {
		SeedHex string `json:"seed_hex"`
	}
	jraw, _ := os.ReadFile(filepath.Join("..", "backup", "testdata", "job-v2-vector.json"))
	_ = json.Unmarshal(jraw, &jv)
	seed, _ := hex.DecodeString(jv.SeedHex)
	der, _ := x509.MarshalPKIXPublicKey(ed25519.NewKeyFromSeed(seed).Public())
	dir := t.TempDir()
	pubFile := filepath.Join(dir, "job.pub")
	_ = os.WriteFile(pubFile, pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}), 0o644)
	body, _ := json.Marshal(v.Envelope)
	s := &PolicyStore{Path: filepath.Join(dir, "policy.json"), NodeID: v.NodeID, PubKeyFile: pubFile}
	if changed, err := s.Apply(body); err != nil || !changed {
		t.Fatalf("vector refused: %v", err)
	}
	p := s.Current()
	if p.Epoch != 3 || !p.Stop.MotionLockout || p.Stop.Agents || len(p.RevokedKids) != 1 || p.AllowedKinds == nil || len(*p.AllowedKinds) != 2 {
		t.Fatalf("%+v", p)
	}
	other := &PolicyStore{Path: filepath.Join(dir, "b.json"), NodeID: "nodeb", PubKeyFile: pubFile}
	if _, err := other.Apply(body); err == nil {
		t.Fatal("node b accepted node a's snapshot")
	}
}

func TestPolicyStoreKeepsTheNewestAndRefusesForgeries(t *testing.T) {
	dir := t.TempDir()
	s, pub, err := jobtest.New(dir)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	st := &PolicyStore{Path: filepath.Join(dir, "policy.json"), NodeID: "n1", PubKeyFile: pub}
	if ok, err := st.Apply(s.Policy("n1", 2, false, false, nil, nil, now)); !ok || err != nil {
		t.Fatalf("epoch 2: %v %v", ok, err)
	}
	if ok, err := st.Apply(s.Policy("n1", 1, true, true, nil, nil, now)); ok || err != nil {
		t.Fatalf("an older snapshot replaced a newer one: %v %v", ok, err)
	}
	other, _, _ := jobtest.New(t.TempDir())
	var forged map[string]any
	_ = json.Unmarshal(s.Policy("n1", 9, false, false, nil, nil, now), &forged)
	forged["stop"] = map[string]any{"motion_lockout": false, "agents": false}
	forged["epoch"] = 10
	fb, _ := json.Marshal(forged)
	for name, body := range map[string][]byte{
		"another key":  other.Policy("n1", 5, false, false, nil, nil, now),
		"another node": s.Policy("n2", 5, false, false, nil, nil, now),
		"edited":       fb,
		"not json":     []byte("{"),
		"epoch zero":   s.Policy("n1", 0, false, false, nil, nil, now),
		"no signature": []byte(`{"schema":"onemind.policy/v1","aud":"node:n1","epoch":7}`),
	} {
		if ok, err := st.Apply(body); ok || err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	// Survives a restart: a new store reads the file and re-verifies it.
	if p := (&PolicyStore{Path: st.Path, NodeID: "n1", PubKeyFile: pub}).Current(); p == nil || p.Epoch != 2 {
		t.Fatalf("reloaded %+v", p)
	}
}

func TestPolicyCheck(t *testing.T) {
	allowed := []string{"host.check", "relay.set"}
	p := &Policy{Epoch: 4, RevokedKids: []string{"job-bad"}, AllowedKinds: &allowed}
	j := func(kind, kid string, epoch uint64) backup.Job {
		return backup.Job{Kind: kind, KeyID: kid, PolicyEpoch: epoch}
	}
	for _, c := range []struct {
		job  backup.Job
		stop bool
		want string
	}{
		{j("host.check", "job-ok", 4), false, ""},
		{j("host.check", "job-ok", 3), false, "stale_epoch"},
		{j("host.check", "job-bad", 4), false, "revoked_key"},
		{j("update.apply", "job-ok", 4), false, "kind_not_allowed"},
		{j("relay.set", "job-ok", 4), false, ""},
		{j("relay.set", "job-ok", 4), true, "stopped"},
		{j("host.check", "job-ok", 5), true, ""},
	} {
		p.Stop.MotionLockout = c.stop
		if got := p.Check(c.job); got != c.want {
			t.Errorf("%+v stop=%v: %q, want %q", c.job, c.stop, got, c.want)
		}
	}
	// #1210 review: with no verified snapshot, nothing that actuates may run; read-only jobs still do.
	if got := (*Policy)(nil).Check(j("relay.set", "x", 0)); got != "no_policy" {
		t.Errorf("no snapshot, actuating job: %q, want no_policy", got)
	}
	if got := (*Policy)(nil).Check(j("host.check", "x", 0)); got != "" {
		t.Errorf("no snapshot, read-only job: %q, want it to run", got)
	}
}

// #1210 review: a snapshot on disk that does not verify is not "no stop": Current is nil (so actuating
// jobs are refused as no_policy) and LoadError says why, for the intake's loud log line.
func TestPolicyStoreOnDiskThatDoesNotVerifyFailsClosedAndSaysWhy(t *testing.T) {
	dir := t.TempDir()
	s, pub, err := jobtest.New(dir)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "policy.json")
	fresh := &PolicyStore{Path: path, NodeID: "n1", PubKeyFile: pub}
	if fresh.Current() != nil || fresh.LoadError() != nil {
		t.Fatal("no file yet must be nil with no error")
	}
	if err := os.WriteFile(path, []byte(`{"schema":"onemind.policy/v1","epoch":9,"stop":{}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	st := &PolicyStore{Path: path, NodeID: "n1", PubKeyFile: pub}
	if p := st.Current(); p != nil {
		t.Fatalf("an unsigned file was used: %+v", p)
	}
	if err := st.LoadError(); err == nil || !strings.Contains(err.Error(), "does not verify") {
		t.Fatalf("load error %v", err)
	}
	if got := st.Current().Check(backup.Job{Kind: "relay.set", PolicyEpoch: 9}); got != "no_policy" {
		t.Fatalf("actuating job with a broken snapshot: %q", got)
	}
	// A new verified note from the hub replaces it and clears the error.
	if ok, err := st.Apply(s.Policy("n1", 1, false, false, nil, nil, time.Now())); !ok || err != nil {
		t.Fatalf("apply: %v %v", ok, err)
	}
	if st.LoadError() != nil || st.Current() == nil {
		t.Fatal("error not cleared by a verified note")
	}
}
