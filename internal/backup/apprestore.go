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
	"time"
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
	// StrictFiles makes a snapshot that lacks any file the app declares (its
	// database dump) a refusal before anything is swapped, instead of
	// restoring the volumes without the data that belongs with them.
	StrictFiles bool `json:"strict_files,omitempty"`
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
	if req.StrictFiles {
		var missing []string
		for _, f := range spec.Files {
			if snapshotPathFor(snap.Paths, f.suffix(), f.Path) == "" {
				missing = append(missing, f.Path)
			}
		}
		if len(missing) > 0 {
			return res, fmt.Errorf("snapshot %s has no copy of %s (its database dump), so restoring would bring back the files without the data that belongs with them; nothing was changed", snap.ShortID, strings.Join(missing, ", "))
		}
	}
	var done []swap
	restoredDirs := map[string]string{} // volume suffix -> its restored folder
	undo := func() {
		for i := len(done) - 1; i >= 0; i-- {
			_ = rollbackSwap(done[i])
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
			if err := safeParent(cur); err != nil {
				undo()
				return res, fmt.Errorf("volume %s/%s: %w", v.Namespace, v.Claim, err)
			}
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
			restoredDirs[v.suffix()] = cur
			item.Restored = true
		}
		res.Items = append(res.Items, item)
	}
	for _, q := range spec.VolumeSQLite {
		dir, ok := restoredDirs[q.suffix()]
		if !ok {
			continue
		}
		put, err := a.putOnlineCopy(ctx, repo, snap, req.AppID, q, dir)
		if err != nil {
			undo()
			return res, fmt.Errorf("sqlite %s in %s/%s: %w", q.Path, q.Namespace, q.Claim, err)
		}
		if put {
			res.Items = append(res.Items, RestoredItem{Namespace: q.Namespace, Claim: q.Claim, Path: q.Path, Restored: true})
		}
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

// dirMeta is the owner, mode and mtime of an existing entry, read through a
// directory handle (metaAt) so it can be given to its replacement.
type dirMeta struct {
	mode     os.FileMode
	mtime    time.Time
	uid, gid int
	isDir    bool
}

// swapDir restores src from the snapshot into a new folder beside cur and
// swaps it in, keeping cur as cur.onemind-old-<stamp>. The new folder takes
// cur's mode and owner, so the app's user can still write it.
//
// The app owns cur's parent and may swap any folder in it for a symlink while
// root works, so the restore lands in a root-only staging folder first and is
// then copied and swapped in through a directory handle opened without
// following symlinks (safefs_unix.go), as restoreDir does for a rewind.
func (a *Agent) swapDir(ctx context.Context, repo Repo, id, src, cur, stamp string) (swap, error) {
	if err := os.MkdirAll(a.Cfg.StateDir, 0o700); err != nil {
		return swap{}, err
	}
	st, err := os.MkdirTemp(a.Cfg.StateDir, "restore-stage-")
	if err != nil {
		return swap{}, err
	}
	defer os.RemoveAll(st)
	if err := repo.Restore(ctx, id, src, st); err != nil {
		return swap{}, err
	}
	pfd, err := openDirNoFollow(filepath.Dir(cur), false)
	if err != nil {
		return swap{}, err
	}
	defer closeDir(pfd)
	if testHookAfterOpen != nil {
		testHookAfterOpen()
	}
	name := filepath.Base(cur)
	old := name + oldSuffix + stamp
	if exists, err := checkDestAt(pfd, old, false); err != nil || exists {
		if err == nil {
			err = fmt.Errorf("%s already exists: finish the previous restore first", old)
		}
		return swap{}, err
	}
	meta, err := metaAt(pfd, name)
	if err != nil {
		return swap{}, err
	}
	if !meta.isDir {
		return swap{}, fmt.Errorf("%s is not a folder; refusing to restore over it", cur)
	}
	tmp := tmpName(".onemind-restore-")
	tfd, err := mkdirAt(pfd, tmp)
	if err != nil {
		return swap{}, err
	}
	defer func() { _ = removeAllAt(pfd, tmp) }() // a no-op once renamed into place
	err = copyTreeAt(st, tfd)
	if err == nil {
		err = applyMetaFd(tfd, meta)
	}
	closeDir(tfd)
	if err != nil {
		return swap{}, err
	}
	if err := renameAt(pfd, name, old); err != nil {
		return swap{}, err
	}
	if err := renameAt(pfd, tmp, name); err != nil {
		_ = renameAt(pfd, old, name)
		return swap{}, err
	}
	return swap{cur: cur, old: filepath.Join(filepath.Dir(cur), old)}, nil
}

// putOnlineCopy puts back, inside a just-restored volume folder, the online
// copy the backup made of a SQLite database (SQLiteHook, in the unit's
// staging folder). That copy is consistent; the volume's own copy of a live
// database may be torn, or excluded. The volume's -wal, -shm and -journal
// files belong to the volume's copy and are removed with it. A snapshot
// without an online copy (taken before the app declared one) keeps the
// volume's copy and reports false.
func (a *Agent) putOnlineCopy(ctx context.Context, repo Repo, snap Snapshot, appID string, f VolumeFile, volDir string) (bool, error) {
	src := ""
	for _, p := range snap.Paths {
		p = filepath.ToSlash(p)
		if pathBase(p) == stagingName("app:"+appID) && pathBase(pathDir(p)) == "staging" {
			src = p + "/" + volumeSQLiteName(f)
		}
	}
	if src == "" {
		return false, nil
	}
	n, err := lookupNode(ctx, repo, snap.ID, src)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	} else if err != nil {
		return false, err
	}
	if n.Type != "file" {
		return false, fmt.Errorf("%s is a %s in the snapshot", src, n.Type)
	}
	dest := filepath.Join(volDir, filepath.FromSlash(f.Path))
	// The restored folder holds what the app wrote: never follow a symlink in it.
	if err := safeParent(dest); err != nil {
		return false, err
	}
	like, strip := dest, os.FileMode(0)
	if fi, err := os.Lstat(dest); err != nil || !fi.Mode().IsRegular() {
		like, strip = volDir, 0o111 // no file to copy from: the folder's owner, no execute bits
	}
	tmp := dest + ".onemind-online"
	if err := restoreFile(ctx, repo, snap.ID, src, tmp, n); err != nil {
		return false, err
	}
	if err := copyOwnerAndMode(like, tmp); err != nil {
		_ = os.Remove(tmp)
		return false, err
	}
	if strip != 0 {
		if fi, err := os.Lstat(tmp); err == nil {
			_ = os.Chmod(tmp, fi.Mode().Perm()&^strip)
		}
	}
	if err := os.Rename(tmp, dest); err != nil {
		_ = os.Remove(tmp)
		return false, err
	}
	for _, sfx := range []string{"-wal", "-shm", "-journal"} {
		if err := os.Remove(dest + sfx); err != nil && !errors.Is(err, os.ErrNotExist) {
			return true, err
		}
	}
	return true, nil
}

