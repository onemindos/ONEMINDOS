// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
)

// Facts is what the engine reads about the box. CollectorFacts reads the
// real tools; tests use a simulated box.
type Facts interface {
	Mirror(ctx context.Context, mount string) (*storage.Mirror, error)
	// Disks lists whole disks and fills m's LUKS facts (backing, generation).
	Disks(ctx context.Context, m *storage.Mirror) ([]storage.Disk, error)
	Health(ctx context.Context, d storage.Disk) (storage.Health, error)
}

// CollectorFacts adapts storage.Collector.
type CollectorFacts struct{ C *storage.Collector }

// Mirror implements Facts.
func (f CollectorFacts) Mirror(ctx context.Context, mount string) (*storage.Mirror, error) {
	return f.C.MirrorStatus(ctx, mount)
}

// Disks implements Facts.
func (f CollectorFacts) Disks(ctx context.Context, m *storage.Mirror) ([]storage.Disk, error) {
	ds, err := f.C.Inventory(ctx, m)
	if err == nil && m != nil && m.State != storage.StateUnavailable {
		f.C.LUKS(ctx, m, ds)
	}
	return ds, err
}

// Health implements Facts.
func (f CollectorFacts) Health(ctx context.Context, d storage.Disk) (storage.Health, error) {
	return f.C.Health(ctx, d, storage.DefaultThresholds)
}

// Errors the API maps to HTTP codes.
var (
	ErrBusy      = errors.New("another storage operation is running")
	ErrNoJournal = errors.New("the data set is not mounted, so storage operations are unavailable")
	ErrNoPlanSHA = errors.New("plan_sha256 is required: an operation runs only the plan the owner approved")
)

// PlanError carries the fresh plan when it is blocked or differs from the
// approved one (code "blocked" or "stale_precondition").
type PlanError struct {
	Code string
	Plan storage.Plan
}

func (e *PlanError) Error() string {
	if e.Code == "blocked" {
		return "the plan is blocked by a failed check"
	}
	return "the plan changed since it was approved"
}

// Ref says how to find a device path again after a reboot.
type Ref struct {
	Kind string `json:"kind"` // part (by PARTUUID), disk (by stable id or the target's PARTUUID), mapper (crypt child of a PARTUUID)
	Key  string `json:"key"`
}

// Engine runs operations one at a time.
type Engine struct {
	Facts   Facts
	Run     Runner
	Store   *Store // nil while the data set is not mounted
	Mount   string
	Options storage.PlanOptions // KeyFile override for labs; Mount is always Engine.Mount
	Log     *slog.Logger
	Now     func() time.Time
	Poll    time.Duration // status polling while a balance or replace runs in the kernel
	// Context is the lifetime of the service; operations run on it, not on
	// the request that started them. Cancelling it stops an operation the
	// way a power cut would: the journal says where to pick up.
	Context context.Context
	// OnChange, when set, sees a copy of the operation after every journal write.
	OnChange func(Op)
	// HoldDir, when set, is the fault-injection point of the power-cut
	// battery (STOR-4, research-output/evidence/lab/storage-actions): while
	// HoldDir/hold-before-<step id> exists the engine waits before that step,
	// so a lab can cut power at an exact point. Root-only tmpfs in production.
	HoldDir string

	mu     sync.Mutex
	active *Op
	wg     sync.WaitGroup
}

func (e *Engine) now() time.Time {
	if e.Now != nil {
		return e.Now().UTC()
	}
	return time.Now().UTC()
}

func (e *Engine) log() *slog.Logger {
	if e.Log != nil {
		return e.Log
	}
	return slog.New(slog.NewTextHandler(os.Stderr, nil))
}

func (e *Engine) poll() time.Duration {
	if e.Poll > 0 {
		return e.Poll
	}
	return 5 * time.Second
}

func (e *Engine) keyFile() string {
	if e.Options.KeyFile != "" {
		return e.Options.KeyFile
	}
	return e.Mount + "/" + storage.SetKeyPath
}

