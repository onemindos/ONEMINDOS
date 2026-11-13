// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"log/slog"
	"os"
	"strings"
	"testing"
	"time"
)

// breakStateDisk makes every later write of state.json fail (the state directory becomes a
// plain file), the way a full or read-only disk would, and works for root too.
func breakStateDisk(t *testing.T, f *fixture) {
	t.Helper()
	if err := os.RemoveAll(f.cfg.StateDir); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(f.cfg.StateDir, []byte("not a directory"), 0o600); err != nil {
		t.Fatal(err)
	}
}

// CS2-01: a failed write of the scheduler's "last job" record must be logged and counted, and the
// finished job must not run again in a loop while the disk stays broken.
func TestTickStateWriteFailureIsSurfacedAndDoesNotLoop(t *testing.T) {
	f := newFixture(t)
	var logs bytes.Buffer
	f.agent.Log = slog.New(slog.NewTextHandler(&logs, nil))
	breakStateDisk(t, f)
	ctx := context.Background()
	f.agent.Tick(ctx, f.clock)
	first := len(f.agent.Store.View().Runs)
	if first != 1 {
		t.Fatalf("runs after first tick = %d", first)
	}
	f.agent.Tick(ctx, f.clock) // same slot: must not re-run
	f.agent.Tick(ctx, f.clock.Add(5*time.Minute))
	if n := len(f.agent.Store.View().Runs); n != first {
		t.Fatalf("job re-ran %d times while the state disk was broken", n-first)
	}
	if f.agent.stateErrs.Load() == 0 || !strings.Contains(logs.String(), "backup state could not be saved") {
		t.Fatalf("failed state writes were not logged and counted (count %d, log %q)", f.agent.stateErrs.Load(), logs.String())
	}
	st, err := f.agent.Status(ctx)
	if err != nil || st.StateWriteErrors == 0 {
		t.Fatalf("status must show the failed writes: %+v err %v", st, err)
	}
}

// CS2-02: a failed write of the pre-restore run record is surfaced, but the restore itself (which
// already holds a safety snapshot) still completes: bookkeeping must never block recovery.
func TestRewindStateWriteFailureIsSurfaced(t *testing.T) {
	f := newFixture(t)
	f.run(ReasonScheduled)
	snap := appSnapshot(t, f)
	file := f.path("data/onemind/storage/photos/a.jpg")
	f.write("data/onemind/storage/photos/a.jpg", "edited-later")
	f.clock = f.clock.Add(time.Hour)
	before := f.agent.stateErrs.Load()
	breakStateDisk(t, f)
	res, err := f.agent.RestorePath(context.Background(), RestoreRequest{SnapshotID: snap.ID, Path: file})
	if err != nil || res.PreRestoreSnapshotID == "" {
		t.Fatalf("restore must complete with its safety snapshot: %+v %v", res, err)
	}
	if f.agent.stateErrs.Load() <= before {
		t.Fatal("failed pre-restore record was not counted")
	}
}

// CS2-02: the run finish record returns its error to the caller instead of dropping it.
func TestRunFinishReportsStateWriteFailure(t *testing.T) {
	f := newFixture(t)
	breakStateDisk(t, f)
	run, err := f.agent.Run(context.Background(), RunRequest{Reason: ReasonManual})
	if err == nil {
		t.Fatalf("run %+v: a failed state write must be returned", run)
	}
}
