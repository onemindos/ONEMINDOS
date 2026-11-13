// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// Job kinds the agent runs (contract §12.11 job kinds, plus the reads the
// gateway's owner-only browse routes need). Every one arrives signed.
const (
	KindConfigure     = "backup.configure"      // destinations and their credentials
	KindRun           = "backup.run"            // one run, optionally with the gateway's app list
	KindSnapshots     = "backup.snapshots"      // list restore points
	KindTree          = "backup.tree"           // browse a snapshot folder
	KindFile          = "backup.file"           // download one file
	KindRestore       = "backup.restore"        // scope path (one file or folder) or app
	KindRestoreFinish = "backup.restore.finish" // commit or roll back an app restore
	KindVerify        = "backup.verify"         // scratch restore (badge) or repository check
	KindKeyAdd        = "backup.key.add"        // owner or escrow key on every destination
	KindStatus        = "backup.status"         // badges, runs and verifications
)

// JobResult is the reply to every job except a successful backup.file.
type JobResult struct {
	JobID  string `json:"job_id"`
	Kind   string `json:"kind"`
	State  string `json:"state"` // succeeded | failed
	Result any    `json:"result,omitempty"`
	Error  string `json:"error,omitempty"`
}

const maxJobBody = 1 << 20

func (a *Agent) jobsHandler(base context.Context) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if a.Jobs == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "no_key", "detail": "signed jobs are not configured"})
			return
		}
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxJobBody))
		if err != nil {
			writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "bad_job", "detail": err.Error()})
			return
		}
		j, err := a.Jobs.Verify(body)
		if err != nil {
			code, slug := http.StatusBadRequest, "bad_job"
			var je *JobError
			if errors.As(err, &je) {
				slug = je.Code
				switch je.Code {
				case "bad_signature", "no_key":
					code = http.StatusForbidden
				case "expired", "replayed":
					code = http.StatusConflict
				}
			}
			a.Log.Warn("job refused", "error", err)
			writeJSON(w, code, map[string]string{"error": slug, "detail": err.Error()})
			return
		}
		// Long jobs keep running if the gateway gives up waiting, so a
		// half-done restore is never abandoned midway.
		ctx, cancel := context.WithTimeout(base, 12*time.Hour)
		defer cancel()
		if j.Kind == KindFile {
			a.serveFile(ctx, w, j)
			return
		}
		out, err := a.runJobKind(ctx, j)
		res := JobResult{JobID: j.ID, Kind: j.Kind, State: StateSucceeded, Result: out}
		var bad badParams
		switch {
		case errors.As(err, &bad):
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad_job", "detail": err.Error()})
			return
		case err != nil:
			res.State, res.Error = StateFailed, err.Error()
		}
		a.Log.Info("job", "job", j.ID, "kind", j.Kind, "action", j.ActionID, "state", res.State, "error", res.Error)
		writeJSON(w, http.StatusOK, res)
	}
}

type badParams struct{ error }

func decodeParams(raw json.RawMessage, v any) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		return badParams{fmt.Errorf("params: %w", err)}
	}
	return nil
}

