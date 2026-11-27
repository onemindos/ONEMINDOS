// SPDX-License-Identifier: Apache-2.0

// Package jobs is a joined machine's intake of signed jobs from its gateway
// (D-029 plan N2; contract sdk/contracts/poc-v0.md §12.9 and §12.11).
//
// The gateway decides; NATS carries. A person approves an action in the
// gateway, the gateway signs one onemind.job/v2 envelope for one machine and
// publishes it on onemind.node.<node_id>.job.<kind>. The hub keeps it in the
// ONEMIND_JOBS work queue, in that machine's own durable pull consumer
// node-<node_id> (core/onemind_core/jetstream.py NodeJobConsumer), so a machine
// that is off or cut off when the job is sent gets it when it is back (up to
// the stream's 24 hours, and never after the job's own expiry).
//
// The machine pulls one job at a time on onemind.node.<node_id>.jobpull, the
// one hub service its NATS account imports for that (natsconf.py job_services).
// Each job goes through backup.JobVerifier (NewNodeJobVerifier): signed by the
// job key pinned at join, addressed to this node, not expired, not older than
// the newest policy epoch, and a job id never seen before. The verifier writes
// the job id to its done-list on disk before Verify returns, and only then is
// the job acknowledged and run. So a job runs at most once: a redelivery (the
// acknowledgement was lost, or the machine crashed mid-job) is refused as
// "replayed" and acknowledged without running again. A refused job is
// terminated (never redelivered) and reported failed with the refusal code.
//
// Nothing here approves anything: a machine only checks and runs what the
// gateway already signed after a person's approval.
package jobs

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"regexp"
	"sync"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/onemindos/onemindos/internal/backup"
)

// Defaults for the pull loop.
const (
	// DefaultPollWait is how long one pull waits on the hub for a job. The
	// request itself waits a little longer, so the hub's "no job" answer (a 408
	// status) arrives before the client gives up and no job is left in flight.
	DefaultPollWait = 20 * time.Second
	// DefaultRetry is the pause after the hub could not be asked (link down).
	DefaultRetry = 5 * time.Second
	ackTimeout   = 5 * time.Second
)

// Job states in a job result (contract §12.9).
const (
	StateRunning   = "running"
	StateSucceeded = "succeeded"
	StateFailed    = "failed"
)

var (
	nodeIDRe = regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)
	jobIDRe  = regexp.MustCompile(`^job_[A-Za-z0-9]{8,64}$`) // backup.jobIDRe
)

// PullSubject is where node nodeID asks the hub for its next job
// (core/onemind_core/natsconf.py job_pull_subject).
func PullSubject(nodeID string) string { return "onemind.node." + nodeID + ".jobpull" }

// ResultSubject is where node nodeID reports on job jobID (contract §12.9).
func ResultSubject(nodeID, jobID string) string {
	return "onemind.node." + nodeID + ".jobresult." + jobID
}

// Result is what a handler reports. State is StateSucceeded or StateFailed;
// Reason is a short slug on failure.
type Result struct {
	State   string
	Summary string
	Reason  string
}

// Handler runs one verified job kind. It must return when ctx is done.
type Handler func(ctx context.Context, j backup.Job) Result

// Report is one job result as published (contract §12.9).
type Report struct {
	JobID      string `json:"job_id"`
	State      string `json:"state"`
	Summary    string `json:"summary"`
	Reason     string `json:"reason,omitempty"`
	FinishedAt string `json:"finished_at,omitempty"`
}

// Intake pulls, verifies and runs this machine's jobs.
type Intake struct {
	NC       *nats.Conn
	NodeID   string
	Verifier *backup.JobVerifier
	// Handlers by job kind. A verified job of a kind with no handler is
	// reported failed with reason unsupported_kind: this machine was never
	// given that power.
	Handlers map[string]Handler
	// Policy is this machine's stop and revoke snapshot (policy.go): read from the hub before every
	// pull (and again right before an actuating job), kept on disk, and checked against every verified
	// job. nil or no verified snapshot: jobs that actuate something are refused (no_policy).
	Policy   *PolicyStore
	Log      *slog.Logger
	PollWait time.Duration
	Retry    time.Duration
	Now      func() time.Time

	mu            sync.Mutex
	stats         Stats
	lastPolicyErr string
}

// Stats counts what the intake did since it started.
type Stats struct {
	Ran      int `json:"ran"`
	Refused  int `json:"refused"`
	Replayed int `json:"replayed"`
}

