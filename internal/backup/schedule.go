// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"time"
)

// Scheduled job names (keys of State.LastJobs).
const (
	jobHourly = "hourly" // backup run to the primary target
	jobDaily  = "daily"  // repository check, off-site runs
	jobWeekly = "weekly" // verified restores, prune
)

// hourlySlot is the latest hh:MM at or before now.
func hourlySlot(now time.Time, minute int) time.Time {
	s := time.Date(now.Year(), now.Month(), now.Day(), now.Hour(), minute, 0, 0, now.Location())
	if s.After(now) {
		s = s.Add(-time.Hour)
	}
	return s
}

// dailySlot is the latest HH:MM at or before now.
func dailySlot(now time.Time, hour, minute int) time.Time {
	s := time.Date(now.Year(), now.Month(), now.Day(), hour, minute, 0, 0, now.Location())
	if s.After(now) {
		s = s.AddDate(0, 0, -1)
	}
	return s
}

// weeklySlot is the latest weekday HH:MM at or before now.
func weeklySlot(now time.Time, day time.Weekday, hour, minute int) time.Time {
	s := dailySlot(now, hour, minute)
	for s.Weekday() != day {
		s = s.AddDate(0, 0, -1)
	}
	return s
}

func (a *Agent) nextHourly(now time.Time) time.Time {
	return hourlySlot(now, a.Cfg.RunMinute()).Add(time.Hour)
}

// dueJobs returns the jobs whose latest slot has not run yet, in order. A
// job that never ran is due only for the hourly run (the first backup should
// happen soon); daily and weekly jobs start counting from first start.
func (a *Agent) dueJobs(now time.Time) (due []string, slots map[string]time.Time) {
	m := a.Cfg.RunMinute()
	sc := a.Cfg.Schedule
	slots = map[string]time.Time{
		jobHourly: hourlySlot(now, m),
		jobDaily:  dailySlot(now, sc.MaintenanceHour, m),
		jobWeekly: weeklySlot(now, sc.VerifyWeekday, sc.MaintenanceHour, m),
	}
	last := a.Store.View().LastJobs
	var initial []string
	for _, j := range []string{jobHourly, jobDaily, jobWeekly} {
		l, ok := last[j]
		switch {
		case !ok && j != jobHourly:
			initial = append(initial, j)
		case !ok || l.Before(slots[j]):
			due = append(due, j)
		}
	}
	if len(initial) > 0 {
		_ = a.persist("schedule start", func(s *State) {
			for _, j := range initial {
				s.LastJobs[j] = now
			}
		})
	}
	return due, slots
}

// Tick runs every job that is due at now. A failed job is recorded in its
// run or verification and is not retried before its next slot, so a broken
// target cannot turn into a tight loop.
func (a *Agent) Tick(ctx context.Context, now time.Time) {
	due, slots := a.dueJobs(now)
	for _, j := range due {
		if ctx.Err() != nil {
			return
		}
		a.runJob(ctx, j)
		// The store keeps this in memory even if the disk write fails, so the job is not re-run in
		// a loop; the failure is logged and counted by persist.
		_ = a.persist("last job "+j, func(s *State) { s.LastJobs[j] = slots[j] })
	}
}

func (a *Agent) runJob(ctx context.Context, job string) {
	c := a.conf()
	primary, ok := c.Primary()
	if !ok {
		return // no destination yet: nothing to back up to
	}
	switch job {
	case jobHourly:
		if c.Schedule.GatewayHourly {
			return // the gateway runs the apps' hooks, then sends backup.run
		}
		if _, err := a.Run(ctx, RunRequest{Reason: ReasonScheduled, Wait: true}); err != nil {
			a.Log.Warn("scheduled backup", "error", err)
		}
	case jobDaily:
		if _, err := a.CheckRepo(ctx, primary.ID); err != nil {
			a.Log.Warn("repository check", "error", err)
		}
		// Off-site copy as a direct run to every other target (BACKUPS.md
		// §3 allows a direct run instead of `restic copy`).
		for _, t := range c.Targets {
			if !t.Primary {
				if _, err := a.Run(ctx, RunRequest{Reason: ReasonScheduled, TargetID: t.ID, Wait: true}); err != nil {
					a.Log.Warn("off-site backup", "target", t.ID, "error", err)
				}
			}
		}
	case jobWeekly:
		units, err := a.Units(ctx)
		if err != nil {
			a.Log.Warn("verify", "error", err)
			return
		}
		for _, u := range units {
			if _, err := a.VerifyRestore(ctx, u, primary.ID); err != nil {
				a.Log.Warn("verified restore", "unit", u.Name, "error", err)
			}
		}
		for _, t := range c.Targets {
			if t.AppendOnly {
				continue // pruning an append-only target is an owner job on that node
			}
			if err := a.Prune(ctx, t.ID); err != nil {
				a.Log.Warn("prune", "target", t.ID, "error", err)
			}
		}
	}
}

// Loop calls Tick every 30 seconds until ctx ends.
func (a *Agent) Loop(ctx context.Context) {
	t := time.NewTicker(30 * time.Second)
	defer t.Stop()
	for {
		a.Tick(ctx, a.Now())
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
	}
}

// Prune removes data no snapshot references on a target the box may delete
// from. It holds the agent lock: prune takes restic's exclusive lock anyway.
func (a *Agent) Prune(ctx context.Context, targetID string) error {
	t, ok := a.target(targetID)
	if !ok {
		return errUnknownTarget(targetID)
	}
	if t.AppendOnly {
		return errAppendOnly
	}
	if err := a.acquire(ctx, "prune"); err != nil {
		return err
	}
	defer a.release()
	repo, err := a.readyRepo(ctx, t)
	if err != nil {
		return err
	}
	return repo.Prune(ctx)
}
