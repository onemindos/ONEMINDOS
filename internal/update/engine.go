// SPDX-License-Identifier: Apache-2.0

package update

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// Mode is how a run was started.
type Mode int

// Modes.
const (
	ModeScheduled Mode = iota // the daemon: policy + window decide
	ModeCheck                 // `onemind update check`: fetch, decide, report; never install
	ModeApply                 // `onemind update apply`: the owner asks to install now
)

// Engine runs update cycles. Every outside effect is an interface or a
// field so tests can replace it.
type Engine struct {
	Cfg         *Config
	Installer   Installer
	Snapshotter Snapshotter // nil = restic not configured
	Rebooter    Rebooter
	HTTP        *http.Client
	Log         *slog.Logger
	Now         func() time.Time             // local time
	Free        func(string) (uint64, error) // free bytes on the download filesystem
	TUFTime     time.Time                    // tests only: TUF reference time instead of now
	// Mirror, when set, is a directory (USB stick or mounted LAN share) laid
	// out like the channel (CHANNEL.md section 3: TUF metadata files and the
	// bundles side by side). Metadata and bundle are verified exactly as online:
	// same image-shipped root, same TUF cache (rollback protection), same
	// length and hash checks, and RAUC re-checks its own signature. Only the
	// freshness check is relaxed, by Cfg.OfflineGrace.
	Mirror string
}

// source is where one run reads the channel from.
type source struct {
	cfg    *Config // URL and TargetsURL rewritten for a mirror
	hc     *http.Client
	ref    time.Time // TUF reference time; zero = now
	mirror string
}

func (e *Engine) source(now time.Time) (source, error) {
	if e.Mirror == "" {
		return source{cfg: e.Cfg, hc: e.HTTP, ref: e.TUFTime}, nil
	}
	if !filepath.IsAbs(e.Mirror) {
		return source{}, fmt.Errorf("mirror %q: must be an absolute directory path", e.Mirror)
	}
	if fi, err := os.Stat(e.Mirror); err != nil || !fi.IsDir() {
		return source{}, fmt.Errorf("mirror %q: not a readable directory", e.Mirror)
	}
	tr := &http.Transport{}
	tr.RegisterProtocol("file", http.NewFileTransport(http.Dir(e.Mirror)))
	mc := *e.Cfg
	mc.URL, mc.TargetsURL = "file:///", "file:///"
	ref := e.TUFTime
	if ref.IsZero() {
		ref = now
	}
	return source{cfg: &mc, hc: &http.Client{Transport: tr}, ref: ref.Add(-e.Cfg.OfflineGrace), mirror: e.Mirror}, nil
}

// New returns an Engine wired to the real rauc, restic and reboot command.
func New(c *Config, log *slog.Logger) *Engine {
	e := &Engine{
		Cfg:       c,
		Installer: RAUC{Binary: c.RAUCBinary},
		Rebooter:  Command{Argv: c.RebootCommand},
		HTTP:      &http.Client{Timeout: 30 * time.Minute},
		Log:       log,
		Now:       time.Now,
		Free:      freeBytes,
	}
	if c.ResticConfigured() {
		e.Snapshotter = Restic{Binary: c.ResticBinary, Repository: c.ResticRepository, PasswordFile: c.ResticPasswordFile,
			Paths: []string{"/data"}, Excludes: snapshotExcludes(c)}
	}
	return e
}

// snapshotExcludes is what the pre-update snapshot of /data leaves out: the
// bundles, the update state and, when the restic repository is a local
// directory (a bare path or "local:<path>", e.g. /data/backup/restic), the
// repository itself, which would otherwise be copied into itself every time.
func snapshotExcludes(c *Config) []string {
	ex := []string{c.DownloadDir, c.StateDir}
	repo := strings.TrimPrefix(c.ResticRepository, "local:")
	if filepath.IsAbs(repo) {
		ex = append(ex, filepath.Clean(repo))
	}
	return ex
}

// Result is what one run did.
type Result struct {
	Decision  Decision
	Reason    string
	Candidate *Target
	Skips     []Skip
	Rebooted  bool
	Status    *Status
}

