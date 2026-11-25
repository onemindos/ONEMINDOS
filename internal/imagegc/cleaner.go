// SPDX-License-Identifier: Apache-2.0

package imagegc

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"strconv"
	"sync"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// Source is what the cleaner reads and changes. Exec implements it with the
// k3s tools; tests use a fake.
type Source interface {
	// Images lists the container runtime's image store.
	Images(ctx context.Context) ([]Image, error)
	// ContainerImages returns the image of every container, running or exited.
	ContainerImages(ctx context.Context) (map[string]bool, error)
	// Workloads returns the cluster's workload list (kubectl get ... -A -o json).
	Workloads(ctx context.Context) ([]byte, error)
	// Remove deletes one image by id.
	Remove(ctx context.Context, id string) error
}

// Config is the box's disk budget and cleanup schedule.
type Config struct {
	// BudgetPct is the share of the image disk the box may fill. Past it the
	// cleanup runs at once. Default 80: below kubelet's own image collector
	// (85 %), so the safe cleanup runs first.
	BudgetPct float64
	// WarnPct is where the owner is warned that the disk is filling (the
	// gateway turns it into the disk.budget_near alert). Default budget - 10.
	WarnPct float64
	// Every is the regular cleanup period. Default 24 h.
	Every time.Duration
	// Check is how often disk use is compared with the budget. Default 5 min.
	Check time.Duration
}

// Defaults fills unset or invalid fields.
func (c Config) Defaults() Config {
	if c.BudgetPct <= 0 || c.BudgetPct > 100 {
		c.BudgetPct = 80
	}
	if c.WarnPct <= 0 || c.WarnPct >= c.BudgetPct {
		c.WarnPct = c.BudgetPct - 10
	}
	if c.Every <= 0 {
		c.Every = 24 * time.Hour
	}
	if c.Check <= 0 {
		c.Check = 5 * time.Minute
	}
	return c
}

// ConfigFromEnv reads ONEMIND_IMAGES_BUDGET_PCT and ONEMIND_IMAGES_WARN_PCT.
func ConfigFromEnv() Config {
	f := func(k string) float64 {
		v, _ := strconv.ParseFloat(os.Getenv(k), 64)
		return v
	}
	return Config{BudgetPct: f("ONEMIND_IMAGES_BUDGET_PCT"), WarnPct: f("ONEMIND_IMAGES_WARN_PCT")}.Defaults()
}

// Report is the heartbeat's "images" object.
type Report = heartbeat.Images

// Result is one cleanup run.
type Result struct {
	Removed []Image
	Kept    int
	Freed   int64
	Outcome string // succeeded | partial | skipped | failed
	Reason  string
}

// Cleaner runs cleanups and keeps the last report.
type Cleaner struct {
	Src   Source
	Cfg   Config
	Usage func() (usedPct float64, ok bool) // disk use of the image store's filesystem
	Now   func() time.Time

	mu     sync.Mutex
	report Report
}

// New returns a Cleaner with defaults.
func New(src Source, cfg Config, usage func() (float64, bool)) *Cleaner {
	cfg = cfg.Defaults()
	return &Cleaner{Src: src, Cfg: cfg, Usage: usage, Now: time.Now,
		report: Report{BudgetPct: cfg.BudgetPct, WarnPct: cfg.WarnPct, LastResult: "none"}}
}

// Clean removes the superseded images once. It removes nothing when the
// cluster's workloads or containers cannot be read: an unknown cluster is no
// evidence that an image is unused (a worker node has no cluster credentials).
func (c *Cleaner) Clean(ctx context.Context) Result {
	images, err := c.Src.Images(ctx)
	if err != nil {
		return c.finish(Result{Outcome: "failed", Reason: "cannot list images: " + err.Error()}, nil, -1)
	}
	skip := func(why string) Result {
		return c.finish(Result{Outcome: "skipped", Reason: why, Kept: len(images)}, images, -1)
	}
	list, err := c.Src.Workloads(ctx)
	if err != nil {
		return skip("cannot read the cluster's workloads: " + err.Error())
	}
	wanted, err := Wanted(list)
	if err != nil {
		return skip("unreadable workload list: " + err.Error())
	}
	inUse, err := c.Src.ContainerImages(ctx)
	if err != nil {
		return skip("cannot list containers: " + err.Error())
	}
	d := Plan(images, wanted, inUse)
	res := Result{Outcome: "succeeded", Kept: len(d.Keep)}
	var errs []error
	var stuck int64
	left := append([]Image{}, d.Keep...)
	for _, img := range d.Prune {
		if err := c.Src.Remove(ctx, img.ID); err != nil {
			errs = append(errs, fmt.Errorf("%s: %w", img.ID, err))
			left = append(left, img)
			stuck += img.Size
			continue
		}
		res.Removed = append(res.Removed, img)
		res.Freed += img.Size
	}
	if len(errs) > 0 {
		res.Outcome, res.Reason = "partial", errors.Join(errs...).Error()
	}
	return c.finish(res, left, stuck)
}

// finish records a run: left is the store afterwards (nil = unknown), superseded
// the bytes of superseded images still there (-1 = unknown: keep the last figure).
func (c *Cleaner) finish(res Result, left []Image, superseded int64) Result {
	now := c.Now().UTC().Format(time.RFC3339)
	c.mu.Lock()
	defer c.mu.Unlock()
	r := &c.report
	r.LastCleanupAt, r.LastResult, r.LastRemoved, r.LastFreedBytes = &now, res.Outcome, len(res.Removed), res.Freed
	if left != nil {
		r.Count, r.Bytes = len(left), 0
		for _, img := range left {
			r.Bytes += img.Size
		}
	}
	if superseded >= 0 {
		r.SupersededBytes = superseded
	}
	return res
}