// Stats returns the counters.
func (in *Intake) Stats() Stats {
	in.mu.Lock()
	defer in.mu.Unlock()
	return in.stats
}

func (in *Intake) count(f func(*Stats)) {
	in.mu.Lock()
	f(&in.stats)
	in.mu.Unlock()
}

func (in *Intake) defaults() error {
	if in.NC == nil || in.Verifier == nil {
		return errors.New("jobs: a NATS connection and a verifier are required")
	}
	if !nodeIDRe.MatchString(in.NodeID) || in.Verifier.NodeID != in.NodeID {
		return errors.New("jobs: the node id must be set, the same on the verifier")
	}
	if in.Log == nil {
		in.Log = slog.Default()
	}
	if in.PollWait <= 0 {
		in.PollWait = DefaultPollWait
	}
	if in.Retry <= 0 {
		in.Retry = DefaultRetry
	}
	if in.Now == nil {
		in.Now = time.Now
	}
	return nil
}

// Run pulls jobs until ctx is done.
func (in *Intake) Run(ctx context.Context) error {
	if err := in.defaults(); err != nil {
		return err
	}
	in.Log.Info("job intake started", "node_id", in.NodeID, "subject", PullSubject(in.NodeID))
	for ctx.Err() == nil {
		if _, err := in.PullOnce(ctx); err != nil && ctx.Err() == nil {
			in.Log.Debug("job pull", "err", err)
			select {
			case <-ctx.Done():
			case <-time.After(in.Retry):
			}
		}
	}
	return nil
}

// PullOnce asks the hub for one job, waiting up to PollWait, and handles it.
// It reports whether a job (of any outcome) arrived.
func (in *Intake) PullOnce(ctx context.Context) (bool, error) {
	if err := in.defaults(); err != nil {
		return false, err
	}
	// The newest stop and revoke snapshot always wins over a queued job: no job is taken while the
	// snapshot cannot be read (fail closed), only while the hub has none for this machine yet.
	if err := in.refreshPolicy(ctx); err != nil {
		return false, err
	}
	in.warnUnverifiedPolicy()
	req, _ := json.Marshal(map[string]any{"batch": 1, "expires": in.PollWait.Nanoseconds()})
	rctx, cancel := context.WithTimeout(ctx, in.PollWait+5*time.Second)
	defer cancel()
	msg, err := in.NC.RequestWithContext(rctx, PullSubject(in.NodeID), req)
	if err != nil {
		return false, err
	}
	if st := msg.Header.Get("Status"); st != "" {
		// 404 no job, 408 the wait ended, 409 the consumer changed: nothing to run.
		if st == "404" || st == "408" {
			return false, nil
		}
		return false, errors.New("hub: " + st + " " + msg.Header.Get("Description"))
	}
	in.handle(ctx, msg)
	return true, nil
}

func (in *Intake) handle(ctx context.Context, msg *nats.Msg) {
	j, err := in.Verifier.Verify(msg.Data)
	if err != nil {
		var je *backup.JobError
		code := "bad_job"
		if errors.As(err, &je) {
			code = je.Code
		}
		if code == "replayed" {
			// Seen before: it already ran, or it was being run when the machine stopped. Never twice.
			in.ack(msg, "+ACK")
			in.count(func(s *Stats) { s.Replayed++ })
			in.Log.Info("job refused: already seen", "subject", msg.Subject)
			return
		}
		in.ack(msg, "+TERM")
		in.count(func(s *Stats) { s.Refused++ })
		in.Log.Warn("job refused", "code", code, "err", err)
		if id := rawJobID(msg.Data); id != "" {
			in.report(Report{JobID: id, State: StateFailed, Summary: "refused by node-" + in.NodeID, Reason: code})
		}
		return
	}
	code := in.Policy.current().Check(j)
	if code == "" && Actuates(j.Kind) {
		// Read the newest snapshot once more right before something moves: a stop pressed while
		// this job was on its way is on the hub before the gateway's stop call returns
		// (fabric_policy.py push_now). Not reachable now means not run (fail closed).
		if err := in.refreshPolicy(ctx); err != nil {
			code = "policy_unreachable"
			in.Log.Warn("policy snapshot not readable before an actuating job", "err", err)
		} else {
			code = in.Policy.current().Check(j)
		}
	}
	if code != "" {
		// Signed and meant for us, but the newest snapshot says no (D-029: it only ever adds a no).
		in.ack(msg, "+TERM")
		in.count(func(s *Stats) { s.Refused++ })
		in.Log.Warn("job refused by the policy snapshot", "code", code, "job_id", j.ID, "kind", j.Kind)
		in.report(Report{JobID: j.ID, State: StateFailed, Summary: "refused by node-" + in.NodeID + "'s policy snapshot", Reason: code})
		return
	}
	// Recorded in the done-list: acknowledge before running, so the hub stops redelivering.
	in.ack(msg, "+ACK")
	in.count(func(s *Stats) { s.Ran++ })
	h := in.Handlers[j.Kind]
	if h == nil {
		in.report(Report{JobID: j.ID, State: StateFailed, Summary: "this machine does not run " + j.Kind, Reason: "unsupported_kind"})
		return
	}
	in.report(Report{JobID: j.ID, State: StateRunning, Summary: j.Kind})
	res := h(ctx, j)
	if res.State != StateSucceeded {
		res.State = StateFailed
	}
	in.report(Report{JobID: j.ID, State: res.State, Summary: res.Summary, Reason: res.Reason})
}

