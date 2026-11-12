// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// App restore (BACKUPS.md §7.2, steps 4 and 7). The gateway has already taken
// the pre-restore snapshot and scaled the app to zero. RestoreApp restores
// each of the app's volumes from the snapshot into a new folder beside the
// live one, then swaps: the live folder is renamed to
// <dir>.onemind-old-<stamp> and the restored one takes its name. Nothing is
// deleted. FinishRestore then either commits (deletes the old folders, after
// the gateway saw the app come back healthy) or rolls back (puts them back).
//
// A volume is matched to the snapshot by <namespace>_<claim>, not by the
// PersistentVolume name, so a restore still lands in the right place after
// the app was removed and reinstalled (a new PV name, the same claim).

// AppRestoreRequest is the backup.restore job with scope "app".
type AppRestoreRequest struct {
	TargetID   string `json:"target_id,omitempty"`
	SnapshotID string `json:"snapshot_id"`
	AppID      string `json:"app_id"`
	Stamp      string `json:"stamp"`
}

// RestoredItem is one volume or file of an app restore.
type RestoredItem struct {
	Namespace string `json:"namespace"`
	Claim     string `json:"claim"`
	Path      string `json:"path,omitempty"` // files: path inside the volume
	Restored  bool   `json:"restored"`
	Reason    string `json:"reason,omitempty"`
}

// AppRestoreResult says what was swapped. Stamp names the moved-aside copies.
type AppRestoreResult struct {
	AppID      string         `json:"app_id"`
	SnapshotID string         `json:"snapshot_id"`
	Stamp      string         `json:"stamp"`
	Items      []RestoredItem `json:"items"`
}

var stampRe = regexp.MustCompile(`^[0-9]{8}T[0-9]{6}Z$`)

const oldSuffix = ".onemind-old-"

type swap struct{ cur, old string }

// RestoreApp restores every volume and file of a managed app from one of its
// snapshots, keeping the live data beside it until FinishRestore.
func (a *Agent) RestoreApp(ctx context.Context, req AppRestoreRequest) (AppRestoreResult, error) {
	res := AppRestoreResult{AppID: req.AppID, Stamp: req.Stamp, Items: []RestoredItem{}}
	if !stampRe.MatchString(req.Stamp) {
		return res, fmt.Errorf("stamp %q must look like 20261112T101500Z", req.Stamp)
	}
	spec, ok := a.managedApp(req.AppID)
	if !ok {
		return res, fmt.Errorf("app %q is not backed up on this node", req.AppID)
	}
	if err := a.acquire(ctx, "restore:app:"+req.AppID); err != nil {
		return res, err
	}
	defer a.release()
	repo, snap, err := a.findSnapshot(ctx, req.TargetID, req.SnapshotID)
	if err != nil {
		return res, err
	}
	res.SnapshotID = snap.ID
	if snap.Tag("unit") != "app:"+req.AppID {
		return res, fmt.Errorf("snapshot %s is of %s, not app:%s", snap.ShortID, snap.Tag("unit"), req.AppID)
	}
	roots := a.conf().StorageRoots
	var done []swap
	undo := func() {
		for i := len(done) - 1; i >= 0; i-- {
			s := done[i]
			_ = os.RemoveAll(s.cur)
			if s.old != "" {
				_ = os.Rename(s.old, s.cur)
			}
		}
	}
	for _, v := range spec.Volumes {
		item := RestoredItem{Namespace: v.Namespace, Claim: v.Claim}
		src := snapshotPathFor(snap.Paths, v.suffix(), "")
		cur := volumeDir(roots, v)
		switch {
		case src == "":
			item.Reason = "the snapshot has no copy of this volume"
		default:
			if _, err := os.Lstat(cur); err != nil {
				undo()
				return res, fmt.Errorf("volume %s/%s: %w", v.Namespace, v.Claim, err)
			}
			s, err := a.swapDir(ctx, repo, snap.ID, src, cur, req.Stamp)
			if err != nil {
				undo()
				return res, fmt.Errorf("volume %s/%s: %w", v.Namespace, v.Claim, err)
			}
			done = append(done, s)
			item.Restored = true
		}
		res.Items = append(res.Items, item)
	}
	for _, f := range spec.Files {
		item := RestoredItem{Namespace: f.Namespace, Claim: f.Claim, Path: f.Path}
		src := snapshotPathFor(snap.Paths, f.suffix(), f.Path)
		if src == "" {
			item.Reason = "the snapshot has no copy of this file"
			res.Items = append(res.Items, item)
			continue
		}
		cur := volumeFilePath(roots, f)
		s, err := a.swapFile(ctx, repo, snap.ID, src, cur, req.Stamp)
		if err != nil {
			undo()
			return res, fmt.Errorf("file %s in %s/%s: %w", f.Path, f.Namespace, f.Claim, err)
		}
		done = append(done, s)
		item.Restored = true
		res.Items = append(res.Items, item)
	}
	a.Log.Info("app restore swapped in", "app", req.AppID, "snapshot", snap.ID, "stamp", req.Stamp, "items", len(done))
	return res, nil
}