func (a *Agent) runJobKind(ctx context.Context, j Job) (any, error) {
	switch j.Kind {
	case KindConfigure:
		var p ConfigureRequest
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		if err := a.acquire(ctx, "configure"); err != nil {
			return nil, err
		}
		defer a.release()
		c, err := a.Configure(p)
		if err != nil {
			return nil, err
		}
		ids := []string{}
		for _, t := range c.Targets {
			ids = append(ids, t.ID)
		}
		return map[string]any{"targets": ids}, nil

	case KindRun:
		var p struct {
			Reason    string     `json:"reason"`
			Units     []string   `json:"units"`
			SkipUnits []string   `json:"skip_units"` // all units but these (apps whose hooks failed)
			Apps      *[]AppSpec `json:"apps"`
			TargetID  string     `json:"target_id"`
			RunID     string     `json:"run_id"`
		}
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		if p.RunID != "" && !tagValueRe.MatchString(p.RunID) {
			return nil, badParams{fmt.Errorf("run_id must be tag-safe")}
		}
		if p.Apps != nil {
			if err := a.SetApps(*p.Apps); err != nil {
				return nil, err
			}
		}
		units := p.Units
		if len(units) == 0 && len(p.SkipUnits) > 0 {
			all, err := a.Units(ctx)
			if err != nil {
				return nil, err
			}
			skip := map[string]bool{}
			for _, u := range p.SkipUnits {
				skip[u] = true
			}
			for _, u := range all {
				if !skip[u.Name] {
					units = append(units, u.Name)
				}
			}
			if len(units) == 0 {
				return nil, errors.New("every unit was skipped")
			}
		}
		return a.Run(ctx, RunRequest{ID: p.RunID, Reason: p.Reason, ActionID: j.ActionID, TargetID: p.TargetID,
			Units: units, Wait: true})

	case KindSnapshots:
		var p struct {
			TargetID string `json:"target_id"`
			Unit     string `json:"unit"`
		}
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		return a.ListSnapshots(ctx, p.TargetID, p.Unit)

	case KindTree:
		var p struct {
			TargetID   string `json:"target_id"`
			SnapshotID string `json:"snapshot_id"`
			Path       string `json:"path"`
		}
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		return a.Tree(ctx, p.TargetID, p.SnapshotID, p.Path)

	case KindRestore:
		var p struct {
			TargetID   string `json:"target_id"`
			SnapshotID string `json:"snapshot_id"`
			Scope      string `json:"scope"`
			Path       string `json:"path"`
			AppID      string `json:"app_id"`
			Stamp      string `json:"stamp"`
			Strict     bool   `json:"strict_files"`
		}
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		switch p.Scope {
		case "path":
			return a.RestorePath(ctx, RestoreRequest{TargetID: p.TargetID, SnapshotID: p.SnapshotID, Path: p.Path, ActionID: j.ActionID})
		case "app":
			return a.RestoreApp(ctx, AppRestoreRequest{TargetID: p.TargetID, SnapshotID: p.SnapshotID, AppID: p.AppID, Stamp: p.Stamp, StrictFiles: p.Strict})
		}
		return nil, badParams{fmt.Errorf("scope must be path or app")}

	case KindRestoreFinish:
		var p FinishRestoreRequest
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		n, err := a.FinishRestore(ctx, p)
		return map[string]any{"items": n, "committed": p.Commit}, err

	case KindVerify:
		var p struct {
			Mode     string   `json:"mode"`
			Units    []string `json:"units"`
			TargetID string   `json:"target_id"`
			Latest   bool     `json:"latest"`
		}
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		switch p.Mode {
		case "check":
			v, err := a.CheckRepo(ctx, p.TargetID)
			return []Verification{v}, err
		case "restore":
			units, err := a.selectUnits(ctx, p.Units)
			if err != nil {
				return nil, err
			}
			minAge := a.Cfg.Schedule.VerifyMinAge.Duration
			if p.Latest {
				minAge = 0
			}
			out := []Verification{}
			for _, u := range units {
				v, err := a.VerifyRestoreMinAge(ctx, u, p.TargetID, minAge)
				if err != nil {
					return out, err
				}
				out = append(out, v)
			}
			return out, nil
		}
		return nil, badParams{fmt.Errorf("mode must be restore or check")}

	case KindKeyAdd:
		var p struct {
			Which string `json:"which"`
			Key   string `json:"key"`
		}
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		if p.Which != "owner" && p.Which != "escrow" {
			return nil, badParams{fmt.Errorf("which must be owner or escrow")}
		}
		if len(p.Key) < 32 || strings.ContainsAny(p.Key, "\r\n") {
			return nil, badParams{fmt.Errorf("key must be at least 32 characters on one line")}
		}
		return a.AddKey(ctx, p.Key)

	case KindStatus:
		var p struct{}
		if err := decodeParams(j.Params, &p); err != nil {
			return nil, err
		}
		s, err := a.Status(ctx)
		if err != nil {
			return nil, err
		}
		st := a.Store.View()
		return map[string]any{"status": s, "runs": lastN(st.Runs, 50), "verifications": lastN(st.Verifications, 50)}, nil
	}
	return nil, badParams{fmt.Errorf("unknown job kind %q", j.Kind)}
}