// Wait blocks until running operations return (tests, shutdown).
func (e *Engine) Wait() { e.wg.Wait() }

// Plan renders the plan for req from a fresh inventory. Nothing changes.
func (e *Engine) Plan(ctx context.Context, req Request) (storage.Plan, error) {
	m, err := e.Facts.Mirror(ctx, e.Mount)
	if err != nil {
		return storage.Plan{}, err
	}
	disks, err := e.Facts.Disks(ctx, m)
	if err != nil {
		return storage.Plan{}, err
	}
	o := e.Options
	o.Mount = e.Mount
	o.KeyFile = e.keyFile()
	o.Health = map[string]storage.Health{}
	if req.Device != "" {
		if d, ok := storage.Find(disks, req.Device); ok {
			if h, err := e.Facts.Health(ctx, d); err == nil {
				o.Health[d.Path] = h
			}
		}
	}
	n := len(m.Members)
	var p storage.Plan
	switch req.Kind {
	case KindCreate:
		p = storage.WithChecks(storage.PlanProtect(disks, m, req.Device, o),
			storage.Check{ID: "kind:create", OK: n == 1, Detail: fmt.Sprintf("the set has %d members; create turns one disk into a mirror, add grows a mirror", n)})
	case KindAdd:
		p = storage.WithChecks(storage.PlanProtect(disks, m, req.Device, o),
			storage.Check{ID: "kind:add", OK: n >= 2, Detail: fmt.Sprintf("the set has %d members; add grows a mirror, create makes one", n)})
	case KindReplace:
		p = storage.PlanReplace(disks, m, req.Member, req.Device, req.Wipe, o)
	case KindRemove:
		p = storage.PlanRemove(disks, m, req.Member, req.Unprotect, req.Wipe, o)
	case KindRepair:
		p = storage.PlanRepair(m)
	default:
		return storage.Plan{}, fmt.Errorf("unknown kind %q (create, add, replace, remove, repair)", req.Kind)
	}
	if usesKey(p, o.KeyFile) {
		_, err := os.Stat(o.KeyFile)
		p = storage.WithChecks(p, storage.Check{ID: "set-key", OK: err == nil, Detail: "the set key opens the new member: " + o.KeyFile})
	}
	return p, nil
}

func usesKey(p storage.Plan, key string) bool {
	for _, s := range p.Steps {
		for _, a := range s.Cmd {
			if a == key {
				return true
			}
		}
	}
	return false
}

