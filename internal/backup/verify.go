// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"time"
)

var errAppendOnly = errors.New("target is append-only: this box cannot delete from it")

func errUnknownTarget(id string) error { return fmt.Errorf("no target %q", id) }

// VerifyRestore proves that the newest snapshot of u (at least
// schedule.verify_min_age old) can be restored: it restores it into an empty
// scratch directory, reads every restored file back and compares it with the
// snapshot's listing, and runs each hook's check on the restored copy (SQLite
// integrity_check, audit chain against the tagged head). Only these fresh
// reads count; nothing restic or the app reports about itself is trusted
// (BACKUPS.md §8, D-B7.6). The scratch directory is always deleted.
//
// Starting the restored app in a sealed namespace with fresh probes is the
// gateway's part (K7); this is the node-side, file-level proof.
func (a *Agent) VerifyRestore(ctx context.Context, u Unit, targetID string) (Verification, error) {
	return a.VerifyRestoreMinAge(ctx, u, targetID, a.Cfg.Schedule.VerifyMinAge.Duration)
}

// VerifyRestoreMinAge is VerifyRestore with the minimum snapshot age given;
// 0 verifies the newest snapshot (an owner's "verify now", contract §12.5
// backup.verify {latest: true}).
func (a *Agent) VerifyRestoreMinAge(ctx context.Context, u Unit, targetID string, minAge time.Duration) (Verification, error) {
	t, ok := a.target(targetID)
	if !ok {
		return Verification{}, errUnknownTarget(targetID)
	}
	if err := a.acquire(ctx, "verify:"+u.Name); err != nil {
		return Verification{}, err
	}
	defer a.release()
	v := Verification{ID: "ver_" + NewRunID(a.Now())[4:], Unit: u.Name, TargetID: t.ID, Kind: "restore",
		StartedAt: a.Now().UTC(), Details: map[string]any{}}
	verdict, err := a.verifyRestore(ctx, u, t, &v, minAge)
	v.Verdict, v.FinishedAt = verdict, a.Now().UTC()
	if err != nil {
		v.Details["error"] = err.Error()
	}
	serr := a.Store.Update(func(s *State) {
		s.Verifications = append(s.Verifications, v)
		if verdict == VerdictPassed {
			s.LastVerified[u.Name] = v
		}
	})
	a.Log.Info("verified restore", "unit", u.Name, "snapshot", v.SnapshotID, "verdict", verdict, "error", err)
	return v, serr
}

func (a *Agent) verifyRestore(ctx context.Context, u Unit, t Target, v *Verification, minAge time.Duration) (string, error) {
	repo, err := a.readyRepo(ctx, t)
	if err != nil {
		return VerdictError, err
	}
	snaps, err := repo.Snapshots(ctx, []string{"onemind", "box=" + a.Cfg.BoxID, "unit=" + u.Name})
	if err != nil {
		return VerdictError, err
	}
	cutoff := a.Now().Add(-minAge)
	var snap *Snapshot
	for i := range snaps {
		s := &snaps[i]
		if !s.Time.After(cutoff) && (snap == nil || s.Time.After(snap.Time)) {
			snap = s
		}
	}
	if snap == nil {
		return VerdictError, fmt.Errorf("no snapshot of %s older than %s", u.Name, minAge)
	}
	v.SnapshotID = snap.ID
	v.Details["snapshot_time"] = snap.Time.UTC().Format(time.RFC3339)

	if err := os.MkdirAll(a.Cfg.ScratchDir, 0o700); err != nil {
		return VerdictError, err
	}
	scratch, err := os.MkdirTemp(a.Cfg.ScratchDir, "verify-"+stagingName(u.Name)+"-")
	if err != nil {
		return VerdictError, err
	}
	defer os.RemoveAll(scratch)

	if err := repo.Restore(ctx, snap.ID, "/", scratch); err != nil {
		return VerdictFailed, fmt.Errorf("restore: %w", err)
	}
	nodes, err := repo.Ls(ctx, snap.ID, "/", true)
	if err != nil {
		return VerdictError, err
	}
	files, bytes, err := compareRestored(scratch, nodes)
	v.Details["files"], v.Details["bytes"] = files, bytes
	if err != nil {
		return VerdictFailed, err
	}
	staging := filepath.Join(scratch, filepath.Join(a.Cfg.StateDir, "staging", stagingName(u.Name)))
	var checks []string
	for _, h := range u.Hooks {
		if err := h.VerifyRestored(ctx, staging, *snap); err != nil {
			return VerdictFailed, err
		}
		checks = append(checks, hookKind(h))
	}
	sort.Strings(checks)
	v.Details["checks"] = checks
	return VerdictPassed, nil
}

