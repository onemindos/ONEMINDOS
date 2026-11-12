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
	"strings"
	"time"
)

// Rewind is the snapshot browse / list / restore-one-path surface
// (BACKUPS.md §7.1, CONTRACT-12-DRAFT §12.5). These are Go functions with
// JSON types; the gateway exposes them owner-only and audited, and restoring
// is always the approved action `backup.restore {scope: path}`.

// SnapshotInfo is one entry of GET /v1/backups/snapshots.
type SnapshotInfo struct {
	ID          string    `json:"id"`
	ShortID     string    `json:"short_id"`
	Unit        string    `json:"unit"`
	AppID       string    `json:"app_id,omitempty"`
	NodeID      string    `json:"node_id"`
	TakenAt     time.Time `json:"taken_at"`
	RunID       string    `json:"run_id,omitempty"`
	Reason      string    `json:"reason"`
	AppRevision string    `json:"app_revision,omitempty"`
	K3sVersion  string    `json:"k3s_version,omitempty"`
	Paths       []string  `json:"paths"`
	Tags        []string  `json:"tags"`
}

// TreeEntry is one entry of GET /v1/backups/snapshots/{id}/tree.
type TreeEntry struct {
	Name  string    `json:"name"`
	Path  string    `json:"path"`
	Type  string    `json:"type"` // file | dir | symlink | other
	Size  int64     `json:"size"`
	Mtime time.Time `json:"mtime"`
}

// RestoreRequest restores one file or directory from a snapshot in place.
type RestoreRequest struct {
	TargetID   string `json:"target_id,omitempty"`
	SnapshotID string `json:"snapshot_id"`
	Path       string `json:"path"`
	ActionID   string `json:"action_id,omitempty"`
}

// RestoreResult says what was restored and how to undo it: restoring
// PreRestoreSnapshotID at the same path brings back what was there before.
// When the path did not exist before, PreRestoreSnapshotID is empty and
// undo means deleting the restored path.
type RestoreResult struct {
	Path                 string    `json:"path"`
	Type                 string    `json:"type"`
	SnapshotID           string    `json:"snapshot_id"`
	PreRestoreSnapshotID string    `json:"pre_restore_snapshot_id,omitempty"`
	Size                 int64     `json:"size"`
	Mtime                time.Time `json:"mtime"`
}

func toInfo(s Snapshot) SnapshotInfo {
	return SnapshotInfo{ID: s.ID, ShortID: s.ShortID, Unit: s.Tag("unit"), AppID: s.Tag("app"), NodeID: s.Tag("node"),
		TakenAt: s.Time.UTC(), RunID: s.Tag("run"), Reason: s.Tag("reason"), AppRevision: s.Tag("rev"),
		K3sVersion: s.Tag("k3s"), Paths: s.Paths, Tags: s.Tags}
}

// ListSnapshots lists this box's snapshots on a target, newest first,
// optionally only one unit. Fence records are not restore points.
func (a *Agent) ListSnapshots(ctx context.Context, targetID, unit string) ([]SnapshotInfo, error) {
	repo, _, err := a.browseRepo(ctx, targetID)
	if err != nil {
		return nil, err
	}
	filter := []string{"onemind", "box=" + a.Cfg.BoxID}
	if unit != "" {
		filter = append(filter, "unit="+unit)
	}
	snaps, err := repo.Snapshots(ctx, filter)
	if err != nil {
		return nil, err
	}
	out := []SnapshotInfo{}
	for _, s := range snaps {
		if s.Tag("unit") != "fence" {
			out = append(out, toInfo(s))
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].TakenAt.After(out[j].TakenAt) })
	return out, nil
}

