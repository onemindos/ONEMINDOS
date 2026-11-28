// SPDX-License-Identifier: Apache-2.0

//go:build unix

package backup

import (
	"context"
	"errors"
	"os"
	"sort"
	"strings"

	"golang.org/x/sys/unix"
)

type nasCopyStore struct{ root *os.File }

func openNASCopyStore(mount, box string, write bool) (copyStore, error) {
	fd, err := openDirNoFollow(mount, false)
	if err != nil {
		return nil, err
	}
	for _, name := range []string{"boxes", box, "copies"} {
		next, err := openNASCopyDir(fd, name, write)
		closeDir(fd)
		if err != nil {
			return nil, err
		}
		fd = next
	}
	return nasCopyStore{os.NewFile(uintptr(fd), "NAS copies")}, nil
}

func openNASCopyDir(parent int, name string, write bool) (int, error) {
	fd, err := openNASDir(parent, name, write)
	if err != nil {
		return -1, err
	}
	if write {
		// Sync existing entries too, in case the preceding publication failed to sync one.
		if err := unix.Fsync(parent); err != nil {
			closeDir(fd)
			return -1, err
		}
	}
	return fd, nil
}

func (s nasCopyStore) close() { _ = s.root.Close() }

func (s nasCopyStore) objectDir(key string, write bool) (int, string, error) {
	id, leaf, _ := strings.Cut(key, "/")
	if !copyID(id) || (leaf != "box.omb" && leaf != "complete.json") {
		return -1, "", errors.New("invalid copy object name")
	}
	fd, err := openNASCopyDir(int(s.root.Fd()), id, write)
	return fd, leaf, err
}

func (s nasCopyStore) put(_ context.Context, key string, data []byte) error {
	fd, leaf, err := s.objectDir(key, true)
	if err != nil {
		return err
	}
	defer closeDir(fd)
	tmp := tmpName(".onemind-copy-")
	raw, err := unix.Openat(fd, tmp, unix.O_WRONLY|unix.O_CREAT|unix.O_EXCL|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0o600)
	if err != nil {
		return err
	}
	defer unix.Unlinkat(fd, tmp, 0)
	f := os.NewFile(uintptr(raw), tmp)
	_, err = f.Write(data)
	if err = errors.Join(err, f.Sync(), f.Close()); err != nil {
		return err
	}
	linkErr := unix.Linkat(fd, tmp, fd, leaf, 0)
	if linkErr != nil && !errors.Is(linkErr, os.ErrExist) {
		return linkErr
	}
	if err := unix.Fsync(fd); err != nil {
		return err
	}
	return linkErr
}

func (s nasCopyStore) get(_ context.Context, key string, max int64) ([]byte, error) {
	fd, leaf, err := s.objectDir(key, false)
	if err != nil {
		return nil, err
	}
	defer closeDir(fd)
	f, err := openNASFile(fd, leaf)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return readCopyObject(f, max)
}

func (s nasCopyStore) records(_ context.Context) ([]string, error) {
	fd, err := unix.Openat(int(s.root.Fd()), ".", dirFlags, 0)
	if err != nil {
		return nil, err
	}
	dir := os.NewFile(uintptr(fd), "NAS copies listing")
	defer dir.Close()
	names, err := dir.Readdirnames(-1)
	if err != nil {
		return nil, err
	}
	var ids []string
	for _, id := range names {
		if copyID(id) && hasCopyRecord(fd, id) {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	return ids, nil
}

func hasCopyRecord(root int, id string) bool {
	fd, err := openNASDir(root, id, false)
	if errors.Is(err, unix.ENOTDIR) || errors.Is(err, unix.ELOOP) {
		return false
	}
	var st unix.Stat_t
	if err == nil {
		defer closeDir(fd)
		err = unix.Fstatat(fd, "complete.json", &st, unix.AT_SYMLINK_NOFOLLOW)
	}
	if err != nil {
		// The record read can reject an inaccessible candidate without hiding the others.
		return !errors.Is(err, os.ErrNotExist)
	}
	return st.Mode&unix.S_IFMT == unix.S_IFREG
}
