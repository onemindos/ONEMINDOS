// SPDX-License-Identifier: Apache-2.0
//go:build unix

package appmodule

import (
	"errors"
	"os"
	"os/exec"
	"syscall"
)

func setGroupCancel(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error {
		err := syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		if errors.Is(err, syscall.ESRCH) {
			return os.ErrProcessDone
		}
		return err
	}
}