// Report returns the heartbeat object, with the disk use read now.
func (c *Cleaner) Report() *Report {
	c.mu.Lock()
	r := c.report
	c.mu.Unlock()
	if c.Usage != nil {
		if pct, ok := c.Usage(); ok {
			r.DiskUsedPct = pct
		}
	}
	return &r
}

// OverBudget reports whether the image disk is past the budget.
func (c *Cleaner) OverBudget() bool {
	if c.Usage == nil {
		return false
	}
	pct, ok := c.Usage()
	return ok && pct >= c.Cfg.BudgetPct
}

// Run cleans once at start, then every Cfg.Every, and at once whenever a
// check finds the disk past the budget (at most once per check period). A run
// that was skipped or failed (k3s not up yet) is retried at the next check.
// After every check it hands the report to publish (the heartbeat's source).
func (c *Cleaner) Run(ctx context.Context, log *slog.Logger, publish func(*Report) error) error {
	var last time.Time
	retry := true
	tick := time.NewTicker(c.Cfg.Check)
	defer tick.Stop()
	for {
		if over := c.OverBudget(); over || retry || c.Now().Sub(last) >= c.Cfg.Every {
			res := c.Clean(ctx)
			last, retry = c.Now(), res.Outcome == "skipped" || res.Outcome == "failed"
			log.Info("image cleanup", "outcome", res.Outcome, "removed", len(res.Removed), "freed_bytes", res.Freed,
				"kept", res.Kept, "over_budget", over, "reason", res.Reason)
		}
		if publish != nil {
			if err := publish(c.Report()); err != nil {
				log.Error("image report not written", "err", err)
			}
		}
		select {
		case <-ctx.Done():
			return nil
		case <-tick.C:
		}
	}
}

// Exec is the Source on a k3s node: crictl for the runtime, kubectl for the
// cluster. Each is a command with leading arguments, for example
// ["crictl"] (a k3s link, deploy/pins.env) or ["/usr/local/bin/k3s", "crictl"].
type Exec struct {
	Crictl, Kubectl []string
	Timeout         time.Duration
}

// WorkloadKinds are the objects whose pod templates name images.
const WorkloadKinds = "deployments,statefulsets,daemonsets,replicasets,controllerrevisions,jobs,cronjobs,pods"

func (e Exec) run(ctx context.Context, cmd []string, args ...string) ([]byte, error) {
	if len(cmd) == 0 {
		return nil, errors.New("no command configured")
	}
	t := e.Timeout
	if t <= 0 {
		t = 2 * time.Minute
	}
	ctx, cancel := context.WithTimeout(ctx, t)
	defer cancel()
	name := cmd[0]
	out, err := exec.CommandContext(ctx, name, append(append([]string{}, cmd[1:]...), args...)...).Output()
	if err != nil {
		var ee *exec.ExitError
		if errors.As(err, &ee) && len(ee.Stderr) > 0 {
			return nil, fmt.Errorf("%s: %w: %.300s", name, err, ee.Stderr)
		}
		return nil, fmt.Errorf("%s: %w", name, err)
	}
	return out, nil
}

// Images implements Source.
func (e Exec) Images(ctx context.Context) ([]Image, error) {
	out, err := e.run(ctx, e.Crictl, "images", "-o", "json")
	if err != nil {
		return nil, err
	}
	return ParseImages(out)
}

// ParseImages reads `crictl images -o json`.
func ParseImages(out []byte) ([]Image, error) {
	var doc struct {
		Images []Image `json:"images"`
	}
	if err := json.Unmarshal(out, &doc); err != nil {
		return nil, err
	}
	return doc.Images, nil
}

// ContainerImages implements Source.
func (e Exec) ContainerImages(ctx context.Context) (map[string]bool, error) {
	out, err := e.run(ctx, e.Crictl, "ps", "-a", "-o", "json")
	if err != nil {
		return nil, err
	}
	return ParseContainers(out)
}

// ParseContainers reads `crictl ps -a -o json`: the image id or reference of every container.
func ParseContainers(out []byte) (map[string]bool, error) {
	var doc struct {
		Containers []struct {
			Image struct {
				Image string `json:"image"`
			} `json:"image"`
			ImageRef string `json:"imageRef"`
		} `json:"containers"`
	}
	if err := json.Unmarshal(out, &doc); err != nil {
		return nil, err
	}
	used := map[string]bool{}
	for _, c := range doc.Containers {
		for _, id := range []string{c.Image.Image, c.ImageRef} {
			if id != "" {
				used[id] = true
			}
		}
	}
	return used, nil
}

// Workloads implements Source.
func (e Exec) Workloads(ctx context.Context) ([]byte, error) {
	return e.run(ctx, e.Kubectl, "get", WorkloadKinds, "-A", "-o", "json")
}

// Remove implements Source.
func (e Exec) Remove(ctx context.Context, id string) error {
	_, err := e.run(ctx, e.Crictl, "rmi", id)
	return err
}

func round1(v float64) float64 { return float64(int64(v*10+0.5)) / 10 }

// DefaultReportPath is where `onemindd images` leaves the heartbeat's "images"
// object for the heartbeat agent (which stays read-only and cannot run the
// cleanup itself).
const DefaultReportPath = "/run/onemind-images/report.json"

// WriteReport writes the report atomically (readable by the heartbeat agent, root).
func WriteReport(path string, r *Report) error {
	b, err := json.Marshal(r)
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

// ReadReport reads the report, or nil when there is none (no cleaner on this node).
func ReadReport(path string) *Report {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var r Report
	if json.Unmarshal(b, &r) != nil || r.LastResult == "" {
		return nil
	}
	return &r
}