// compareRestored reads every regular file the snapshot lists back from the
// scratch tree and checks its size.
func compareRestored(root string, nodes []Node) (int, int64, error) {
	var files int
	var total int64
	buf := make([]byte, 1<<20)
	for _, n := range nodes {
		p := filepath.Join(root, filepath.FromSlash(n.Path))
		switch n.Type {
		case "dir":
			fi, err := os.Lstat(p)
			if err != nil || !fi.IsDir() {
				return files, total, fmt.Errorf("restored directory %s missing", n.Path)
			}
		case "file":
			f, err := os.Open(p)
			if err != nil {
				return files, total, fmt.Errorf("restored file %s: %w", n.Path, err)
			}
			got, err := io.CopyBuffer(io.Discard, f, buf)
			f.Close()
			if err != nil {
				return files, total, fmt.Errorf("read restored %s: %w", n.Path, err)
			}
			if got != n.Size {
				return files, total, fmt.Errorf("restored %s has %d bytes, snapshot says %d", n.Path, got, n.Size)
			}
			files++
			total += got
		}
	}
	return files, total, nil
}

// CheckRepo runs `restic check` reading a rotating slice of the data: one
// seventh a day on local and node targets so everything is read every week,
// one twenty-eighth on S3 to limit egress cost (BACKUPS.md §3). A failure is
// retried once before it is recorded, because a flaky read is more common
// than real damage.
func (a *Agent) CheckRepo(ctx context.Context, targetID string) (Verification, error) {
	t, ok := a.target(targetID)
	if !ok {
		return Verification{}, errUnknownTarget(targetID)
	}
	if err := a.acquire(ctx, "check"); err != nil {
		return Verification{}, err
	}
	defer a.release()
	now := a.Now()
	parts := 7
	if t.Kind == KindS3 {
		parts = 28
	}
	subset := fmt.Sprintf("%d/%d", now.YearDay()%parts+1, parts)
	v := Verification{ID: "chk_" + NewRunID(now)[4:], Unit: "repository", TargetID: t.ID, Kind: "check",
		StartedAt: now.UTC(), Details: map[string]any{"read_data_subset": subset}}
	repo, err := a.readyRepo(ctx, t)
	if err == nil {
		if err = repo.Check(ctx, subset); err != nil && ctx.Err() == nil {
			v.Details["first_attempt"] = err.Error()
			err = repo.Check(ctx, subset)
		}
	}
	switch {
	case err == nil:
		v.Verdict = VerdictPassed
	case isDamage(err):
		v.Verdict = VerdictFailed
		v.Details["error"] = err.Error()
	default:
		v.Verdict = VerdictError
		v.Details["error"] = err.Error()
	}
	v.FinishedAt = a.Now().UTC()
	return v, a.Store.Update(func(s *State) { s.Verifications = append(s.Verifications, v) })
}

// isDamage reports a check that ran and found a problem (restic exit 1), as
// opposed to one that could not run (no repository, lock, wrong key).
func isDamage(err error) bool {
	var re *ResticError
	return errors.As(err, &re) && re.ExitCode == 1
}

func hookKind(h Hook) string {
	switch h.(type) {
	case *SQLiteHook:
		return "sqlite_integrity"
	case *AuditLogHook:
		return "audit_chain"
	case *CommandOutputHook:
		return "dump_present"
	}
	return "custom"
}
