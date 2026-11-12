// SPDX-License-Identifier: Apache-2.0

//go:build !linux

package ops

import "net"

// peerCred is unavailable here; OneMind boxes are Linux.
func peerCred(*net.UnixConn) (uid, gid int, ok bool) { return 0, 0, false }
