// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"testing"
	"time"
)

func TestSlots(t *testing.T) {
	now := time.Date(2026, 11, 12, 10, 30, 0, 0, time.UTC) // a Thursday
	if got := hourlySlot(now, 17); !got.Equal(time.Date(2026, 11, 12, 10, 17, 0, 0, time.UTC)) {
		t.Fatalf("hourly = %v", got)
	}
	if got := hourlySlot(now, 45); !got.Equal(time.Date(2026, 11, 12, 9, 45, 0, 0, time.UTC)) {
		t.Fatalf("hourly before minute = %v", got)
	}
	if got := dailySlot(now, 3, 17); !got.Equal(time.Date(2026, 11, 12, 3, 17, 0, 0, time.UTC)) {
		t.Fatalf("daily = %v", got)
	}
	if got := weeklySlot(now, time.Sunday, 3, 17); !got.Equal(time.Date(2026, 11, 8, 3, 17, 0, 0, time.UTC)) {
		t.Fatalf("weekly = %v", got)
	}
}

func TestTickRunsHourlyThenWaitsForNextSlot(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	f.agent.Tick(ctx, f.clock) // first start: hourly due now, daily/weekly start counting
	if n := len(f.agent.Store.View().Runs); n != 1 {
		t.Fatalf("runs after first tick = %d", n)
	}
	f.clock = f.clock.Add(10 * time.Minute) // 10:40, next slot 11:17
	f.agent.Tick(ctx, f.clock)
	if n := len(f.agent.Store.View().Runs); n != 1 {
		t.Fatalf("ran again before the slot: %d", n)
	}
	f.clock = time.Date(2026, 11, 12, 11, 17, 0, 0, time.UTC)
	f.agent.Tick(ctx, f.clock)
	if n := len(f.agent.Store.View().Runs); n != 2 {
		t.Fatalf("runs at slot = %d", n)
	}
	// a box that was off for a day catches up with one run, not 24
	f.clock = f.clock.Add(26 * time.Hour) // 13 Nov 13:17: also past the daily 03:17 slot
	f.agent.Tick(ctx, f.clock)
	st := f.agent.Store.View()
	primaryRuns, offsite := 0, 0
	for _, r := range st.Runs {
		if r.TargetID == "usb1" {
			primaryRuns++
		} else {
			offsite++
		}
	}
	if primaryRuns != 3 || offsite != 1 {
		t.Fatalf("after catch-up: %d primary runs, %d off-site", primaryRuns, offsite)
	}
	checks := 0
	for _, v := range st.Verifications {
		if v.Kind == "check" {
			checks++
		}
	}
	if checks != 1 {
		t.Fatalf("checks = %d", checks)
	}
}

func TestWeeklyVerifiesEveryUnit(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	f.agent.Tick(ctx, f.clock)                               // Thu 10:30: first run
	f.clock = time.Date(2026, 11, 15, 3, 17, 0, 0, time.UTC) // Sunday maintenance slot
	f.agent.Tick(ctx, f.clock)
	st := f.agent.Store.View()
	if len(st.LastVerified) != 4 {
		t.Fatalf("verified units = %v (verifications %+v)", st.LastVerified, st.Verifications)
	}
	s, _ := f.agent.Status(ctx)
	if s.Box.State != BadgeVerified {
		t.Fatalf("box badge = %+v", s.Box)
	}
}
