// SPDX-License-Identifier: Apache-2.0

//go:build linux

package rescue

import (
	"errors"
	"fmt"
	"os"
	"runtime"

	"golang.org/x/sys/unix"
)

// RunShellHelper is `onemindd rescue-shell -- <shell>` (see ShellHelperCommand). It fails closed: if any
// capability is left after the drop, no shell starts.
func RunShellHelper(args []string) int {
	shell, err := helperShell(args)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	// Capabilities and no_new_privs belong to one thread, and execve uses the calling thread's: drop and exec
	// on the same OS thread. Never unlocked; the exec replaces the process.
	runtime.LockOSThread()
	if err := dropAllCaps(); err != nil {
		fmt.Fprintln(os.Stderr, "rescue shell not started:", err)
		return 1
	}
	err = unix.Exec(shell, []string{shell}, os.Environ())
	fmt.Fprintln(os.Stderr, "rescue shell not started:", err)
	return 1
}

// dropAllCaps empties the calling thread's ambient, inheritable, permitted and effective capability sets and
// sets no_new_privs, then reads the sets back. The caller must hold its OS thread.
func dropAllCaps() error {
	if err := unix.Prctl(unix.PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0); err != nil {
		return fmt.Errorf("no_new_privs: %w", err)
	}
	// EINVAL: a kernel without ambient capabilities (< 4.3), so there is nothing to clear.
	if err := unix.Prctl(unix.PR_CAP_AMBIENT, unix.PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0); err != nil &&
		!errors.Is(err, unix.EINVAL) {
		return fmt.Errorf("clear ambient capabilities: %w", err)
	}
	hdr := unix.CapUserHeader{Version: unix.LINUX_CAPABILITY_VERSION_3}
	var none [2]unix.CapUserData // version 3 takes two 32-bit words per set
	if err := unix.Capset(&hdr, &none[0]); err != nil {
		return fmt.Errorf("capset: %w", err)
	}
	var got [2]unix.CapUserData
	if err := unix.Capget(&hdr, &got[0]); err != nil {
		return fmt.Errorf("capget: %w", err)
	}
	if got != none {
		return fmt.Errorf("capabilities still held after the drop: %+v", got)
	}
	if v, err := unix.PrctlRetInt(unix.PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0); err != nil || v != 1 {
		return fmt.Errorf("no_new_privs not set (%d, %v)", v, err)
	}
	return nil
}