// snapshotPathFor finds the snapshot source whose volume folder ends in
// suffix (and, for a file, whose path inside the volume is rel).
func snapshotPathFor(paths []string, suffix, rel string) string {
	for _, p := range paths {
		p = filepath.ToSlash(p)
		if rel == "" {
			if strings.HasSuffix(pathBase(p), suffix) {
				return p
			}
			continue
		}
		if strings.HasSuffix(p, "/"+rel) {
			dir := strings.TrimSuffix(p, "/"+rel)
			if strings.HasSuffix(pathBase(dir), suffix) {
				return p
			}
		}
	}
	return ""
}

func pathBase(p string) string { return p[strings.LastIndex(p, "/")+1:] }

// swapDir restores src from the snapshot into a new folder beside cur and
// swaps it in, keeping cur as cur.onemind-old-<stamp>. The new folder takes
// cur's mode and owner, so the app's user can still write it.
func (a *Agent) swapDir(ctx context.Context, repo Repo, id, src, cur, stamp string) (swap, error) {
	if err := safeParent(cur); err != nil {
		return swap{}, err
	}
	old := cur + oldSuffix + stamp
	if _, err := os.Lstat(old); err == nil {
		return swap{}, fmt.Errorf("%s already exists: finish the previous restore first", filepath.Base(old))
	}
	tmp, err := os.MkdirTemp(filepath.Dir(cur), ".onemind-restore-")
	if err != nil {
		return swap{}, err
	}
	if err := repo.Restore(ctx, id, src, tmp); err != nil {
		_ = os.RemoveAll(tmp)
		return swap{}, err
	}
	if err := copyOwnerAndMode(cur, tmp); err != nil {
		_ = os.RemoveAll(tmp)
		return swap{}, err
	}
	if err := os.Rename(cur, old); err != nil {
		_ = os.RemoveAll(tmp)
		return swap{}, err
	}
	if err := os.Rename(tmp, cur); err != nil {
		_ = os.Rename(old, cur)
		_ = os.RemoveAll(tmp)
		return swap{}, err
	}
	return swap{cur: cur, old: old}, nil
}

// swapFile restores one file next to cur and swaps it in. When cur did not
// exist, undo just removes the restored file (old stays "").
func (a *Agent) swapFile(ctx context.Context, repo Repo, id, src, cur, stamp string) (swap, error) {
	if err := safeParent(cur); err != nil {
		return swap{}, err
	}
	n, err := lookupNode(ctx, repo, id, src)
	if err != nil {
		return swap{}, err
	}
	if n.Type != "file" {
		return swap{}, fmt.Errorf("%s is a %s in the snapshot", src, n.Type)
	}
	s := swap{cur: cur}
	if _, err := os.Lstat(cur); err == nil {
		s.old = cur + oldSuffix + stamp
		if err := os.Rename(cur, s.old); err != nil {
			return swap{}, err
		}
	}
	if err := restoreFile(ctx, repo, id, src, cur, n); err != nil {
		if s.old != "" {
			_ = os.Rename(s.old, cur)
		}
		return swap{}, err
	}
	if s.old != "" {
		_ = copyOwnerAndMode(s.old, cur)
	}
	return s, nil
}

// FinishRestoreRequest is the backup.restore.finish job.
type FinishRestoreRequest struct {
	AppID  string `json:"app_id"`
	Stamp  string `json:"stamp"`
	Commit bool   `json:"commit"`
}

// FinishRestore commits an app restore (deletes the moved-aside data; the
// pre-restore snapshot still holds it) or rolls it back (puts it back).
func (a *Agent) FinishRestore(ctx context.Context, req FinishRestoreRequest) (int, error) {
	if !stampRe.MatchString(req.Stamp) {
		return 0, fmt.Errorf("stamp %q is malformed", req.Stamp)
	}
	spec, ok := a.managedApp(req.AppID)
	if !ok {
		return 0, fmt.Errorf("app %q is not backed up on this node", req.AppID)
	}
	if err := a.acquire(ctx, "restore-finish:"+req.AppID); err != nil {
		return 0, err
	}
	defer a.release()
	roots := a.conf().StorageRoots
	var curs []string
	for _, v := range spec.Volumes {
		curs = append(curs, volumeDir(roots, v))
	}
	for _, f := range spec.Files {
		curs = append(curs, volumeFilePath(roots, f))
	}
	n := 0
	var errs []error
	for _, cur := range curs {
		old := cur + oldSuffix + req.Stamp
		if _, err := os.Lstat(old); err != nil {
			continue
		}
		n++
		if req.Commit {
			errs = append(errs, os.RemoveAll(old))
			continue
		}
		if err := os.RemoveAll(cur); err != nil {
			errs = append(errs, err)
			continue
		}
		errs = append(errs, os.Rename(old, cur))
	}
	return n, errors.Join(errs...)
}