func lastN[T any](s []T, n int) []T {
	if len(s) > n {
		s = s[len(s)-n:]
	}
	if s == nil {
		return []T{}
	}
	return s
}

// KeyResult is the outcome of adding a key on one destination.
type KeyResult struct {
	TargetID string `json:"target_id"`
	OK       bool   `json:"ok"`
	Error    string `json:"error,omitempty"`
}

// AddKey adds a recovery key to every destination's repository (BACKUPS.md
// §5.1: the same keys open every target). The key exists on disk only in a
// 0600 temporary file while restic reads it.
func (a *Agent) AddKey(ctx context.Context, key string) ([]KeyResult, error) {
	if err := a.acquire(ctx, "key-add"); err != nil {
		return nil, err
	}
	defer a.release()
	c := a.conf()
	if len(c.Targets) == 0 {
		return nil, errors.New("no destination is set up yet")
	}
	if err := os.MkdirAll(c.StateDir, 0o700); err != nil {
		return nil, err
	}
	f, err := os.CreateTemp(c.StateDir, ".key-*")
	if err != nil {
		return nil, err
	}
	defer os.Remove(f.Name())
	if _, err := f.WriteString(key + "\n"); err != nil {
		f.Close()
		return nil, err
	}
	if err := f.Close(); err != nil {
		return nil, err
	}
	out := []KeyResult{}
	var failed int
	for _, t := range c.Targets {
		r := KeyResult{TargetID: t.ID}
		repo, err := a.readyRepo(ctx, t)
		if err == nil {
			err = repo.AddKey(ctx, f.Name())
		}
		if err != nil {
			r.Error, failed = err.Error(), failed+1
		} else {
			r.OK = true
		}
		out = append(out, r)
	}
	if failed > 0 {
		return out, fmt.Errorf("the key could not be added on %d of %d destinations", failed, len(out))
	}
	return out, nil
}

// serveFile streams one file of a snapshot. Content-Length is the size the
// snapshot lists, so a restic failure midway reaches the gateway as a short
// body, never as a complete-looking file.
func (a *Agent) serveFile(ctx context.Context, w http.ResponseWriter, j Job) {
	var p struct {
		TargetID   string `json:"target_id"`
		SnapshotID string `json:"snapshot_id"`
		Path       string `json:"path"`
	}
	fail := func(code int, err error) {
		a.Log.Info("job", "job", j.ID, "kind", j.Kind, "state", StateFailed, "error", err)
		writeJSON(w, code, JobResult{JobID: j.ID, Kind: j.Kind, State: StateFailed, Error: err.Error()})
	}
	if err := decodeParams(j.Params, &p); err != nil {
		fail(http.StatusBadRequest, err)
		return
	}
	repo, snap, err := a.findSnapshot(ctx, p.TargetID, p.SnapshotID)
	if err != nil {
		fail(http.StatusOK, err)
		return
	}
	n, err := lookupNode(ctx, repo, snap.ID, cleanSnapPath(p.Path))
	if err != nil {
		fail(http.StatusOK, err)
		return
	}
	if n.Type != "file" {
		fail(http.StatusOK, fmt.Errorf("%s is a %s, not a file", p.Path, n.Type))
		return
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("Content-Length", strconv.FormatInt(n.Size, 10))
	w.Header().Set("OneMind-Job-State", StateSucceeded)
	w.Header().Set("OneMind-File-Name", filepath.Base(n.Path))
	w.WriteHeader(http.StatusOK)
	if err := repo.Dump(ctx, snap.ID, cleanSnapPath(p.Path), w); err != nil {
		a.Log.Warn("file download broke off", "job", j.ID, "error", err)
	}
}