// Tree lists the direct children of dir in a snapshot.
func (a *Agent) Tree(ctx context.Context, targetID, snapshotID, dir string) ([]TreeEntry, error) {
	repo, snap, err := a.findSnapshot(ctx, targetID, snapshotID)
	if err != nil {
		return nil, err
	}
	nodes, err := repo.Ls(ctx, snap.ID, cleanSnapPath(dir), false)
	if err != nil {
		return nil, err
	}
	out := []TreeEntry{}
	for _, n := range nodes {
		typ := n.Type
		if typ != "file" && typ != "dir" && typ != "symlink" {
			typ = "other"
		}
		out = append(out, TreeEntry{Name: n.Name, Path: cleanSnapPath(n.Path), Type: typ, Size: n.Size, Mtime: n.Mtime})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out, nil
}

// DumpFile streams one regular file of a snapshot to w.
func (a *Agent) DumpFile(ctx context.Context, targetID, snapshotID, path string, w io.Writer) error {
	repo, snap, err := a.findSnapshot(ctx, targetID, snapshotID)
	if err != nil {
		return err
	}
	n, err := lookupNode(ctx, repo, snap.ID, cleanSnapPath(path))
	if err != nil {
		return err
	}
	if n.Type != "file" {
		return fmt.Errorf("%s is a %s, not a file", path, n.Type)
	}
	return repo.Dump(ctx, snap.ID, cleanSnapPath(path), w)
}

// RestorePath puts one file or directory from a snapshot back at its
// original place. Before it changes anything it snapshots what is there now
// (reason=pre-restore), so every restore can be undone. The new content is
// written beside the target and renamed over it, so a crash leaves either
// the old or the new version, never half of one. Only paths inside the
// unit's current sources can be restored, and never through a symlink.
func (a *Agent) RestorePath(ctx context.Context, req RestoreRequest) (RestoreResult, error) {
	if err := a.acquire(ctx, "restore"); err != nil {
		return RestoreResult{}, err
	}
	defer a.release()
	repo, snap, err := a.findSnapshot(ctx, req.TargetID, req.SnapshotID)
	if err != nil {
		return RestoreResult{}, err
	}
	p := cleanSnapPath(req.Path)
	if p == "/" {
		return RestoreResult{}, errors.New("restore one path: path is required")
	}
	unit, err := a.restorableUnit(ctx, snap, p)
	if err != nil {
		return RestoreResult{}, err
	}
	n, err := lookupNode(ctx, repo, snap.ID, p)
	if err != nil {
		return RestoreResult{}, err
	}
	if n.Type != "file" && n.Type != "dir" {
		return RestoreResult{}, fmt.Errorf("%s is a %s; only files and directories can be restored", p, n.Type)
	}
	dest := filepath.FromSlash(p)
	if err := safeParent(dest); err != nil {
		return RestoreResult{}, err
	}
	res := RestoreResult{Path: p, Type: n.Type, SnapshotID: snap.ID, Size: n.Size, Mtime: n.Mtime}

	if _, err := os.Lstat(dest); err == nil {
		pre, err := a.preRestoreSnapshot(ctx, repo, unit, dest, req)
		if err != nil {
			return res, fmt.Errorf("pre-restore snapshot failed, nothing was changed: %w", err)
		}
		res.PreRestoreSnapshotID = pre
	} else if !errors.Is(err, os.ErrNotExist) {
		return res, err
	}

	if n.Type == "file" {
		err = restoreFile(ctx, repo, snap.ID, p, dest, n)
	} else {
		err = restoreDir(ctx, repo, snap.ID, p, dest, n, a.Now())
	}
	a.Log.Info("rewind restore", "path", p, "snapshot", snap.ID, "pre_restore", res.PreRestoreSnapshotID, "error", err)
	return res, err
}

// restorableUnit checks that p is inside both the snapshot and the current
// sources of the snapshot's unit, and not inside the hook staging area.
func (a *Agent) restorableUnit(ctx context.Context, snap Snapshot, p string) (Unit, error) {
	if isUnder(p, cleanSnapPath(filepath.ToSlash(a.Cfg.StateDir))) {
		return Unit{}, errors.New("hook copies (database dumps, audit log) are restored by the unit restore, not in place")
	}
	inSnap := false
	for _, sp := range snap.Paths {
		inSnap = inSnap || isUnder(p, cleanSnapPath(filepath.ToSlash(sp)))
	}
	if !inSnap {
		return Unit{}, fmt.Errorf("%s is not in snapshot %s", p, snap.ShortID)
	}
	units, err := a.Units(ctx)
	if err != nil {
		return Unit{}, err
	}
	name := snap.Tag("unit")
	for _, u := range units {
		if u.Name != name {
			continue
		}
		for _, src := range u.Paths {
			if isUnder(p, cleanSnapPath(filepath.ToSlash(src))) {
				return u, nil
			}
		}
		return Unit{}, fmt.Errorf("%s is outside the current sources of %s", p, name)
	}
	return Unit{}, fmt.Errorf("unit %s is not backed up on this node any more", name)
}

func (a *Agent) preRestoreSnapshot(ctx context.Context, repo Repo, u Unit, dest string, req RestoreRequest) (string, error) {
	run := Run{ID: NewRunID(a.Now()), Reason: ReasonPreRestore, ActionID: req.ActionID, TargetID: req.TargetID,
		StartedAt: a.Now().UTC()}
	if run.TargetID == "" {
		p, _ := a.target("")
		run.TargetID = p.ID
	}
	tags := append(a.baseTags(u.Name), "run="+run.ID, "reason="+ReasonPreRestore, "keep="+keepClass(ReasonPreRestore))
	tags = append(tags, u.Tags...)
	res, err := repo.Backup(ctx, BackupRequest{Paths: []string{dest}, Tags: tags, Host: a.Cfg.NodeID})
	end := a.Now().UTC()
	run.FinishedAt = &end
	ur := UnitResult{Unit: u.Name, State: StateSucceeded, SnapshotID: res.SnapshotID}
	switch {
	case err != nil:
		ur.State, ur.Error = StateFailed, err.Error()
	case res.Incomplete:
		ur.State, ur.Error, err = StateFailed, "some files could not be read", errors.New("some files could not be read")
	}
	run.State, run.Units, run.BytesAdded = ur.State, []UnitResult{ur}, res.DataAdded
	_ = a.Store.Update(func(s *State) { s.Runs = append(s.Runs, run) })
	return res.SnapshotID, err
}

func restoreFile(ctx context.Context, repo Repo, id, p, dest string, n Node) error {
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(dest), ".onemind-restore-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if err := repo.Dump(ctx, id, p, tmp); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Chmod(n.Mode.Perm()); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Chtimes(tmp.Name(), n.Mtime, n.Mtime); err != nil {
		return err
	}
	if fi, err := os.Lstat(dest); err == nil && fi.IsDir() {
		return fmt.Errorf("%s is now a directory; restore it as a directory or move it first", dest)
	}
	return os.Rename(tmp.Name(), dest)
}

