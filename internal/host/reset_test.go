// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
	"github.com/onemindos/onemindos/internal/storage/ops"
)

func cand(part, uuid, set string, gen int, sys bool) ops.Candidate {
	return ops.Candidate{Part: part, PartUUID: uuid, Disk: strings.TrimSuffix(part, "1"), System: sys,
		Token: &storage.Token{Type: storage.TokenType, SetUUID: set, PartUUID: uuid, Generation: gen}}
}

// A two-disk mirror plus a disk of another box.
func mirror() []ops.Candidate {
	return []ops.Candidate{
		cand("/dev/vda7", "p-sys", "set-a", 3, true),
		cand("/dev/vdb1", "p-two", "set-a", 3, false),
		cand("/dev/vdc1", "p-other", "set-b", 9, false),
	}
}

func useDisks(t *testing.T, c []ops.Candidate, err error) {
	t.Helper()
	old := candidates
	candidates = func(context.Context, ops.Runner) ([]ops.Candidate, error) { return c, err }
	t.Cleanup(func() { candidates = old })
}

func TestPlanListsEveryMirrorMemberAndTheRecoveryKeyWarning(t *testing.T) {
	p := BuildPlan(mirror())
	if !p.Available || p.SetUUID != "set-a" || len(p.Members) != 2 {
		t.Fatalf("plan: %+v", p)
	}
	got := map[string]bool{}
	for _, m := range p.Members {
		got[m.PartUUID] = true
	}
	if !got["p-sys"] || !got["p-two"] || got["p-other"] {
		t.Fatalf("members must be this box's set only: %v", got)
	}
	for _, want := range []string{"printed recovery key", "fast wipe", "not overwritten", "off this box"} {
		if !strings.Contains(strings.ToLower(p.Warning), strings.ToLower(want)) {
			t.Errorf("warning lacks %q: %s", want, p.Warning)
		}
	}
	if len(p.Erases) == 0 || len(p.Survives) == 0 {
		t.Fatal("the plan must say what is erased and what survives")
	}
	// Stable, and any change to the members changes the hash the owner approved.
	if q := BuildPlan(mirror()); q.SHA256 != p.SHA256 {
		t.Fatal("same disks, different plan hash")
	}
	if q := BuildPlan(mirror()[:1]); q.SHA256 == p.SHA256 || len(q.Members) != 1 {
		t.Fatal("a pulled mirror member must change the plan hash")
	}
}

func TestPlanRefusesWhenDataIsNotEncrypted(t *testing.T) {
	p := BuildPlan(nil)
	if p.Available || !strings.Contains(p.Refusal, "not encrypted") || !strings.Contains(p.Refusal, "slow overwrite is deliberately not offered") {
		t.Fatalf("plan: %+v", p)
	}
	if p.SHA256 == "" || len(p.Members) != 0 {
		t.Fatalf("a refused plan still carries the warning and a hash: %+v", p)
	}
	useDisks(t, nil, nil)
	f := &FactoryReset{ESP: t.TempDir()}
	if f.Unavailable() == "" {
		t.Fatal("Unavailable must carry the refusal")
	}
	if err := f.Arm(context.Background(), Op{ID: "x", PlanSHA256: p.SHA256}); err == nil {
		t.Fatal("armed on an unencrypted box")
	}
	if _, err := os.Stat(filepath.Join(f.ESP, MarkerName)); err == nil {
		t.Fatal("a marker was written")
	}
}

