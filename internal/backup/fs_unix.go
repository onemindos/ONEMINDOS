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
