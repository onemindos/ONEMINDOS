// SPDX-License-Identifier: Apache-2.0

//go:build unix

package imagegc

import "syscall"

// DiskUsedPct returns how full the filesystem holding path is, the way df
// counts it (blocks reserved for root count as unavailable).
func DiskUsedPct(path string) (float64, bool) {
	var st syscall.Statfs_t
	if err := syscall.Statfs(path, &st); err != nil {
		return 0, false
	}
	used := st.Blocks - st.Bfree
	avail := used + st.Bavail
	if avail == 0 {
		return 0, false
	}
	return round1(float64(used) / float64(avail) * 100), true
}
