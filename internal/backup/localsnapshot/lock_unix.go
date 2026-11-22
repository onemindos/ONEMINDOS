// SPDX-License-Identifier: Apache-2.0
//go:build unix

package localsnapshot

import (
	"fmt"
	"golang.org/x/sys/unix"
	"os"
	"syscall"
)

func owned(fi os.FileInfo) bool {
	uid, err := ownerOf(fi)
	return err == nil && trustedUID(uid)
}

func ownerOf(fi os.FileInfo) (uint32, error) {
	st, ok := fi.Sys().(*syscall.Stat_t)
	if !ok {
		return 0, fmt.Errorf("cannot read owner of %s", fi.Name())
	}
	return st.Uid, nil
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
