// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"
)

func unitNamed(t *testing.T, a *Agent, name string) Unit {
	units, _ := a.Units(context.Background())
	for _, u := range units {
		if u.Name == name {
			return u
		}
	}
	t.Fatalf("no unit %s", name)
	return Unit{}
}

func TestVerifyRestorePassesAndRecords(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	sys := unitNamed(t, f.agent, "system")

	// too fresh: nothing at least an hour old yet
	v, err := f.agent.VerifyRestore(context.Background(), sys, "")
	if err != nil || v.Verdict != VerdictError {
		t.Fatalf("fresh: %+v %v", v, err)
	}
	f.clock = f.clock.Add(2 * time.Hour)
	v, err = f.agent.VerifyRestore(context.Background(), sys, "")
	if err != nil || v.Verdict != VerdictPassed {
		t.Fatalf("verify: %+v %v", v, err)
	}
	checks, _ := v.Details["checks"].([]string)
	if strings.Join(checks, ",") != "audit_chain,sqlite_integrity" || v.Details["files"].(int) < 3 {
		t.Fatalf("details = %v", v.Details)
	}
	if lv := f.agent.Store.View().LastVerified["system"]; lv.ID != v.ID {
		t.Fatalf("last verified = %+v", lv)
	}
	if entries, _ := os.ReadDir(f.cfg.ScratchDir); len(entries) != 0 {
		t.Fatalf("scratch not cleaned: %v", entries)
	}
}

// A restore that comes back short fails, even though restic reported success.
func TestVerifyRestoreDetectsBadRestore(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	f.clock = f.clock.Add(2 * time.Hour)
	f.repo.corrupt = f.path("data/onemind/storage/photos/a.jpg")
	v, _ := f.agent.VerifyRestore(context.Background(), unitNamed(t, f.agent, "app:photos"), "")
	if v.Verdict != VerdictFailed || !strings.Contains(v.Details["error"].(string), "bytes") {
		t.Fatalf("verify = %+v", v)
	}
	if b := f.agent.Store.View().UnitBadge("app:photos", f.clock); b.State != BadgeFailing {
		t.Fatalf("badge = %+v", b)
	}
}

func TestVerifyRestoreRunsHookChecks(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	f.clock = f.clock.Add(2 * time.Hour)
	sys := unitNamed(t, f.agent, "system")
	// tamper with the tagged head so the restored chain no longer matches
	for _, s := range f.repo.snaps {
		for i, tag := range s.Tags {
			if strings.HasPrefix(tag, "audit_head=") {
				s.Tags[i] = "audit_head=" + strings.Repeat("9", 64)
			}
		}
	}
	if v, _ := f.agent.VerifyRestore(context.Background(), sys, ""); v.Verdict != VerdictFailed {
		t.Fatalf("verify = %+v", v)
	}
}

func TestCheckRepoRetriesOnceAndRotatesSubset(t *testing.T) {
	f := newFixture(t)
	f.repo.checkErrs = []error{&ResticError{Op: "check", ExitCode: 1, Stderr: "flaky"}}
	v, err := f.agent.CheckRepo(context.Background(), "")
	if err != nil || v.Verdict != VerdictPassed || v.Details["first_attempt"] == nil {
		t.Fatalf("check = %+v %v", v, err)
	}
	if v.Details["read_data_subset"] != "2/7" { // day 316 of 2026: 316 % 7 + 1
		t.Fatalf("subset = %v", v.Details["read_data_subset"])
	}
	f.repo.checkErrs = []error{&ResticError{Op: "check", ExitCode: 1}, &ResticError{Op: "check", ExitCode: 1}}
	if v, _ := f.agent.CheckRepo(context.Background(), ""); v.Verdict != VerdictFailed {
		t.Fatalf("damage = %+v", v)
	}
	f.repo.checkErrs = []error{&ResticError{Op: "check", ExitCode: 11}, &ResticError{Op: "check", ExitCode: 11}}
	if v, _ := f.agent.CheckRepo(context.Background(), ""); v.Verdict != VerdictError {
		t.Fatalf("locked repo should be error, not damage: %+v", v)
	}
}

// BT-11: badge states at their boundaries.
func TestBadgeBoundaries(t *testing.T) {
	now := time.Date(2026, 11, 12, 12, 0, 0, 0, time.UTC)
	at := func(d time.Duration) *time.Time { t := now.Add(-d); return &t }
	run := func(ago time.Duration, state string) Run {
		return Run{FinishedAt: at(ago), State: state, Units: []UnitResult{{Unit: "u", State: state}}}
	}
	ver := func(ago time.Duration, verdict string) Verification {
		return Verification{Unit: "u", Kind: "restore", FinishedAt: *at(ago), Verdict: verdict}
	}
	type tc struct {
		runs []Run
		vers []Verification
		want string
	}
	for name, c := range map[string]tc{
		"none":                 {want: BadgeNone},
		"verified":             {[]Run{run(2*time.Hour, StateSucceeded)}, []Verification{ver(8*24*time.Hour, VerdictPassed)}, BadgeVerified},
		"verification too old": {[]Run{run(time.Hour, StateSucceeded)}, []Verification{ver(8*24*time.Hour+time.Second, VerdictPassed)}, BadgeUnverified},
		"never verified":       {[]Run{run(time.Hour, StateSucceeded)}, nil, BadgeUnverified},
		"stale":                {[]Run{run(2*time.Hour+time.Second, StateSucceeded)}, []Verification{ver(time.Hour, VerdictPassed)}, BadgeStale},
		"two failures":         {[]Run{run(3*time.Hour, StateSucceeded), run(2*time.Hour, StateFailed), run(time.Hour, StateFailed)}, nil, BadgeStale},
		"three failures":       {[]Run{run(4*time.Hour, StateFailed), run(2*time.Hour, StateFailed), run(time.Hour, StateFailed)}, nil, BadgeFailing},
		"verify failed":        {[]Run{run(time.Hour, StateSucceeded)}, []Verification{ver(2*time.Hour, VerdictPassed), ver(time.Hour, VerdictFailed)}, BadgeFailing},
		"error is not failing": {[]Run{run(time.Hour, StateSucceeded)}, []Verification{ver(2*time.Hour, VerdictPassed), ver(time.Hour, VerdictError)}, BadgeVerified},
	} {
		st := State{Runs: c.runs, Verifications: c.vers, LastVerified: map[string]Verification{}}
		for _, v := range c.vers {
			if v.Verdict == VerdictPassed {
				st.LastVerified["u"] = v
			}
		}
		if got := st.UnitBadge("u", now).State; got != c.want {
			t.Errorf("%s: badge %s, want %s", name, got, c.want)
		}
	}
}
