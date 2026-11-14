// SPDX-License-Identifier: Apache-2.0

//go:build !linux

package ops

import "net"

// peerCredSupported: without SO_PEERCRED the socket's mode is the gate (dev only).
const peerCredSupported = false

// peerCred is unavailable here; OneMind boxes are Linux.
func peerCred(*net.UnixConn) (uid, gid int, ok bool) { return 0, 0, false }
