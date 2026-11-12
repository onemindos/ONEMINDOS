// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io/fs"
	"log/slog"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// ErrBusy means another backup job holds the agent.
var ErrBusy = errors.New("another backup job is running")

// Agent is the onemindd backup agent for one node.
type Agent struct {
	Cfg   Config
	Store *Store
	// OpenRepo returns the repository client for a target.
	OpenRepo func(Target) (Repo, error)
	// Units returns what to back up now. The default reads the config; the
	// gateway coordinator (K3) replaces the app list per job.
	Units     func(ctx context.Context) ([]Unit, error)
	Now       func() time.Time
	FreeBytes func(path string) (int64, error)
	IsMount   func(path string) (bool, error)
	Log       *slog.Logger
	// Jobs verifies the gateway's signed jobs (job.go); nil refuses them.
	Jobs *JobVerifier

	lock    chan struct{}
	running atomic.Value // run id of the job in progress ("" = idle)
	// cfgMu guards Cfg.Targets and Cfg.Units.Apps, which the gateway can
	// replace at run time (managed.go). Read them through conf().
	cfgMu sync.RWMutex
}

// New builds an agent from validated settings: it checks the restic binary
// against its pin (unless skip_pin_check), opens the state file and wires
// the real restic runner.
func New(cfg Config) (*Agent, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if !cfg.Restic.SkipPinCheck {
		p, ok := PinFor("restic", runtime.GOARCH)
		if !ok {
			return nil, fmt.Errorf("no restic pin for %s", runtime.GOARCH)
		}
		if err := VerifyBinary(cfg.Restic.Binary, p); err != nil {
			return nil, err
		}
	}
	if err := checkKeyFile(cfg.DeviceKeyFile); err != nil {
		return nil, err
	}
	st, err := OpenStore(filepath.Join(cfg.StateDir, "state.json"))
	if err != nil {
		return nil, err
	}
	a := newAgent(cfg, st)
	a.OpenRepo = func(t Target) (Repo, error) { c := a.conf(); return NewRestic(&c, t, ExecRunner{}) }
	a.Units = func(context.Context) ([]Unit, error) { c := a.conf(); return BuildUnits(&c, ExecRunner{}), nil }
	a.Jobs = &JobVerifier{PubKeyFile: cfg.JobPubKeyFile, DonePath: filepath.Join(cfg.StateDir, "jobs-done.json"),
		Now: func() time.Time { return a.Now() }}
	return a, nil
}

func newAgent(cfg Config, st *Store) *Agent {
	a := &Agent{Cfg: cfg, Store: st, Now: time.Now, FreeBytes: freeBytes, IsMount: isMountPoint,
		Log: slog.Default(), lock: make(chan struct{}, 1)}
	a.running.Store("")
	return a
}

func (a *Agent) tryAcquire(id string) bool {
	select {
	case a.lock <- struct{}{}:
		a.running.Store(id)
		return true
	default:
		return false
	}
}

