// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Run reasons (BACKUPS.md §10).
const (
	ReasonScheduled  = "scheduled"
	ReasonManual     = "manual"
	ReasonPreUpdate  = "pre-update"
	ReasonPreRestore = "pre-restore"
	ReasonPreDelete  = "pre-delete"
)

// Run and unit states.
const (
	StateRunning   = "running"
	StateSucceeded = "succeeded"
	StatePartial   = "partial"
	StateFailed    = "failed"
	StateRefused   = "refused" // space check or fence stopped the run
)

// Run is one backup run: the restore point the owner picks from. JSON
// follows CONTRACT-12-DRAFT §12.5 GET /v1/backups/runs.
type Run struct {
	ID         string       `json:"id"`
	Reason     string       `json:"reason"`
	ActionID   string       `json:"action_id,omitempty"`
	TargetID   string       `json:"target_id"`
	StartedAt  time.Time    `json:"started_at"`
	FinishedAt *time.Time   `json:"finished_at"`
	State      string       `json:"state"`
	Units      []UnitResult `json:"units"`
	BytesAdded int64        `json:"bytes_added"`
	Error      string       `json:"error,omitempty"`
}

// UnitResult is one unit inside a run.
type UnitResult struct {
	Unit       string `json:"unit"`
	State      string `json:"state"`
	SnapshotID string `json:"snapshot_id,omitempty"`
	Error      string `json:"error,omitempty"`
}

// Verdicts of a verification.
const (
	VerdictPassed = "passed"
	VerdictFailed = "failed"
	VerdictError  = "error" // could not test (no snapshot old enough, target down)
)

// Verification is one verified restore or repository check
// (GET /v1/backups/verifications).
type Verification struct {
	ID         string         `json:"id"`
	Unit       string         `json:"unit"`
	TargetID   string         `json:"target_id"`
	SnapshotID string         `json:"snapshot_id,omitempty"`
	Kind       string         `json:"kind"` // restore | check
	StartedAt  time.Time      `json:"started_at"`
	FinishedAt time.Time      `json:"finished_at"`
	Verdict    string         `json:"verdict"`
	Details    map[string]any `json:"details,omitempty"`
}

// State is what the agent keeps on disk between restarts.
type State struct {
	Generation int `json:"generation"`
	// FencedBy is the newer generation found in a fence record; non-zero
	// means this box was replaced by a restore and must stop backing up.
	FencedBy      int                     `json:"fenced_by,omitempty"`
	Runs          []Run                   `json:"runs"`
	Verifications []Verification          `json:"verifications"`
	LastJobs      map[string]time.Time    `json:"last_jobs"`
	SourceBytes   map[string]int64        `json:"source_bytes"`  // per target, for the space check
	LastVerified  map[string]Verification `json:"last_verified"` // newest passed restore per unit
}

const keepRecords = 500

// Store persists State as JSON with atomic replace.
type Store struct {
	path string
	mu   sync.Mutex
	st   State
}

// OpenStore loads path, or starts empty when it does not exist.
func OpenStore(path string) (*Store, error) {
	s := &Store{path: path}
	b, err := os.ReadFile(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	if err == nil {
		if err := json.Unmarshal(b, &s.st); err != nil {
			return nil, err
		}
	}
	if s.st.LastJobs == nil {
		s.st.LastJobs = map[string]time.Time{}
	}
	if s.st.SourceBytes == nil {
		s.st.SourceBytes = map[string]int64{}
	}
	if s.st.LastVerified == nil {
		s.st.LastVerified = map[string]Verification{}
	}
	return s, nil
}

// View returns a copy of the state.
func (s *Store) View() State {
	s.mu.Lock()
	defer s.mu.Unlock()
	b, _ := json.Marshal(s.st)
	var c State
	_ = json.Unmarshal(b, &c)
	return c
}

// Update changes the state under the lock and saves it.
func (s *Store) Update(f func(*State)) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	f(&s.st)
	if n := len(s.st.Runs); n > keepRecords {
		s.st.Runs = s.st.Runs[n-keepRecords:]
	}
	if n := len(s.st.Verifications); n > keepRecords {
		s.st.Verifications = s.st.Verifications[n-keepRecords:]
	}
	return s.save()
}

func (s *Store) save() error {
	b, err := json.MarshalIndent(s.st, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(s.path), 0o700); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(s.path), ".state-*")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if _, err := f.Write(b); err != nil {
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
	return os.Rename(f.Name(), s.path)
}

// Badge states (BACKUPS.md §8).
const (
	BadgeVerified   = "verified"
	BadgeUnverified = "unverified"
	BadgeStale      = "stale"
	BadgeFailing    = "failing"
	BadgeNone       = "none"
)

// Badge is the per-unit backup badge (CONTRACT-12-DRAFT §12.5).
type Badge struct {
	State         string     `json:"state"`
	VerifiedAt    *time.Time `json:"verified_at"`
	LastSuccessAt *time.Time `json:"last_success_at"`
	Reason        string     `json:"reason,omitempty"`
}

// Badge thresholds for the hourly schedule (BACKUPS.md §8).
const (
	verifiedWindow = 8 * 24 * time.Hour
	staleAfter     = 2 * time.Hour
	failingRuns    = 3
)

// UnitBadge computes the badge of unit from the state at now. Precedence:
// failing, then stale, then not verified, then verified.
func (st State) UnitBadge(unit string, now time.Time) Badge {
	var b Badge
	var results []string // newest last
	for _, r := range st.Runs {
		for _, u := range r.Units {
			if u.Unit != unit || r.State == StateRunning {
				continue
			}
			results = append(results, u.State)
			if u.State == StateSucceeded && r.FinishedAt != nil {
				t := *r.FinishedAt
				b.LastSuccessAt = &t
			}
		}
	}
	var lastVer *Verification
	for i := range st.Verifications {
		v := &st.Verifications[i]
		if v.Unit == unit && v.Kind == "restore" && v.Verdict != VerdictError {
			lastVer = v
		}
	}
	if v, ok := st.LastVerified[unit]; ok {
		t := v.FinishedAt
		b.VerifiedAt = &t
	}
	if len(results) == 0 && lastVer == nil {
		b.State = BadgeNone
		return b
	}
	n := len(results)
	switch {
	case lastVer != nil && lastVer.Verdict == VerdictFailed:
		b.State, b.Reason = BadgeFailing, "last verified restore failed"
	case n >= failingRuns && results[n-1] != StateSucceeded && results[n-2] != StateSucceeded && results[n-3] != StateSucceeded:
		b.State, b.Reason = BadgeFailing, "last 3 runs failed"
	case b.LastSuccessAt == nil || now.Sub(*b.LastSuccessAt) > staleAfter:
		b.State, b.Reason = BadgeStale, "no successful backup within 2 hours"
	case b.VerifiedAt == nil || now.Sub(*b.VerifiedAt) > verifiedWindow:
		b.State, b.Reason = BadgeUnverified, "no passing verified restore within 8 days"
	default:
		b.State = BadgeVerified
	}
	return b
}

// Heartbeat is the optional `backup` object of the node heartbeat
// (CONTRACT-12-DRAFT §12.11).
type Heartbeat struct {
	Running    bool    `json:"running"`
	LastRunAt  *string `json:"last_run_at"`
	LastResult string  `json:"last_result"`
}