// refreshPolicy reads this machine's newest snapshot from the hub and keeps it when it verifies and
// is newer; the one on disk stays otherwise. An error (the hub's snapshot service is not reachable)
// means no job is pulled this round; "no snapshot yet" (404) is not an error.
func (in *Intake) refreshPolicy(ctx context.Context) error {
	if in.Policy == nil {
		return nil
	}
	rctx, cancel := context.WithTimeout(ctx, ackTimeout)
	defer cancel()
	msg, err := in.NC.RequestWithContext(rctx, PolicyGetSubject(in.NodeID), nil)
	if err != nil {
		return fmt.Errorf("policy snapshot: %w", err)
	}
	switch st := msg.Header.Get("Status"); st {
	case "":
	case "404":
		return nil
	default:
		return fmt.Errorf("policy snapshot: hub status %s %s", st, msg.Header.Get("Description"))
	}
	changed, err := in.Policy.Apply(msg.Data)
	switch {
	case err != nil:
		in.Log.Warn("policy snapshot refused", "err", err)
	case changed:
		p := in.Policy.Current()
		in.Log.Info("policy snapshot applied", "epoch", p.Epoch, "motion_lockout", p.Stop.MotionLockout, "agents_stopped", p.Stop.Agents)
	}
	return nil
}

// warnUnverifiedPolicy says loudly, once per cause, that the snapshot on disk
// does not verify: actuating jobs are refused (no_policy) until a new one arrives.
func (in *Intake) warnUnverifiedPolicy() {
	if in.Policy == nil || in.Policy.Current() != nil {
		return
	}
	err := in.Policy.LoadError()
	in.mu.Lock()
	msg := ""
	if err != nil {
		msg = err.Error()
	}
	first := msg != "" && msg != in.lastPolicyErr
	in.lastPolicyErr = msg
	in.mu.Unlock()
	if first {
		in.Log.Error("the stop snapshot this machine keeps does not verify; actuating jobs are refused until the hub sends a new one", "err", err)
	}
}

// ack answers the hub for msg: +ACK (done, remove it) or +TERM (refused, never redeliver).
func (in *Intake) ack(msg *nats.Msg, verb string) {
	if msg.Reply == "" {
		return
	}
	if _, err := in.NC.Request(msg.Reply, []byte(verb), ackTimeout); err != nil {
		// The job id is already in the done-list, so a redelivery is refused as replayed.
		in.Log.Warn("job acknowledgement not confirmed", "verb", verb, "err", err)
	}
}

func (in *Intake) report(r Report) {
	if r.State != StateRunning {
		r.FinishedAt = in.Now().UTC().Format(time.RFC3339)
	}
	b, _ := json.Marshal(r)
	if err := in.NC.Publish(ResultSubject(in.NodeID, r.JobID), b); err != nil {
		in.Log.Warn("job result not sent", "job_id", r.JobID, "err", err)
	}
}

// rawJobID is the job id of a refused envelope, when it has a well-formed one,
// so the gateway learns why its job did not run.
func rawJobID(body []byte) string {
	var env struct {
		JobID string `json:"job_id"`
	}
	if json.Unmarshal(body, &env) != nil || !jobIDRe.MatchString(env.JobID) {
		return ""
	}
	return env.JobID
}
