// SPDX-License-Identifier: Apache-2.0

//go:build linux

package ops

import (
	"net"
	"syscall"
)

// peerCred returns the connecting process's uid and gid (SO_PEERCRED).
func peerCred(c *net.UnixConn) (uid, gid int, ok bool) {
	raw, err := c.SyscallConn()
	if err != nil {
		return 0, 0, false
	}
	var cred *syscall.Ucred
	var cerr error
	if err := raw.Control(func(fd uintptr) {
		cred, cerr = syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED)
	}); err != nil || cerr != nil {
		return 0, 0, false
	}
	return int(cred.Uid), int(cred.Gid), true
}