func (a *Agent) acquire(ctx context.Context, id string) error {
	select {
	case a.lock <- struct{}{}:
		a.running.Store(id)
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (a *Agent) release() { a.running.Store(""); <-a.lock }

// Running returns the id of the job in progress, or "".
func (a *Agent) Running() string { return a.running.Load().(string) }

// NewRunID returns a sortable run id.
func NewRunID(now time.Time) string {
	var b [3]byte
	_, _ = rand.Read(b[:])
	return "run_" + now.UTC().Format("20060102T150405Z") + "_" + hex.EncodeToString(b[:])
}

// RunRequest asks for one backup run.
type RunRequest struct {
	ID       string // optional; generated when empty
	Reason   string
	ActionID string
	TargetID string   // empty = primary
	Units    []string // empty = all units
	// Wait blocks until another job finishes instead of returning ErrBusy.
	Wait bool
}

// keepClass maps a run reason to the retention rule its snapshots follow.
// Scheduled and manual snapshots share the ladder; safety snapshots taken
// before risky changes are kept by age so the ladder never thins them out.
func keepClass(reason string) string {
	switch reason {
	case ReasonPreUpdate, ReasonPreRestore:
		return "14d"
	case ReasonPreDelete:
		return "30d"
	}
	return "ladder"
}

// Run takes one snapshot per unit into the target and applies retention.
func (a *Agent) Run(ctx context.Context, req RunRequest) (Run, error) {
	switch req.Reason {
	case ReasonScheduled, ReasonManual, ReasonPreUpdate, ReasonPreRestore, ReasonPreDelete:
	default:
		return Run{}, fmt.Errorf("unknown reason %q", req.Reason)
	}
	if req.ID == "" {
		req.ID = NewRunID(a.Now())
	}
	if req.Wait {
		if err := a.acquire(ctx, req.ID); err != nil {
			return Run{}, err
		}
	} else if !a.tryAcquire(req.ID) {
		return Run{}, ErrBusy
	}
	defer a.release()
	return a.runLocked(ctx, req)
}

func (a *Agent) runLocked(ctx context.Context, req RunRequest) (Run, error) {
	t, ok := a.target(req.TargetID)
	if !ok {
		return Run{}, fmt.Errorf("no target %q", req.TargetID)
	}
	run := Run{ID: req.ID, Reason: req.Reason, ActionID: req.ActionID, TargetID: t.ID,
		StartedAt: a.Now().UTC(), State: StateRunning, Units: []UnitResult{}}
	_ = a.Store.Update(func(s *State) { s.Runs = append(s.Runs, run) })
	finish := func(state, msg string) (Run, error) {
		end := a.Now().UTC()
		run.FinishedAt, run.State, run.Error = &end, state, msg
		err := a.Store.Update(func(s *State) {
			for i := range s.Runs {
				if s.Runs[i].ID == run.ID {
					s.Runs[i] = run
				}
			}
		})
		a.Log.Info("backup run finished", "run", run.ID, "target", t.ID, "state", state, "error", msg)
		return run, err
	}

	if f := a.Store.View().FencedBy; f > a.Cfg.Generation {
		return finish(StateRefused, fmt.Sprintf("this box was replaced by a restore (generation %d); backups stopped", f))
	}
	units, err := a.selectUnits(ctx, req.Units)
	if err != nil {
		return finish(StateFailed, err.Error())
	}
	repo, err := a.readyRepo(ctx, t)
	if err != nil {
		return finish(StateFailed, err.Error())
	}
	if gen, err := a.newestFence(ctx, repo); err != nil {
		return finish(StateFailed, "fence check: "+err.Error())
	} else if gen > a.Cfg.Generation {
		_ = a.Store.Update(func(s *State) { s.FencedBy = gen })
		return finish(StateRefused, fmt.Sprintf("this box was replaced by a restore (generation %d is newer than %d); backups stopped", gen, a.Cfg.Generation))
	}
	srcBytes := sourceBytes(units)
	if msg := a.spaceCheck(t, srcBytes); msg != "" {
		return finish(StateRefused, msg)
	}

	succeeded, failed := 0, 0
	for _, u := range units {
		res := a.backupUnit(ctx, repo, run, u)
		run.Units = append(run.Units, res.UnitResult)
		run.BytesAdded += res.added
		if res.State == StateSucceeded {
			succeeded++
		} else {
			failed++
		}
		if ctx.Err() != nil {
			break
		}
	}
	if !t.AppendOnly {
		for _, u := range units {
			if err := a.forget(ctx, repo, u.Name, keepClass(req.Reason)); err != nil {
				a.Log.Warn("retention failed", "unit", u.Name, "error", err)
			}
		}
	}
	_ = a.Store.Update(func(s *State) { s.SourceBytes[t.ID] = srcBytes })
	switch {
	case failed == 0:
		return finish(StateSucceeded, "")
	case succeeded == 0:
		return finish(StateFailed, "every unit failed")
	default:
		return finish(StatePartial, "")
	}
}

func (a *Agent) target(id string) (Target, bool) {
	c := a.conf()
	if id == "" {
		return c.Primary()
	}
	return c.Target(id)
}

func (a *Agent) selectUnits(ctx context.Context, names []string) ([]Unit, error) {
	all, err := a.Units(ctx)
	if err != nil {
		return nil, err
	}
	if len(names) == 0 {
		return all, nil
	}
	var out []Unit
	for _, n := range names {
		found := false
		for _, u := range all {
			if u.Name == n {
				out, found = append(out, u), true
			}
		}
		if !found {
			return nil, fmt.Errorf("unknown unit %q", n)
		}
	}
	return out, nil
}

// readyRepo opens the target and creates the repository on first use. A
// USB target must be a mounted disk: if the disk is unplugged the mount
// directory is an empty folder on the system disk, and writing there would
// fill /data with a backup that is not where the owner thinks it is.
func (a *Agent) readyRepo(ctx context.Context, t Target) (Repo, error) {
	if t.Kind == KindUSB && !t.AllowNonMountDir {
		mount := filepath.Join(t.MountRoot, t.USBUUID)
		if m, err := a.IsMount(mount); err != nil || !m {
			return nil, fmt.Errorf("backup disk %s is not mounted", t.USBUUID)
		}
	}
	repo, err := a.OpenRepo(t)
	if err != nil {
		return nil, err
	}
	if err := repo.Init(ctx); err != nil {
		return nil, err
	}
	return repo, nil
}

func (a *Agent) baseTags(unit string) []string {
	return []string{"onemind", "box=" + a.Cfg.BoxID, "gen=" + strconv.Itoa(a.Cfg.Generation),
		"unit=" + unit, "node=" + a.Cfg.NodeID}
}

type unitOutcome struct {
	UnitResult
	added int64
}

func (a *Agent) backupUnit(ctx context.Context, repo Repo, run Run, u Unit) unitOutcome {
	out := unitOutcome{UnitResult: UnitResult{Unit: u.Name, State: StateFailed}}
	fail := func(err error) unitOutcome {
		out.Error = err.Error()
		a.Log.Warn("backup unit failed", "unit", u.Name, "error", err)
		return out
	}
	for _, p := range u.Paths {
		if _, err := os.Lstat(p); err != nil {
			return fail(fmt.Errorf("source %s: %w", p, err))
		}
	}
	tags := append(a.baseTags(u.Name), "run="+run.ID, "reason="+run.Reason, "keep="+keepClass(run.Reason))
	tags = append(tags, u.Tags...)
	paths := append([]string{}, u.Paths...)
	if len(u.Hooks) > 0 {
		staging := filepath.Join(a.Cfg.StateDir, "staging", stagingName(u.Name))
		if err := os.RemoveAll(staging); err != nil {
			return fail(err)
		}
		if err := os.MkdirAll(staging, 0o700); err != nil {
			return fail(err)
		}
		defer os.RemoveAll(staging)
		for _, h := range u.Hooks {
			extra, err := h.Prepare(ctx, staging)
			if err != nil {
				return fail(err)
			}
			tags = append(tags, extra...)
		}
		paths = append(paths, staging)
	}
	if len(paths) == 0 {
		return fail(errors.New("unit has nothing to back up"))
	}
	res, err := repo.Backup(ctx, BackupRequest{Paths: paths, Excludes: u.Excludes, Tags: tags, Host: a.Cfg.NodeID})
	if err != nil {
		return fail(err)
	}
	out.SnapshotID, out.added = res.SnapshotID, res.DataAdded
	if res.Incomplete {
		return fail(errors.New("snapshot made, but some files could not be read"))
	}
	out.State = StateSucceeded
	return out
}

// RetentionArgs returns restic keep flags for a keep class.
func (r Retention) Args(class string) []string {
	switch class {
	case "14d":
		return []string{"--keep-within", "14d"}
	case "30d":
		return []string{"--keep-within", "30d"}
	}
	var args []string
	for _, k := range []struct {
		flag string
		n    int
	}{{"--keep-hourly", r.Hourly}, {"--keep-daily", r.Daily}, {"--keep-weekly", r.Weekly}, {"--keep-monthly", r.Monthly}} {
		if k.n > 0 {
			args = append(args, k.flag, strconv.Itoa(k.n))
		}
	}
	return args
}

// forget applies one keep class to one unit of this box. The filter always
// names the box, so boxes sharing a bucket never thin out each other.
func (a *Agent) forget(ctx context.Context, repo Repo, unit, class string) error {
	filter := []string{"onemind", "box=" + a.Cfg.BoxID, "unit=" + unit, "keep=" + class}
	return repo.Forget(ctx, filter, a.Cfg.Retention.Args(class))
}

// newestFence returns the highest generation written as a fence record for
// this box (BACKUPS.md §7.3 step 5), or 0.
func (a *Agent) newestFence(ctx context.Context, repo Repo) (int, error) {
	snaps, err := repo.Snapshots(ctx, []string{"onemind", "box=" + a.Cfg.BoxID, "unit=fence"})
	if err != nil {
		return 0, err
	}
	max := 0
	for _, s := range snaps {
		if g, err := strconv.Atoi(s.Tag("gen")); err == nil && g > max {
			max = g
		}
	}
	return max, nil
}

// WriteFence records this box's generation on a target. A whole-box restore
// calls it on every target after it bumps the generation, so the replaced
// box stops at its next run.
func (a *Agent) WriteFence(ctx context.Context, targetID string) error {
	t, ok := a.target(targetID)
	if !ok {
		return fmt.Errorf("no target %q", targetID)
	}
	repo, err := a.readyRepo(ctx, t)
	if err != nil {
		return err
	}
	body := fmt.Sprintf("generation=%d\n", a.Cfg.Generation)
	_, err = repo.BackupStdin(ctx, "fence", strings.NewReader(body), a.baseTags("fence"), a.Cfg.NodeID)
	return err
}

// spaceCheck refuses a run when a local target has less than twice the
// estimated new data free (BACKUPS.md §3). The estimate is the growth of the
// sources since the last run plus 10 %; the first run counts everything.
// Remote targets do not report free space, so they are not checked here.
func (a *Agent) spaceCheck(t Target, src int64) string {
	if t.Kind != KindUSB {
		return ""
	}
	last, seen := a.Store.View().SourceBytes[t.ID]
	growth := src
	if seen {
		growth = max(src-last, 0)
	}
	need := 2 * (growth + growth/10)
	free, err := a.FreeBytes(filepath.Join(t.MountRoot, t.USBUUID))
	if err != nil {
		return "" // unknown free space never blocks a backup
	}
	if free < need {
		return fmt.Sprintf("not enough space on the backup disk: %d bytes free, %d bytes needed", free, need)
	}
	return ""
}

// sourceBytes sums the apparent size of every regular file in the units.
func sourceBytes(units []Unit) int64 {
	var n int64
	for _, u := range units {
		for _, p := range u.Paths {
			_ = filepath.WalkDir(p, func(_ string, d fs.DirEntry, err error) error {
				if err == nil && d.Type().IsRegular() {
					if fi, err := d.Info(); err == nil {
						n += fi.Size()
					}
				}
				return nil
			})
		}
	}
	return n
}

func checkKeyFile(path string) error {
	fi, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("device key: %w", err)
	}
	if fi.Mode().Perm()&0o077 != 0 {
		return fmt.Errorf("device key %s must not be readable by group or others (mode %o)", path, fi.Mode().Perm())
	}
	if fi.Size() == 0 {
		return fmt.Errorf("device key %s is empty", path)
	}
	return nil
}

// GenerateKey writes a new 256-bit random repository key to path (0600),
// refusing to overwrite. Keys are never derived from a password (W5-R4).
func GenerateKey(path string) error {
	var b [32]byte
	if _, err := rand.Read(b[:]); err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err := f.WriteString(hex.EncodeToString(b[:]) + "\n"); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}

// Heartbeat returns the heartbeat `backup` object.
func (a *Agent) Heartbeat() Heartbeat {
	h := HeartbeatFromState(a.Store.View())
	h.Running = a.Running() != ""
	return h
}

// HeartbeatFromState builds the heartbeat `backup` object from the state
// file alone, for the heartbeat agent, which runs in another process.
// last_result is succeeded|failed|partial|none (contract §12.10); a run
// refused by the space check or the fence reports failed.
func HeartbeatFromState(st State) Heartbeat {
	h := Heartbeat{LastResult: "none"}
	for i := len(st.Runs) - 1; i >= 0; i-- {
		r := st.Runs[i]
		if r.State == StateRunning {
			h.Running = true
			continue
		}
		at := r.StartedAt.UTC().Format(time.RFC3339)
		h.LastRunAt, h.LastResult = &at, r.State
		if r.State == StateRefused {
			h.LastResult = StateFailed
		}
		break
	}
	return h
}

// Status is the agent's part of GET /v1/backups/status: badges for the
// units it backs up, the last run and the next hourly run.
type Status struct {
	Box          Badge                   `json:"box"`
	Units        map[string]Badge        `json:"units"`
	LastRun      *Run                    `json:"last_run"`
	NextRun      time.Time               `json:"next_run"`
	Running      string                  `json:"running,omitempty"`
	Generation   int                     `json:"generation"`
	Fenced       bool                    `json:"fenced"`
	Copies       int                     `json:"copies"`
	LastVerified map[string]Verification `json:"last_verified"`
}

// Status computes the current status.
func (a *Agent) Status(ctx context.Context) (Status, error) {
	now := a.Now()
	st := a.Store.View()
	units, err := a.Units(ctx)
	if err != nil {
		return Status{}, err
	}
	s := Status{Units: map[string]Badge{}, NextRun: a.nextHourly(now), Running: a.Running(),
		Generation: a.Cfg.Generation, Fenced: st.FencedBy > a.Cfg.Generation, Copies: len(a.conf().Targets),
		LastVerified: st.LastVerified}
	order := map[string]int{BadgeFailing: 4, BadgeStale: 3, BadgeUnverified: 2, BadgeVerified: 1, BadgeNone: 0}
	s.Box.State = BadgeNone
	for _, u := range units {
		b := st.UnitBadge(u.Name, now)
		s.Units[u.Name] = b
		if order[b.State] > order[s.Box.State] {
			s.Box = b
		}
	}
	if s.Fenced {
		s.Box = Badge{State: BadgeFailing, Reason: "this box was replaced by a restore"}
	}
	for i := len(st.Runs) - 1; i >= 0; i-- {
		if st.Runs[i].State != StateRunning {
			r := st.Runs[i]
			s.LastRun = &r
			break
		}
	}
	return s, nil
}
