// SPDX-License-Identifier: Apache-2.0

//go:build unix

package update

import (
	"errors"
	"os"
	"path/filepath"
	"syscall"
)

func freeBytes(dir string) (uint64, error) {
	var s syscall.Statfs_t
	if err := syscall.Statfs(dir, &s); err != nil {
		return 0, err
	}
	return uint64(s.Bavail) * uint64(s.Bsize), nil //nolint:unconvert // field types differ per OS
}

// ErrBusy means another update run holds the lock.
var ErrBusy = errors.New("another update run is in progress")

// lock takes an exclusive, non-blocking lock on <state_dir>/lock so the
// daemon and `onemind update apply` never install at the same time.
// The kernel drops the lock if the process dies.
func lock(stateDir string) (func(), error) {
	if err := os.MkdirAll(stateDir, 0o755); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(filepath.Join(stateDir, "lock"), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		if errors.Is(err, syscall.EWOULDBLOCK) {
			return nil, ErrBusy
		}
		return nil, err
	}
	return func() { _ = syscall.Flock(int(f.Fd()), syscall.LOCK_UN); f.Close() }, nil
}