func TestArmWritesMarkerOnlyForTheApprovedPlan(t *testing.T) {
	useDisks(t, mirror(), nil)
	esp := t.TempDir()
	at := time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)
	f := &FactoryReset{ESP: esp, Now: func() time.Time { return at }}
	plan := f.Plan(context.Background())
	if err := f.Arm(context.Background(), Op{ID: "a1", PlanSHA256: strings.Repeat("0", 64)}); err == nil {
		t.Fatal("armed with a plan the owner did not approve")
	}
	if err := f.Arm(context.Background(), Op{ID: "a1", PlanSHA256: plan.SHA256}); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(filepath.Join(esp, MarkerName))
	m, err := ParseMarker(b)
	if err != nil || m.ActionID != "a1" || m.DataSet != "set-a" || !m.ExpiresAt.Equal(at.Add(time.Hour)) {
		t.Fatalf("marker %+v err %v", m, err)
	}
	// An update trial waiting for its verdict: no marker.
	esp2 := t.TempDir()
	_ = os.MkdirAll(filepath.Join(esp2, "onemind"), 0o755)
	_ = os.WriteFile(filepath.Join(esp2, PendingName), []byte("slot=b"), 0o644)
	if err := (&FactoryReset{ESP: esp2}).Arm(context.Background(), Op{ID: "a2", PlanSHA256: plan.SHA256}); err == nil {
		t.Fatal("armed during an update trial")
	}
}

func TestSubmitRefusesAChangedPlan(t *testing.T) {
	useDisks(t, mirror(), nil)
	s, p := newService(t, t.TempDir(), "b")
	s.Reset = &FactoryReset{ESP: t.TempDir()}
	_, _, err := s.Submit(context.Background(), Request{ActionID: "f1", Kind: KindFactoryReset, PlanSHA256: strings.Repeat("0", 64)})
	var r *Refusal
	if !errors.As(err, &r) || r.Reason != "plan_changed" {
		t.Fatalf("err: %v", err)
	}
	if p.reboots != 0 {
		t.Fatal("rebooted")
	}
	// A request without the plan hash is malformed.
	if err := (Request{ActionID: "f1", Kind: KindFactoryReset}).Validate(); err == nil {
		t.Fatal("factory-reset without plan_sha256 accepted")
	}
	if err := (Request{ActionID: "f1", Kind: KindRestart, PlanSHA256: strings.Repeat("a", 64)}).Validate(); err == nil {
		t.Fatal("restart with plan_sha256 accepted")
	}
	good := s.Reset.Plan(context.Background())
	if _, created, err := s.Submit(context.Background(), Request{ActionID: "f2", Kind: KindFactoryReset, PlanSHA256: good.SHA256}); err != nil || !created {
		t.Fatalf("approved plan: %v", err)
	}
	s.Wait()
	if op, _ := s.Store.Get("f2"); op.State != StateGoingDown || p.reboots != 1 {
		t.Fatalf("op %+v reboots %d", op, p.reboots)
	}
}

func TestPlanEndpoint(t *testing.T) {
	useDisks(t, mirror(), nil)
	s, _ := newService(t, t.TempDir(), "b")
	s.Reset = &FactoryReset{ESP: t.TempDir()}
	rec := httptest.NewRecorder()
	(&Server{S: s}).Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/plans/factory-reset", nil))
	var p ResetPlan
	if rec.Code != http.StatusOK || json.Unmarshal(rec.Body.Bytes(), &p) != nil || len(p.Members) != 2 || p.Warning == "" {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
	s.Reset = nil
	rec = httptest.NewRecorder()
	(&Server{S: s}).Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/plans/factory-reset", nil))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("no resetter: %d", rec.Code)
	}
}

type recRunner struct {
	cmds []string
	fail string
}

func (r *recRunner) Exec(_ context.Context, _ string, name string, args ...string) ([]byte, int, error) {
	c := name + " " + strings.Join(args, " ")
	r.cmds = append(r.cmds, c)
	if r.fail != "" && strings.Contains(c, r.fail) {
		return []byte("boom"), 1, nil
	}
	return nil, 0, nil
}

func armed(t *testing.T, at time.Time, set string) string {
	t.Helper()
	esp := t.TempDir()
	m := Marker{ActionID: "fr1", RequestedAt: at, DataSet: set, PlanSHA256: strings.Repeat("a", 64), ExpiresAt: at.Add(time.Hour)}
	if err := writeAtomic(filepath.Join(esp, MarkerName), m.encode()); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(filepath.Join(esp, AppliedName), []byte("join_code=x"), 0o644)
	return esp
}

