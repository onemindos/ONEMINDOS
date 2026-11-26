// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path"
	"path/filepath"
)

// Restore into a new folder (gateway permissions design 25b: data access never
// needs a strong key). A copy of one path, or of an app's saved folders, is put
// into an EMPTY folder the gateway made in the person's Files Home. Nothing that
// exists is overwritten, no app is stopped, and the copy is the folder owner's:
// every entry gets the folder's uid and gid, owner read and write, and symlinks,
// devices, sockets and pipes are left out, so a snapshot cannot plant a link that
// the Files service would later follow.

// CopyRequest is a restore of scope "copy".
type CopyRequest struct {
	TargetID   string
	SnapshotID string
	Path       string // one file or folder inside the snapshot; empty: every saved folder of the snapshot
	Dest       string // the empty folder to fill; must be under Config.CopyRoot
}

// CopyResult says what landed in Dest.
type CopyResult struct {
	Dest       string `json:"dest"`
	SnapshotID string `json:"snapshot_id"`
	Folders    int    `json:"folders"`
	Files      int    `json:"files"`
	Skipped    int    `json:"skipped"` // symlinks and special files left out
}

// copyRoot is where a copy may land (the Files root on the image).
func (a *Agent) copyRoot() string {
	if a.Cfg.CopyRoot != "" {
		return a.Cfg.CopyRoot
	}
	return "/data/onemind/files"
}

// RestoreCopy restores into a new folder.
func (a *Agent) RestoreCopy(ctx context.Context, req CopyRequest) (CopyResult, error) {
	root := filepath.Clean(a.copyRoot())
	dest := filepath.Clean(req.Dest)
	if !filepath.IsAbs(req.Dest) || dest == root || !isUnder(filepath.ToSlash(dest), filepath.ToSlash(root)) {
		return CopyResult{}, badParams{fmt.Errorf("dest must be a folder under %s", root)}
	}
	if err := a.acquire(ctx, "restore"); err != nil {
		return CopyResult{}, err
	}
	defer a.release()
	repo, snap, err := a.findSnapshot(ctx, req.TargetID, req.SnapshotID)
	if err != nil {
		return CopyResult{}, err
	}
	var sources []string
	if req.Path != "" {
		p := cleanSnapPath(req.Path)
		in := false
		for _, sp := range snap.Paths {
			in = in || isUnder(p, cleanSnapPath(filepath.ToSlash(sp)))
		}
		if p == "/" || !in {
			return CopyResult{}, fmt.Errorf("%s is not in snapshot %s", p, snap.ShortID)
		}
		sources = []string{p}
	} else {
		for _, sp := range snap.Paths {
			sources = append(sources, cleanSnapPath(filepath.ToSlash(sp)))
		}
	}
	if len(sources) == 0 {
		return CopyResult{}, errors.New("the snapshot has no saved folders")
	}
	nodes := make([]Node, len(sources))
	var total, largest int64
	for i, src := range sources {
		n, err := lookupNode(ctx, repo, snap.ID, src)
		if err != nil {
			return CopyResult{}, err
		}
		size, err := nodeBytes(ctx, repo, snap.ID, n)
		if err != nil {
			return CopyResult{}, err
		}
		nodes[i], total, largest = n, total+size, max(largest, size)
	}
	if err := os.MkdirAll(a.Cfg.StateDir, 0o700); err != nil {
		return CopyResult{}, err
	}
	if msg := a.copySpaceCheck(dest, total, largest); msg != "" {
		return CopyResult{}, errors.New(msg)
	}
	dfd, err := openEmptyDir(dest)
	if err != nil {
		return CopyResult{}, err
	}
	defer closeDir(dfd)
	res := CopyResult{Dest: dest, SnapshotID: snap.ID}
	seen := map[string]int{}
	for i, src := range sources {
		n := nodes[i]
		if n.Type != "file" && n.Type != "dir" {
			res.Skipped++
			continue
		}
		name := path.Base(src)
		if seen[name]++; seen[name] > 1 { // two saved folders with the same last name
			name = fmt.Sprintf("%s-%d", name, seen[name])
		}
		st, err := os.MkdirTemp(a.Cfg.StateDir, "copy-stage-")
		if err != nil {
			return res, err
		}
		from := st
		if n.Type == "dir" {
			err = repo.Restore(ctx, snap.ID, src, st) // restic restores a folder's contents with <id>:<folder>
		} else {
			from = filepath.Join(st, "file")
			err = dumpTo(ctx, repo, snap.ID, src, from) // and one file with dump
		}
		if err == nil {
			err = copyOwnedAt(from, n.Type == "dir", dfd, name, &res)
		}
		os.RemoveAll(st)
		if err != nil {
			return res, err
		}
	}
	a.Log.Info("restore copy", "snapshot", snap.ID, "dest", dest, "files", res.Files, "skipped", res.Skipped)
	return res, nil
}

// nodeBytes is how much a copy of n writes: its size for a file, the sum of the
// files below it for a folder. Symlinks and special files are skipped, so 0.
func nodeBytes(ctx context.Context, repo Repo, id string, n Node) (int64, error) {
	switch n.Type {
	case "file":
		return n.Size, nil
	case "dir":
		below, err := repo.Ls(ctx, id, cleanSnapPath(n.Path), true)
		if err != nil {
			return 0, err
		}
		var sum int64
		for _, b := range below {
			if b.Type == "file" {
				sum += b.Size
			}
		}
		return sum, nil
	}
	return 0, nil
}

// copySpaceCheck refuses a copy before it starts when it cannot fit (review of
// #1193): the folder needs every byte plus 10 %, and the staging folder (where
// restic writes each saved folder before it is copied) needs the largest one
// plus 10 %. Staging and the Files root are usually the same /data disk, so the
// folder's disk is asked for both. Unknown free space never blocks a copy, as
// for a backup (spaceCheck).
func (a *Agent) copySpaceCheck(dest string, total, largest int64) string {
	pad := func(n int64) int64 { return n + n/10 }
	need := pad(total) + pad(largest)
	if free, err := a.FreeBytes(dest); err == nil && free < need {
		return fmt.Sprintf("not enough space for this copy: %d bytes free, %d bytes needed (the copy plus room to unpack it)", free, need)
	}
	if free, err := a.FreeBytes(a.Cfg.StateDir); err == nil && free < pad(largest) {
		return fmt.Sprintf("not enough space to unpack this copy: %d bytes free, %d bytes needed", free, pad(largest))
	}
	return ""
}

func dumpTo(ctx context.Context, repo Repo, id, p, file string) error {
	out, err := os.OpenFile(file, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	err = repo.Dump(ctx, id, p, out)
	if cerr := out.Close(); err == nil {
		err = cerr
	}
	return err
}
