// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"os"

	"golang.org/x/sys/windows"
)

func lockConfigFile(path string) (func(), error) {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	var offset windows.Overlapped
	if err := windows.LockFileEx(windows.Handle(file.Fd()), windows.LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, &offset); err != nil {
		file.Close()
		return nil, err
	}
	return func() { file.Close() }, nil
}