// Run performs one update cycle. noReboot applies to ModeApply only.
func (e *Engine) Run(ctx context.Context, mode Mode, noReboot bool) (*Result, error) {
	unlock, err := lock(e.Cfg.StateDir)
	if err != nil {
		return nil, err
	}
	defer unlock()

	st, err := LoadStatus(e.Cfg)
	if err != nil {
		return nil, err
	}
	res := &Result{Status: st}
	box, err := ReadBox(e.Cfg)
	if err != nil {
		return res, e.fail(st, "", "box: "+err.Error())
	}
	prev := st.CurrentVersion // what the last run saw running; reconcile spots an owner go-back by it
	st.CurrentVersion = box.Version
	if !box.MarkerPresent && box.Version != "" {
		// Running and committed: the gate passed this version, so any earlier
		// bad verdict for it is stale.
		if cleared, cerr := ClearBadRelease(e.Cfg, box.Version); cerr != nil {
			e.Log.Warn("cannot clear stale bad-releases entry", "version", box.Version, "err", cerr)
		} else if cleared {
			e.Log.Info("cleared stale bad-releases entry for the committed running version", "version", box.Version)
		}
	}
	bad, err := ReadBadReleases(e.Cfg)
	if err != nil {
		return res, e.fail(st, "", "bad-releases: "+err.Error())
	}
	e.reconcile(st, box, bad, prev)

	// Installed but not yet rebooted: finish that before anything else.
	if st.State == heartbeat.UpdatePendingReboot && mode != ModeCheck {
		res.Decision, res.Reason = DecideBlockedTrial, "installed "+st.TargetVersion+", reboot pending"
		res.Rebooted = e.maybeReboot(ctx, st, mode, noReboot)
		return res, st.Save(e.Cfg)
	}

	now := e.Now()
	ts := now.UTC().Format(time.RFC3339)
	st.LastCheck = &ts
	src, err := e.source(now)
	if err != nil {
		return res, e.fail(st, "", err.Error())
	}
	idx, err := fetchIndex(src.cfg, src.hc, src.ref)
	if err != nil {
		e.Log.Warn("update check failed", "channel", e.Cfg.Channel, "err", err)
		st.LastResult = "check failed: " + err.Error()
		if st.State != heartbeat.UpdateTrial && st.State != heartbeat.UpdatePendingReboot {
			st.State = heartbeat.UpdateError
		}
		return res, errors.Join(err, st.Save(e.Cfg))
	}
	cand, skips := Select(e.Cfg, idx, box, bad)
	res.Candidate, res.Skips = cand, skips
	for _, s := range skips {
		e.Log.Debug("target skipped", "path", s.Path, "why", s.Why)
	}
	st.AvailableVersion = nil
	if cand != nil {
		v := cand.Meta.Version
		st.AvailableVersion = &v
	}
	if st.State == heartbeat.UpdateError {
		st.State = heartbeat.UpdateIdle
	}
	postpone, perr := ReadPostpone(e.Cfg)
	if perr != nil {
		e.Log.Warn("postpone-until unreadable; ignoring it", "err", perr)
	}
	policy, window := e.settings(st)
	res.Decision, res.Reason = Decide(DecideInput{
		Policy: policy, Window: window, Now: now, PostponeUntil: postpone,
		TrialPending: box.MarkerPresent, HaveCandidate: cand != nil, Explicit: mode == ModeApply,
	})
	st.Decision, st.Reason = string(res.Decision), res.Reason
	avail := "none"
	if cand != nil {
		avail = cand.Meta.Version
	}
	e.Log.Info("update decision", "channel", e.Cfg.Channel, "current", box.Version, "available", avail,
		"policy", policy, "window", window.String(), "decision", res.Decision, "reason", res.Reason)
	if mode == ModeCheck || res.Decision != DecideInstall {
		switch {
		case res.Decision == DecideInstall: // ModeCheck
			st.LastResult = "check: would install " + avail
		case (res.Decision == DecideNothing || res.Decision == DecideBlockedTrial) && st.State != heartbeat.UpdateIdle:
			// keep the verdict / trial text the reconcile step reported
		default:
			st.LastResult = string(res.Decision) + ": " + res.Reason
		}
		return res, st.Save(e.Cfg)
	}
	if err := e.install(ctx, st, src, idx, cand, box.Version); err != nil {
		return res, err
	}
	res.Rebooted = e.maybeReboot(ctx, st, mode, noReboot)
	return res, st.Save(e.Cfg)
}

