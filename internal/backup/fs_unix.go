// SPDX-License-Identifier: Apache-2.0

//go:build unix

package backup

import (
	"os"
	"path/filepath"
	"syscall"
)

// freeBytes returns the space available to unprivileged writers at path.
func freeBytes(path string) (int64, error) {
	var s syscall.Statfs_t
	if err := syscall.Statfs(path, &s); err != nil {
		return 0, err
	}
	return int64(s.Bavail) * int64(s.Bsize), nil
}

// isMountPoint reports whether path is the root of a mounted filesystem:
// its device differs from its parent's.
func isMountPoint(path string) (bool, error) {
	fi, err := os.Lstat(path)
	if err != nil {
		return false, err
	}
	pi, err := os.Lstat(filepath.Dir(path))
	if err != nil {
		return false, err
	}
	return fi.Sys().(*syscall.Stat_t).Dev != pi.Sys().(*syscall.Stat_t).Dev, nil
}

// copyOwnerAndMode gives dst the permission bits and owner of src.
func copyOwnerAndMode(src, dst string) error {
	fi, err := os.Lstat(src)
	if err != nil {
		return err
	}
	if err := os.Chmod(dst, fi.Mode().Perm()); err != nil {
		return err
	}
	st := fi.Sys().(*syscall.Stat_t)
	if err := os.Lchown(dst, int(st.Uid), int(st.Gid)); err != nil && os.Geteuid() == 0 {
		return err // as root a failed chown is real; unprivileged tests cannot chown
	}
	return nil
}
