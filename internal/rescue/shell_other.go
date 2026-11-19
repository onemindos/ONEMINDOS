// SPDX-License-Identifier: Apache-2.0

//go:build !linux

package rescue

import (
	"fmt"
	"os"
)

// RunShellHelper is only implemented on Linux, where the rescue terminal runs.
func RunShellHelper([]string) int {
	fmt.Fprintln(os.Stderr, "onemindd "+ShellHelperCommand+": the rescue terminal needs Linux")
	return 1
}
