// SPDX-License-Identifier: Apache-2.0

// Package ops runs approved storage plans (docs/umbrel2/storage.md §4.5,
// STORAGE-ACT-1 / UMB-STOR-4): one operation at a time per node, every step
// journaled before and after it runs, so a power cut or a crash at any step
// is either resumed or rolled back when onemindd starts again.
//
// The engine never runs commands it is given: a caller sends a request (kind,
// disks, the plan_sha256 the owner approved), the engine renders the plan
// itself from a fresh inventory, and refuses when the hash differs.
package ops

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
)

// Operation kinds (action types storage.mirror.<kind>, plus repair).
const (
	KindCreate  = "create"  // one disk → mirror (PlanProtect on a one-member set)
	KindAdd     = "add"     // n → n+1 (PlanProtect on a set of two or more)
	KindReplace = "replace" // PlanReplace
	KindRemove  = "remove"  // PlanRemove
	KindRepair  = "repair"  // PlanRepair: scrub, soft-convert, clear marker
)

// Operation and step states.
const (
	StateRunning        = "running"
	StateSucceeded      = "succeeded"
	StateFailed         = "failed"          // a commit step failed: nothing rolled back, the set is usable; see Error
	StateRollingBack    = "rolling_back"    // undoing prepare/join steps
	StateRolledBack     = "rolled_back"     // back to the state before the operation
	StateNeedsAttention = "needs_attention" // could neither finish nor undo (a disk vanished mid-way)

	StepPending = "pending"
	StepRunning = "running"
	StepDone    = "done"
	StepFailed  = "failed"
	StepSkipped = "skipped" // the probe found its effect already in place
)

// Request is what the gateway sends for an approved action.
type Request struct {
	Kind       string `json:"kind"`
	Device     string `json:"device,omitempty"`    // create/add/replace: the blank disk (path or id)
	Member     string `json:"member,omitempty"`    // replace/remove: devid, device, disk or "missing"
	Unprotect  bool   `json:"unprotect,omitempty"` // remove: accept going below two members
	Wipe       bool   `json:"wipe,omitempty"`      // replace/remove: erase the old disk afterwards
	PlanSHA256 string `json:"plan_sha256,omitempty"`
	ActionID   string `json:"action_id,omitempty"` // the gateway action; becomes the operation id
}

// StepRun is the journal record of one plan step.
type StepRun struct {
	State      string     `json:"state"`
	Attempts   int        `json:"attempts,omitempty"`
	StartedAt  *time.Time `json:"started_at,omitempty"`
	FinishedAt *time.Time `json:"finished_at,omitempty"`
	Exit       int        `json:"exit,omitempty"`
	Output     string     `json:"output,omitempty"` // tail of stdout+stderr
	Note       string     `json:"note,omitempty"`   // what a resume probe decided
}

// Target is a disk the operation prepares, and how to find it again after
// a reboot (the kernel may hand out vdb and vdc the other way round).
type Target struct {
	DiskID   string `json:"disk_id"`
	Path     string `json:"path"`
	Part     string `json:"part"`
	PartUUID string `json:"partuuid,omitempty"`
	Size     uint64 `json:"size_bytes"`
	Model    string `json:"model,omitempty"`
}

// Op is one journaled operation.
type Op struct {
	ID         string         `json:"id"`
	Request    Request        `json:"request"`
	Plan       storage.Plan   `json:"plan"`
	Targets    []Target       `json:"targets,omitempty"`
	Refs       map[string]Ref `json:"refs,omitempty"`      // device path → how to find it after a reboot
	Relocated  []string       `json:"relocated,omitempty"` // "old→new" device paths rewritten on resume
	State      string         `json:"state"`
	Next       int            `json:"next"` // index of the first step not done
	Steps      []StepRun      `json:"steps"`
	Rollback   []RollbackRun  `json:"rollback,omitempty"`
	Error      string         `json:"error,omitempty"`
	Resumes    int            `json:"resumes,omitempty"`
	CreatedAt  time.Time      `json:"created_at"`
	UpdatedAt  time.Time      `json:"updated_at"`
	FinishedAt *time.Time     `json:"finished_at,omitempty"`
}

// RollbackRun records one undo command.
type RollbackRun struct {
	Cmd    []string `json:"cmd"`
	Exit   int      `json:"exit"`
	Output string   `json:"output,omitempty"`
}

// Busy reports whether the operation still owns the set.
func (o *Op) Busy() bool { return o.State == StateRunning || o.State == StateRollingBack }

// Progress is done steps over all steps.
func (o *Op) Progress() (done, total int) {
	for _, s := range o.Steps {
		if s.State == StepDone || s.State == StepSkipped {
			done++
		}
	}
	return done, len(o.Steps)
}

func (o *Op) clone() *Op {
	b, _ := json.Marshal(o)
	var c Op
	_ = json.Unmarshal(b, &c)
	return &c
}

var idRe = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`)

// ValidID reports whether id can name an operation (and its journal file).
func ValidID(id string) bool { return idRe.MatchString(id) }

// Store keeps one JSON file per operation in Dir. Every write goes to a temp
// file that is fsynced and renamed, then the directory is fsynced, so after a
// power cut a record is either the old or the new version, never torn.
type Store struct {
	Dir  string
	lock *os.File
}

// OpenStore creates Dir and takes an exclusive lock on it: a second onemindd
// storage service on the same set refuses to start.
func OpenStore(dir string) (*Store, error) {
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(filepath.Join(dir, "lock"), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		return nil, fmt.Errorf("storage journal %s is in use by another process: %w", dir, err)
	}
	return &Store{Dir: dir, lock: f}, nil
}

// Close releases the lock.
func (s *Store) Close() error {
	if s.lock == nil {
		return nil
	}
	return s.lock.Close()
}

func (s *Store) path(id string) string { return filepath.Join(s.Dir, "op-"+id+".json") }

// Save writes op durably.
func (s *Store) Save(op *Op) error {
	if !ValidID(op.ID) {
		return fmt.Errorf("bad operation id %q", op.ID)
	}
	b, err := json.MarshalIndent(op, "", " ")
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(s.Dir, ".op-*.tmp")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(b); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp.Name(), s.path(op.ID)); err != nil {
		return err
	}
	d, err := os.Open(s.Dir)
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}

// ErrNotFound is returned for an unknown operation id.
var ErrNotFound = errors.New("no such operation")

// Load reads one operation.
func (s *Store) Load(id string) (*Op, error) {
	if !ValidID(id) {
		return nil, ErrNotFound
	}
	b, err := os.ReadFile(s.path(id))
	if errors.Is(err, os.ErrNotExist) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	var op Op
	if err := json.Unmarshal(b, &op); err != nil {
		return nil, fmt.Errorf("journal %s: %w", id, err)
	}
	return &op, nil
}

// List returns every operation, newest first.
func (s *Store) List() ([]*Op, error) {
	ents, err := os.ReadDir(s.Dir)
	if err != nil {
		return nil, err
	}
	var out []*Op
	for _, e := range ents {
		n := e.Name()
		if !strings.HasPrefix(n, "op-") || !strings.HasSuffix(n, ".json") {
			continue
		}
		op, err := s.Load(strings.TrimSuffix(strings.TrimPrefix(n, "op-"), ".json"))
		if err != nil {
			return nil, err
		}
		out = append(out, op)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].CreatedAt.After(out[j].CreatedAt) })
	return out, nil
}