func restoreDir(ctx context.Context, repo Repo, id, p, dest string, n Node, now time.Time) error {
	parent := filepath.Dir(dest)
	if err := os.MkdirAll(parent, 0o755); err != nil {
		return err
	}
	tmp, err := os.MkdirTemp(parent, ".onemind-restore-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(tmp)
	if err := repo.Restore(ctx, id, p, tmp); err != nil {
		return err
	}
	if err := os.Chmod(tmp, n.Mode.Perm()); err != nil {
		return err
	}
	_ = os.Chtimes(tmp, n.Mtime, n.Mtime)
	old := ""
	if _, err := os.Lstat(dest); err == nil {
		old = dest + ".onemind-old-" + now.UTC().Format("20060102T150405Z")
		if err := os.Rename(dest, old); err != nil {
			return err
		}
	}
	if err := os.Rename(tmp, dest); err != nil {
		if old != "" {
			_ = os.Rename(old, dest)
		}
		return err
	}
	if old != "" {
		return os.RemoveAll(old) // the pre-restore snapshot holds it
	}
	return nil
}

// safeParent refuses a destination whose existing ancestors include a
// symlink, so a restore cannot be redirected outside the unit's sources.
func safeParent(dest string) error {
	if fi, err := os.Lstat(dest); err == nil && fi.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("%s is a symlink; refusing to restore over it", dest)
	}
	dir := filepath.Dir(dest)
	for {
		if _, err := os.Lstat(dir); err == nil {
			break
		}
		next := filepath.Dir(dir)
		if next == dir {
			break
		}
		dir = next
	}
	real, err := filepath.EvalSymlinks(dir)
	if err != nil {
		return err
	}
	if real != dir {
		return fmt.Errorf("%s goes through a symlink (%s); refusing to restore", dest, real)
	}
	return nil
}

func lookupNode(ctx context.Context, repo Repo, id, p string) (Node, error) {
	nodes, err := repo.Ls(ctx, id, pathDir(p), false)
	if err != nil {
		return Node{}, err
	}
	for _, n := range nodes {
		if cleanSnapPath(n.Path) == p {
			return n, nil
		}
	}
	return Node{}, fmt.Errorf("%s: %w", p, os.ErrNotExist)
}

func (a *Agent) browseRepo(ctx context.Context, targetID string) (Repo, Target, error) {
	t, ok := a.target(targetID)
	if !ok {
		return nil, t, errUnknownTarget(targetID)
	}
	repo, err := a.readyRepo(ctx, t)
	return repo, t, err
}

// findSnapshot resolves a full id or a short id (at least 8 characters)
// among this box's snapshots.
func (a *Agent) findSnapshot(ctx context.Context, targetID, id string) (Repo, Snapshot, error) {
	if len(id) < 8 || !tagValueRe.MatchString(id) {
		return nil, Snapshot{}, fmt.Errorf("snapshot id %q is too short or malformed", id)
	}
	repo, _, err := a.browseRepo(ctx, targetID)
	if err != nil {
		return nil, Snapshot{}, err
	}
	snaps, err := repo.Snapshots(ctx, []string{"onemind", "box=" + a.Cfg.BoxID})
	if err != nil {
		return nil, Snapshot{}, err
	}
	var found []Snapshot
	for _, s := range snaps {
		if strings.HasPrefix(s.ID, id) && s.Tag("unit") != "fence" {
			found = append(found, s)
		}
	}
	switch len(found) {
	case 0:
		return nil, Snapshot{}, fmt.Errorf("snapshot %s: %w", id, os.ErrNotExist)
	case 1:
		return repo, found[0], nil
	}
	return nil, Snapshot{}, fmt.Errorf("snapshot id %q is ambiguous", id)
}