// reconcile turns what the box shows after a (re)boot into the reported
// state. RAUC's exit status alone never counts as success (B4.2,
// [C-TD-casaos-zimaos-044]): only the booted version plus the gate's
// marker decide committed vs rolled back.
func (e *Engine) reconcile(st *Status, box Box, bad BadReleases, prev string) {
	now := e.Now().UTC().Format(time.RFC3339)
	switch {
	case box.MarkerPresent && box.MarkerVersion == box.Version:
		st.State, st.TargetVersion = heartbeat.UpdateTrial, box.Version
		st.LastResult = "trial: health gate is deciding on " + box.Version
	case box.MarkerPresent:
		if st.State != heartbeat.UpdatePendingReboot {
			st.LastResult = "installed " + box.MarkerVersion + ", reboot pending"
		}
		st.State = heartbeat.UpdatePendingReboot
		if st.TargetVersion == "" {
			st.TargetVersion = box.MarkerVersion
		}
	case st.State == heartbeat.UpdateTrial || st.State == heartbeat.UpdatePendingReboot:
		from := st.TargetVersion
		if box.Version == st.TargetVersion {
			st.State, st.LastResult = heartbeat.UpdateCommitted, "committed "+box.Version+" (health gate passed)"
			st.PreviousVersion = ""
			if st.FromVersion != box.Version {
				st.PreviousVersion = st.FromVersion // the other slot still holds it: "go back" boots it (P-16)
			}
			st.addHistory(HistoryEntry{At: now, From: st.FromVersion, To: box.Version, Result: heartbeat.UpdateCommitted})
		} else {
			v := bad.Verdict(from)
			if v == "" {
				v = "unknown"
			}
			st.State = heartbeat.UpdateRolledBack
			st.PreviousVersion = "" // the other slot holds the version the gate turned away
			st.LastResult = fmt.Sprintf("rolled back from %s to %s (gate verdict %s)", from, box.Version, v)
			st.addHistory(HistoryEntry{At: now, From: box.Version, To: from, Result: heartbeat.UpdateRolledBack, Detail: "gate verdict " + v})
		}
		e.Log.Info("update verdict", "state", st.State, "detail", st.LastResult)
	case prev != "" && prev != box.Version && bad.OwnerRolledBack(prev):
		// The owner approved going back (P-16): the host marked the other slot active and rebooted. The
		// status still says "committed <prev>", so record the go-back like the gate's own rollback.
		st.State, st.TargetVersion, st.FromVersion = heartbeat.UpdateRolledBack, prev, box.Version
		st.PreviousVersion = "" // the other slot holds the version the owner turned away
		st.LastResult = fmt.Sprintf("went back from %s to %s (owner request)", prev, box.Version)
		st.addHistory(HistoryEntry{At: now, From: prev, To: box.Version, Result: heartbeat.UpdateRolledBack, Detail: "owner rollback"})
		e.Log.Info("owner rollback", "from", prev, "to", box.Version)
	case st.State == heartbeat.UpdateDownloading || st.State == heartbeat.UpdateInstalling:
		st.State, st.LastResult = heartbeat.UpdateError, "interrupted while "+st.State+" "+st.TargetVersion
		st.addHistory(HistoryEntry{At: now, From: box.Version, To: st.TargetVersion, Result: heartbeat.UpdateError, Detail: "interrupted"})
	}
}

func (e *Engine) install(ctx context.Context, st *Status, src source, idx *Index, t *Target, from string) error {
	to := t.Meta.Version
	st.State, st.TargetVersion, st.FromVersion, st.Warnings, st.Snapshot = heartbeat.UpdateDownloading, to, from, nil, ""
	st.PreviousVersion = "" // the install is about to overwrite the other slot
	st.LastResult = "downloading " + to
	if err := st.Save(e.Cfg); err != nil {
		return err
	}
	if src.mirror != "" {
		st.Warnings = append(st.Warnings, "installed from mirror "+src.mirror+" (metadata freshness grace "+src.cfg.OfflineGrace.String()+")")
	}
	url := downloadURL(src.cfg, idx, t)
	e.Log.Info("downloading", "target", t.Path, "url", url, "bytes", t.Length)
	bundle, err := download(ctx, src.hc, url, e.Cfg.DownloadDir, t, e.Free)
	if err != nil {
		return e.fail(st, from, "download: "+err.Error())
	}
	st.State, st.LastResult = heartbeat.UpdateInstalling, "installing "+to
	if err := st.Save(e.Cfg); err != nil {
		return err
	}

	// Pre-update snapshot of /data (B4.2, D-B7.5).
	switch {
	case e.Snapshotter != nil:
		id, err := e.Snapshotter.Snapshot(ctx, from, to)
		if err != nil {
			if e.Cfg.RequireSnapshot {
				return e.fail(st, from, "pre-update snapshot: "+err.Error())
			}
			st.Snapshot = "none"
			st.Warnings = append(st.Warnings, "pre-update snapshot failed, installing anyway (require_snapshot=false): "+err.Error())
		} else {
			st.Snapshot = id
		}
	case e.Cfg.RequireSnapshot:
		return e.fail(st, from, "no pre-update snapshot: restic is not configured and require_snapshot=true")
	default:
		st.Snapshot = "none"
		st.Warnings = append(st.Warnings, "no pre-update snapshot: restic is not configured")
	}
	for _, w := range st.Warnings {
		e.Log.Warn(w)
	}
	e.Log.Info("installing", "bundle", bundle, "snapshot", st.Snapshot)
	if err := e.Installer.Install(ctx, bundle); err != nil {
		// RAUC's pre-install handler writes the trial marker before it writes
		// any slot. If the write then failed, the marker is a lie: left in
		// place the next cycle would report "reboot pending", reboot the box
		// and let the gate mark a release image-bad that never installed.
		msg := err.Error()
		if cerr := e.clearTrialMarker(to); cerr != nil {
			msg += "; could not clear the trial marker: " + cerr.Error()
		}
		return e.fail(st, from, msg)
	}
	_ = os.Remove(bundle) // RAUC wrote it into the slot; free /data
	st.State, st.LastResult = heartbeat.UpdatePendingReboot, "installed "+to+", reboot pending"
	return st.Save(e.Cfg)
}

