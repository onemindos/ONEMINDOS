// SPDX-License-Identifier: Apache-2.0

package appmodule

import (
	"os/exec"
	"strconv"
)

// make and npm both start child processes. Stop their descendants as well as the parent.
func setGroupCancel(cmd *exec.Cmd) {
	cmd.Cancel = func() error {
		return exec.Command("taskkill", "/F", "/T", "/PID", strconv.Itoa(cmd.Process.Pid)).Run()
	}
}
