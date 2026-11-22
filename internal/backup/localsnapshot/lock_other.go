// SPDX-License-Identifier: Apache-2.0
//go:build !unix

package localsnapshot

import (
	"fmt"
	"os"
)

func owned(os.FileInfo) bool { return false }
func ownerOf(os.FileInfo) (uint32, error) {
	return 0, fmt.Errorf("local snapshots require Unix")
}
func lock(string) (func(), error) { return nil, fmt.Errorf("local snapshots require Unix") }