// swapFile restores one file next to cur and swaps it in. When cur did not
// exist, undo just removes the restored file (old stays ""). Every step is
// relative to the parent folder, opened without following symlinks.
func (a *Agent) swapFile(ctx context.Context, repo Repo, id, src, cur, stamp string) (swap, error) {
	n, err := lookupNode(ctx, repo, id, src)
	if err != nil {
		return swap{}, err
	}
	if n.Type != "file" {
		return swap{}, fmt.Errorf("%s is a %s in the snapshot", src, n.Type)
	}
	pfd, err := openDirNoFollow(filepath.Dir(cur), true)
	if err != nil {
		return swap{}, err
	}
	defer closeDir(pfd)
	if testHookAfterOpen != nil {
		testHookAfterOpen()
	}
	name := filepath.Base(cur)
	exists, err := checkDestAt(pfd, name, true)
	if err != nil {
		return swap{}, err
	}
	s := swap{cur: cur}
	mode, mtime := n.Mode, n.Mtime
	var meta dirMeta
	oldName := ""
	if exists {
		if meta, err = metaAt(pfd, name); err != nil {
			return swap{}, err
		}
		oldName = name + oldSuffix + stamp
		if err := renameAt(pfd, name, oldName); err != nil {
			return swap{}, err
		}
		s.old = filepath.Join(filepath.Dir(cur), oldName)
		mode = meta.mode
	}
	err = writeFileAt(pfd, name, mode, mtime, func(f *os.File) error {
		if err := repo.Dump(ctx, id, src, f); err != nil {
			return err
		}
		if exists {
			_ = applyMetaFd(int(f.Fd()), meta) // best effort, as before: keep the old owner
		}
		return nil
	})
	if err != nil {
		if oldName != "" {
			_ = renameAt(pfd, oldName, name)
		}
		return swap{}, err
	}
	return s, nil
}

// rollbackSwap puts s.old back over s.cur, and removeOld deletes it; both go
// through the parent folder opened without following symlinks.
func rollbackSwap(s swap) error {
	pfd, err := openDirNoFollow(filepath.Dir(s.cur), false)
	if err != nil {
		return err
	}
	defer closeDir(pfd)
	name := filepath.Base(s.cur)
	if err := removeAllAt(pfd, name); err != nil {
		return err
	}
	if s.old == "" {
		return nil
	}
	return renameAt(pfd, filepath.Base(s.old), name)
}

func removeOld(old string) error {
	pfd, err := openDirNoFollow(filepath.Dir(old), false)
	if err != nil {
		return err
	}
	defer closeDir(pfd)
	return removeAllAt(pfd, filepath.Base(old))
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
			errs = append(errs, removeOld(old))
			continue
		}
		errs = append(errs, rollbackSwap(swap{cur: cur, old: old}))
	}
	return n, errors.Join(errs...)
}