func TestWipeErasesKeysOfEveryMemberOfTheSetOnly(t *testing.T) {
	useDisks(t, mirror(), nil)
	at := time.Now().UTC()
	esp := armed(t, at, "set-a")
	r := &recRunner{}
	if err := Wipe(context.Background(), r, esp, at.Add(time.Minute)); err != nil {
		t.Fatal(err)
	}
	all := strings.Join(r.cmds, "\n")
	for _, want := range []string{"cryptsetup erase --batch-mode /dev/vda7", "wipefs -a /dev/vda7", "cryptsetup erase --batch-mode /dev/vdb1", "wipefs -a /dev/vdb1"} {
		if !strings.Contains(all, want) {
			t.Errorf("missing %q in\n%s", want, all)
		}
	}
	if strings.Contains(all, "vdc1") {
		t.Fatal("wiped a disk of another set")
	}
	for _, c := range r.cmds { // fast wipe only: nothing overwrites the disks
		if strings.HasPrefix(c, "dd ") || strings.HasPrefix(c, "shred") || strings.Contains(c, "mkfs") {
			t.Fatalf("slow overwrite: %s", c)
		}
	}
	for _, gone := range []string{MarkerName, AppliedName} {
		if _, err := os.Stat(filepath.Join(esp, gone)); err == nil {
			t.Errorf("%s still there", gone)
		}
	}
	if _, err := os.Stat(filepath.Join(esp, MarkerDoneName)); err != nil {
		t.Fatal("no .done marker")
	}
}

func TestWipeRefusesStaleOrMismatchedMarker(t *testing.T) {
	useDisks(t, mirror(), nil)
	at := time.Now().UTC()
	for name, c := range map[string]struct {
		esp string
		now time.Time
	}{
		"expired":          {armed(t, at, "set-a"), at.Add(2 * time.Hour)},
		"another disk set": {armed(t, at, "set-z"), at.Add(time.Minute)},
	} {
		r := &recRunner{}
		if err := Wipe(context.Background(), r, c.esp, c.now); !errors.Is(err, ErrStaleMarker) || len(r.cmds) != 0 {
			t.Errorf("%s: err %v cmds %v", name, err, r.cmds)
		}
		if _, err := os.Stat(filepath.Join(c.esp, MarkerName)); err != nil {
			t.Errorf("%s: marker removed", name)
		}
	}
	if err := Wipe(context.Background(), &recRunner{}, t.TempDir(), at); !errors.Is(err, ErrNoMarker) {
		t.Fatalf("no marker: %v", err)
	}
}

func TestWipeFailureKeepsMarkerAndRetryFinishes(t *testing.T) {
	useDisks(t, mirror(), nil)
	at := time.Now().UTC()
	esp := armed(t, at, "set-a")
	if err := Wipe(context.Background(), &recRunner{fail: "erase --batch-mode /dev/vdb1"}, esp, at); err == nil {
		t.Fatal("a failed erase must fail the wipe")
	}
	b, _ := os.ReadFile(filepath.Join(esp, MarkerName))
	if m, err := ParseMarker(b); err != nil || m.State != "wiping" || m.Attempts != 1 {
		t.Fatalf("marker after failure: %+v %v", m, err)
	}
	// Retry on the next boot: the system disk is already blank, the other member is left.
	useDisks(t, []ops.Candidate{cand("/dev/vdb1", "p-two", "set-a", 3, false), cand("/dev/vdc1", "p-other", "set-b", 9, false)}, nil)
	r := &recRunner{}
	if err := Wipe(context.Background(), r, esp, at); err != nil {
		t.Fatal(err)
	}
	if all := strings.Join(r.cmds, "\n"); !strings.Contains(all, "erase --batch-mode /dev/vdb1") || strings.Contains(all, "vdc1") {
		t.Fatalf("retry: %s", all)
	}
	if _, err := os.Stat(filepath.Join(esp, MarkerDoneName)); err != nil {
		t.Fatal("not finished")
	}
}