// Start checks req against a fresh plan and runs it in the background.
// The same ActionID twice returns the first operation (idempotent).
func (e *Engine) Start(ctx context.Context, req Request) (*Op, error) {
	if e.Store == nil {
		return nil, ErrNoJournal
	}
	if req.ActionID != "" && !ValidID(req.ActionID) {
		return nil, fmt.Errorf("bad action_id %q", req.ActionID)
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if req.ActionID != "" {
		if op, err := e.Store.Load(req.ActionID); err == nil {
			return op.clone(), nil
		}
	}
	if e.active != nil && e.active.Busy() {
		return nil, ErrBusy
	}
	if req.PlanSHA256 == "" {
		return nil, ErrNoPlanSHA
	}
	p, err := e.Plan(ctx, req)
	if err != nil {
		return nil, err
	}
	if p.Blocked {
		return nil, &PlanError{Code: "blocked", Plan: p}
	}
	if p.SHA256 != req.PlanSHA256 {
		return nil, &PlanError{Code: "stale_precondition", Plan: p}
	}
	id := req.ActionID
	if id == "" {
		var b [6]byte
		_, _ = rand.Read(b[:])
		id = "op_" + e.now().Format("20060102T150405") + "_" + hex.EncodeToString(b[:])
	}
	now := e.now()
	op := &Op{ID: id, Request: req, Plan: p, State: StateRunning, Steps: make([]StepRun, len(p.Steps)), CreatedAt: now, UpdatedAt: now}
	for i := range op.Steps {
		op.Steps[i].State = StepPending
	}
	m, _ := e.Facts.Mirror(ctx, e.Mount)
	disks, _ := e.Facts.Disks(ctx, m)
	op.Targets, op.Refs = targetsAndRefs(p, disks)
	if err := e.save(op); err != nil {
		return nil, err
	}
	e.active = op
	e.log().Info("storage operation started", "op", op.ID, "kind", req.Kind, "plan_sha256", p.SHA256, "steps", len(p.Steps))
	e.spawn(op)
	return op.clone(), nil
}

func (e *Engine) spawn(op *Op) {
	ctx := e.Context
	if ctx == nil {
		ctx = context.Background()
	}
	e.wg.Add(1)
	go func() {
		defer e.wg.Done()
		e.execute(ctx, op)
	}()
}

// Get returns one operation.
func (e *Engine) Get(id string) (*Op, error) {
	if e.Store == nil {
		return nil, ErrNoJournal
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.active != nil && e.active.ID == id {
		return e.active.clone(), nil
	}
	return e.Store.Load(id)
}

// Active returns the running operation, if any.
func (e *Engine) Active() *Op {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.active != nil && e.active.Busy() {
		return e.active.clone()
	}
	return nil
}

func (e *Engine) save(op *Op) error {
	op.UpdatedAt = e.now()
	if err := e.Store.Save(op); err != nil {
		e.log().Error("storage journal write failed", "op", op.ID, "err", err)
		return err
	}
	if e.OnChange != nil {
		e.OnChange(*op.clone())
	}
	return nil
}

// update runs fn on the operation under the lock and journals it.
func (e *Engine) update(op *Op, fn func()) {
	e.mu.Lock()
	defer e.mu.Unlock()
	fn()
	_ = e.save(op)
}

func (e *Engine) finish(op *Op, state, msg string) {
	e.update(op, func() {
		now := e.now()
		op.State, op.FinishedAt = state, &now
		if msg != "" {
			op.Error = msg
		}
	})
	e.log().Info("storage operation finished", "op", op.ID, "state", state, "error", msg)
}

// execute runs the steps from op.Next. It returns without touching the
// journal when ctx ends (shutdown or a simulated power cut): the step that
// was running stays "running" and Resume decides what to do with it.
func (e *Engine) execute(ctx context.Context, op *Op) {
	for op.Next < len(op.Plan.Steps) {
		if ctx.Err() != nil {
			return
		}
		i := op.Next
		st := op.Plan.Steps[i]
		run, note, err := e.probe(ctx, op, i)
		if ctx.Err() != nil {
			return
		}
		if err != nil {
			e.fail(ctx, op, i, fmt.Sprintf("step %d %s: %v", i+1, st.ID, err))
			return
		}
		if !run {
			e.update(op, func() {
				now := e.now()
				op.Steps[i].State, op.Steps[i].Note, op.Steps[i].FinishedAt = StepSkipped, note, &now
				op.Next = i + 1
			})
			continue
		}
		if !e.hold(ctx, st.ID) {
			return
		}
		if len(st.Cmd) == 0 || !allowed[st.Cmd[0]] {
			e.fail(ctx, op, i, fmt.Sprintf("step %d %s: program not allowed", i+1, st.ID))
			return
		}
		e.update(op, func() {
			now := e.now()
			sr := &op.Steps[i]
			sr.State, sr.StartedAt, sr.FinishedAt, sr.Note = StepRunning, &now, nil, note
			sr.Attempts++
		})
		out, exit, err := e.Run.Exec(ctx, st.Stdin, st.Cmd[0], st.Cmd[1:]...)
		if ctx.Err() != nil {
			return
		}
		ok := err == nil && exit == 0
		msg := ""
		if err != nil {
			msg = err.Error()
		}
		if ok && st.ID == "verify" {
			if bad := verifyProfiles(out, op.Plan); bad != "" {
				ok, msg = false, bad
			}
		}
		e.update(op, func() {
			now := e.now()
			sr := &op.Steps[i]
			sr.Exit, sr.Output, sr.FinishedAt = exit, tail(out, 2000), &now
			if msg != "" {
				sr.Note = msg
			}
			if ok {
				sr.State = StepDone
				op.Next = i + 1
			} else {
				sr.State = StepFailed
			}
		})
		if !ok {
			why := fmt.Sprintf("step %d %s exited %d", i+1, st.ID, exit)
			if msg != "" {
				why += ": " + msg
			}
			e.fail(ctx, op, i, why)
			return
		}
	}
	e.finish(op, StateSucceeded, "")
}

// fail rolls back when nothing has moved yet (prepare and join steps), else
// stops forward-only: commit steps are restartable, the set stays usable.
func (e *Engine) fail(ctx context.Context, op *Op, i int, why string) {
	switch op.Plan.Steps[i].Phase {
	case storage.PhasePrepare, storage.PhaseJoin:
		e.rollback(ctx, op, why)
	default:
		e.finish(op, StateFailed, why)
	}
}

// Resume picks up what a power cut or crash interrupted. Call once at start,
// before serving requests.
func (e *Engine) Resume(ctx context.Context) error {
	if e.Store == nil {
		return nil
	}
	all, err := e.Store.List()
	if err != nil {
		return err
	}
	var op *Op
	for _, o := range all {
		if !o.Busy() {
			continue
		}
		if op != nil { // more than one: should never happen; keep the newest
			e.finish(o, StateNeedsAttention, "found running next to "+op.ID+" after a restart")
			continue
		}
		op = o
	}
	if op == nil {
		return nil
	}
	e.mu.Lock()
	e.active = op
	op.Resumes++
	e.mu.Unlock()
	e.log().Warn("resuming storage operation after a restart", "op", op.ID, "state", op.State, "next", op.Next, "resumes", op.Resumes)
	if op.State == StateRollingBack {
		e.wg.Add(1)
		go func() { defer e.wg.Done(); e.rollback(ctx, op, op.Error) }()
		return nil
	}
	phase := ""
	if op.Next < len(op.Plan.Steps) {
		phase = op.Plan.Steps[op.Next].Phase
	}
	if err := e.relocate(ctx, op); err != nil {
		why := "after a restart: " + err.Error()
		if phase == storage.PhasePrepare || phase == storage.PhaseJoin {
			e.wg.Add(1)
			go func() { defer e.wg.Done(); e.rollback(ctx, op, why) }()
		} else {
			e.finish(op, StateNeedsAttention, why)
		}
		return nil
	}
	if phase == storage.PhasePrepare {
		// Prepare steps are not individually restartable (the header copy in
		// /run is gone after a reboot, a partition cannot be created twice),
		// but the target is not in the set yet: start the prepare phase over.
		if err := e.restartPrepare(ctx, op); err != nil {
			e.wg.Add(1)
			go func() { defer e.wg.Done(); e.rollback(ctx, op, "after a restart: "+err.Error()) }()
			return nil
		}
	} else if err := e.reopen(ctx, op); err != nil {
		e.finish(op, StateNeedsAttention, "after a restart: "+err.Error())
		return nil
	}
	e.update(op, func() {})
	e.spawn(op)
	return nil
}

func (e *Engine) restartPrepare(ctx context.Context, op *Op) error {
	first := -1
	for i, s := range op.Plan.Steps {
		if s.Phase == storage.PhasePrepare {
			first = i
			break
		}
	}
	m, err := e.Facts.Mirror(ctx, e.Mount)
	if err != nil {
		return err
	}
	for _, s := range op.Plan.Steps {
		if s.ID == "device-add" && isMember(m, s.Cmd[3]) {
			return fmt.Errorf("the new disk is already in the set before its prepare steps finished")
		}
	}
	// Close any mapping on the target (ours, or one a boot opened under
	// another name) before wiping under it.
	disks, err := e.Facts.Disks(ctx, m)
	if err != nil {
		return err
	}
	for _, t := range op.Targets {
		d, ok := storage.Find(disks, t.Path)
		if !ok {
			continue
		}
		if c, ok := storage.CryptChild(d, t.Part); ok {
			if out, code, err := e.Run.Exec(ctx, "", "cryptsetup", "close", c.Path); err != nil || code != 0 {
				return fmt.Errorf("cryptsetup close %s: %s", c.Path, tail(out, 200))
			}
		}
	}
	e.update(op, func() {
		for j := first; j < op.Next && j < len(op.Steps); j++ {
			op.Steps[j].State, op.Steps[j].Note = StepPending, "prepare phase restarted after a restart"
		}
		if op.Next < len(op.Steps) {
			op.Steps[op.Next].State = StepPending
		}
		op.Next = first
	})
	return nil
}

// reopen re-opens the new member's dm-crypt mapping when a reboot closed it
// and the operation is past its prepare phase. When the boot assembly already
// opened it under its own name, the operation adopts that mapping instead.
func (e *Engine) reopen(ctx context.Context, op *Op) error {
	for j := 0; j < op.Next && j < len(op.Plan.Steps); j++ {
		s := op.Plan.Steps[j]
		if s.ID != "luks-open" {
			continue
		}
		name, part := s.Cmd[len(s.Cmd)-1], s.Cmd[len(s.Cmd)-2]
		if _, code, err := e.Run.Exec(ctx, "", "cryptsetup", "status", name); err == nil && code == 0 {
			continue
		}
		m, err := e.Facts.Mirror(ctx, e.Mount)
		if err != nil {
			return err
		}
		disks, err := e.Facts.Disks(ctx, m)
		if err != nil {
			return err
		}
		if d, _, ok := containingPart(disks, part); ok {
			if c, ok := storage.CryptChild(d, part); ok {
				e.substitute(op, map[string]string{"/dev/mapper/" + name: c.Path})
				continue
			}
		}
		if out, code, err := e.Run.Exec(ctx, s.Stdin, s.Cmd[0], s.Cmd[1:]...); err != nil || code != 0 {
			return fmt.Errorf("re-open %s: %s", name, tail(out, 200))
		}
	}
	return nil
}

func containingPart(disks []storage.Disk, part string) (storage.Disk, storage.Signature, bool) {
	for _, d := range disks {
		for _, s := range d.Holds {
			if s.Path == part {
				return d, s, true
			}
		}
	}
	return storage.Disk{}, storage.Signature{}, false
}

// probe decides whether step i must run, and waits for kernel work a power
// cut left behind (btrfs resumes a balance and a replace at mount).
func (e *Engine) probe(ctx context.Context, op *Op, i int) (run bool, note string, err error) {
	s := op.Plan.Steps[i]
	mount := op.Plan.Mount
	switch s.ID {
	case "device-add":
		m, err := e.Facts.Mirror(ctx, mount)
		if err != nil {
			return false, "", err
		}
		if isMember(m, s.Cmd[3]) {
			return false, s.Cmd[3] + " is already a member", nil
		}
	case "device-remove":
		m, err := e.Facts.Mirror(ctx, mount)
		if err != nil {
			return false, "", err
		}
		if !hasDevice(m, s.Cmd[3]) {
			return false, "devid " + s.Cmd[3] + " already left the set", nil
		}
	case "luks-open":
		if _, code, err := e.Run.Exec(ctx, "", "cryptsetup", "status", s.Cmd[len(s.Cmd)-1]); err == nil && code == 0 {
			return false, "already open", nil
		}
	case "old-close":
		if _, code, err := e.Run.Exec(ctx, "", "cryptsetup", "status", s.Cmd[len(s.Cmd)-1]); err == nil && code != 0 {
			return false, "already closed", nil
		}
	case "balance":
		return e.waitBalance(ctx, mount)
	case "replace":
		return e.waitReplace(ctx, mount)
	case "scrub":
		return e.waitScrub(ctx, mount)
	}
	return true, "", nil
}

// hold waits while a hold file for step id exists; false when ctx ended.
func (e *Engine) hold(ctx context.Context, id string) bool {
	if e.HoldDir == "" {
		return true
	}
	f := e.HoldDir + "/hold-before-" + id
	for logged := false; ; logged = true {
		if _, err := os.Stat(f); err != nil {
			return true
		}
		if !logged {
			e.log().Warn("storage operation held before a step (fault injection)", "step", id, "file", f)
		}
		if !e.sleep(ctx) {
			return false
		}
	}
}

func (e *Engine) sleep(ctx context.Context) bool {
	t := time.NewTimer(e.poll())
	defer t.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-t.C:
		return true
	}
}

// waitBalance: a running balance is waited for, a paused one resumed; then
// the soft-convert start runs (a no-op when every chunk is converted).
func (e *Engine) waitBalance(ctx context.Context, mount string) (bool, string, error) {
	note := ""
	for {
		out, code, err := e.Run.Exec(ctx, "", "btrfs", "balance", "status", mount)
		if err != nil {
			return false, "", err
		}
		s := string(out)
		switch {
		case code == 0:
			return true, note, nil
		case strings.Contains(s, "paused"):
			note = "resumed a paused balance"
			if o, c, err := e.Run.Exec(ctx, "", "btrfs", "balance", "resume", mount); err != nil || (c != 0 && !strings.Contains(string(o), "not paused")) {
				if err == nil {
					err = fmt.Errorf("balance resume exited %d: %s", c, tail(o, 200))
				}
				return false, "", err
			}
		default:
			note = "waited for the balance the kernel resumed at mount"
			if !e.sleep(ctx) {
				return false, "", ctx.Err()
			}
		}
	}
}

func (e *Engine) waitReplace(ctx context.Context, mount string) (bool, string, error) {
	note := ""
	for {
		out, _, err := e.Run.Exec(ctx, "", "btrfs", "replace", "status", "-1", mount)
		if err != nil {
			return false, "", err
		}
		s := strings.ToLower(string(out))
		switch {
		case strings.Contains(s, "finished"):
			return false, "replace already finished" + note, nil
		case strings.Contains(s, "never started"), strings.Contains(s, "canceled"):
			return true, note, nil
		case strings.Contains(s, "% done"), strings.Contains(s, "started"):
			note = "; waited for the replace the kernel resumed at mount"
			if !e.sleep(ctx) {
				return false, "", ctx.Err()
			}
		default:
			return true, note, nil
		}
	}
}

func (e *Engine) waitScrub(ctx context.Context, mount string) (bool, string, error) {
	for {
		out, _, err := e.Run.Exec(ctx, "", "btrfs", "scrub", "status", mount)
		if err != nil {
			return false, "", err
		}
		if !strings.Contains(strings.ToLower(string(out)), "running") {
			return true, "", nil
		}
		if !e.sleep(ctx) {
			return false, "", ctx.Err()
		}
	}
}

func isMember(m *storage.Mirror, dev string) bool {
	for _, mem := range m.Members {
		if !mem.Missing && mem.Path == dev {
			return true
		}
	}
	return false
}

// hasDevice: target is a devid, or "missing" (any missing member left).
func hasDevice(m *storage.Mirror, target string) bool {
	for _, mem := range m.Members {
		if target == "missing" && mem.Missing {
			return true
		}
		if fmt.Sprint(mem.DevID) == target {
			return true
		}
	}
	return false
}

// verifyProfiles reads `btrfs filesystem df -b` and checks every Data,
// Metadata and System line against the plan's profiles.
func verifyProfiles(out []byte, p storage.Plan) string {
	if p.DataProfile == "" {
		return ""
	}
	want := map[string]string{"Data": p.DataProfile, "Metadata": p.MetaProfile, "System": p.MetaProfile}
	var bad []string
	for _, line := range strings.Split(string(out), "\n") {
		kind, rest, ok := strings.Cut(line, ", ")
		if !ok || want[kind] == "" {
			continue
		}
		prof, _, _ := strings.Cut(rest, ":")
		if strings.ToLower(strings.TrimSpace(prof)) != want[kind] {
			bad = append(bad, kind+" is "+strings.ToLower(strings.TrimSpace(prof))+", want "+want[kind])
		}
	}
	if len(bad) > 0 {
		return "profile check failed: " + strings.Join(bad, "; ")
	}
	return ""
}
