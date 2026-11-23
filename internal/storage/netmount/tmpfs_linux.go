// SPDX-License-Identifier: Apache-2.0

package netmount

import "syscall"

const tmpfsMagic = 0x01021994

// onTmpfs reports whether dir is on tmpfs (memory), so a credentials file
// written there never reaches a disk.
func onTmpfs(dir string) (bool, error) {
	var st syscall.Statfs_t
	if err := syscall.Statfs(dir, &st); err != nil {
		return false, err
	}
	return int64(st.Type) == tmpfsMagic, nil
}
