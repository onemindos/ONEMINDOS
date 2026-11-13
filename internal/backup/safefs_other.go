// SPDX-License-Identifier: Apache-2.0

//go:build !unix

package backup

import (
	"os"
	"time"
)

// Restores write through directory handles that cannot follow symlinks, which
// needs a unix kernel (safefs_unix.go). Elsewhere they fail closed.

var testHookAfterOpen func()

func safeParent(string) error { return errUnsupported }

func openDirNoFollow(string, bool) (int, error) { return -1, errUnsupported }
func closeDir(int)                              {}
func checkDestAt(int, string, bool) (bool, error) {
	return false, errUnsupported
}
func writeFileAt(int, string, os.FileMode, time.Time, func(*os.File) error) error {
	return errUnsupported
}
func removeAllAt(int, string) error                             { return errUnsupported }
func copyTreeAt(string, int) error                              { return errUnsupported }
func tmpName(prefix string) string                              { return prefix }
func renameAt(int, string, string) error                        { return errUnsupported }
func mkdirAt(int, string) (int, error)                          { return -1, errUnsupported }
func setDirMeta(int, int, string, os.FileMode, time.Time) error { return errUnsupported }