// clearTrialMarker removes the gate's trial marker and its ESP copy when
// they name version to (the install that just failed). A marker naming any
// other version is not ours and stays.
func (e *Engine) clearTrialMarker(to string) error {
	var errs []error
	for _, p := range []string{filepath.Join(e.Cfg.GateDir, "pending"), e.Cfg.ESPMarker} {
		if p == "" {
			continue
		}
		b, err := os.ReadFile(p)
		if err != nil {
			if !errors.Is(err, os.ErrNotExist) {
				errs = append(errs, err)
			}
			continue
		}
		if f := strings.Fields(string(b)); len(f) > 1 && f[1] == to {
			if err := os.Remove(p); err != nil && !errors.Is(err, os.ErrNotExist) {
				errs = append(errs, err)
			} else {
				e.Log.Warn("install failed: removed the trial marker so the box does not reboot into a trial that never started", "marker", p)
			}
		}
	}
	return errors.Join(errs...)
}

// maybeReboot reboots at a safe point: an explicit apply reboots now (unless
// --no-reboot); the daemon never once the owner turned updates off (the switch
// may come after the install, REL-02), and otherwise only inside the window; never while the reboot inhibit file exists (mission-safe
// reboot, BD-09).
func (e *Engine) maybeReboot(ctx context.Context, st *Status, mode Mode, noReboot bool) bool {
	switch {
	case mode == ModeApply && noReboot:
		return false
	}
	policy, window := e.settings(st)
	if mode == ModeScheduled && policy == PolicyOff {
		st.LastResult = "installed " + st.TargetVersion + ", reboot waits for the owner: policy " + string(policy) +
			" (run `onemind update apply` to restart into it)"
		e.Log.Info("reboot waits for the owner", "policy", policy)
		return false
	}
	if mode == ModeScheduled && !window.Contains(e.Now()) {
		e.Log.Info("reboot waits for the maintenance window", "window", window.String())
		return false
	}
	if _, err := os.Stat(e.Cfg.RebootInhibitFile); err == nil {
		st.LastResult = "installed " + st.TargetVersion + ", reboot deferred: " + e.Cfg.RebootInhibitFile + " present"
		e.Log.Info("reboot deferred", "inhibit", e.Cfg.RebootInhibitFile)
		return false
	}
	st.LastResult = "rebooting into " + st.TargetVersion
	if err := st.Save(e.Cfg); err != nil {
		e.Log.Warn("save status", "err", err)
	}
	e.Log.Info("rebooting", "target", st.TargetVersion)
	if err := e.Rebooter.Reboot(ctx); err != nil {
		st.LastResult = "installed " + st.TargetVersion + ", reboot failed: " + err.Error()
		e.Log.Error("reboot failed", "err", err)
		return false
	}
	return true
}

func (e *Engine) fail(st *Status, from, msg string) error {
	st.State, st.LastResult = heartbeat.UpdateError, msg
	if st.TargetVersion != "" {
		st.addHistory(HistoryEntry{At: e.Now().UTC().Format(time.RFC3339), From: from, To: st.TargetVersion,
			Result: heartbeat.UpdateError, Detail: msg})
	}
	e.Log.Error("update failed", "err", msg)
	return errors.Join(errors.New(msg), st.Save(e.Cfg))
}

// settings returns the policy and window in force (the owner's file over the
// image's update.conf, owner.go) and records them in the status. A bad owner
// file is logged and the image's settings apply.
func (e *Engine) settings(st *Status) (Policy, Window) {
	p, w, src, err := e.Cfg.Effective()
	if err != nil {
		e.Log.Warn("owner update settings unreadable; the image's settings apply", "err", err)
	}
	st.Policy, st.Window, st.SettingsSource = string(p), w.String(), src
	return p, w
}

// Daemon runs scheduled cycles until ctx ends: one at start (which also
// reports the verdict of the update that may have just booted), then every
// CheckInterval with up to 10% jitter so a fleet does not hit the channel at once.
func (e *Engine) Daemon(ctx context.Context) {
	for {
		if _, err := e.Run(ctx, ModeScheduled, false); err != nil {
			e.Log.Warn("update cycle", "err", err)
		}
		d := e.Cfg.CheckInterval + time.Duration(rand.Int64N(int64(e.Cfg.CheckInterval/10)+1))
		select {
		case <-ctx.Done():
			return
		case <-time.After(d):
		}
	}
}
