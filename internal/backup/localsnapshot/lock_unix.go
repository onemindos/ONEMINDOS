// SPDX-License-Identifier: Apache-2.0
//go:build unix

package localsnapshot

import (
	"golang.org/x/sys/unix"
	"os"
	"syscall"
)

func owned(fi os.FileInfo) bool {
	uid := fi.Sys().(*syscall.Stat_t).Uid
	return uid == 0 || uid == uint32(os.Geteuid())
}

func lock(path string) (func(), error) {
	fd, err := unix.Open(path, unix.O_CREAT|unix.O_RDWR|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0600)
	if err != nil {
		return nil, err
	}
	if err = unix.Flock(fd, unix.LOCK_EX|unix.LOCK_NB); err != nil {
		unix.Close(fd)
		return nil, err
	}
	return func() { unix.Close(fd) }, nil
}
