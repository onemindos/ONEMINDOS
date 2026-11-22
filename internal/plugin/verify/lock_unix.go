// SPDX-License-Identifier: Apache-2.0

//go:build unix

package verify

import (
	"fmt"
	"path/filepath"

	"golang.org/x/sys/unix"
)

func lockRevocations(dir string) (func(), error) {
	fd, err := unix.Open(filepath.Join(dir, "revocations.lock"), unix.O_CREAT|unix.O_RDWR|unix.O_NOFOLLOW|unix.O_NONBLOCK, 0600)
	if err != nil {
		return nil, err
	}
	var st unix.Stat_t
	if err = unix.Fstat(fd, &st); err != nil || st.Mode&unix.S_IFMT != unix.S_IFREG {
		unix.Close(fd)
		return nil, fmt.Errorf("invalid revocation lock file")
	}
	if err = unix.Flock(fd, unix.LOCK_EX|unix.LOCK_NB); err != nil {
		unix.Close(fd)
		return nil, fmt.Errorf("revocation check already running: %w", err)
	}
	return func() { _ = unix.Flock(fd, unix.LOCK_UN); _ = unix.Close(fd) }, nil
}
