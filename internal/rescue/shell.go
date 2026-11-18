// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"fmt"
	"path/filepath"
)

// ShellHelperCommand is the hidden `onemindd rescue-shell -- <shell>` mode. The terminal never starts the shell
// directly: it starts this helper on the pty, the helper drops every capability, then execs the shell.
//
// Why a helper: the rescue unit keeps CAP_DAC_READ_SEARCH (CORE-UPDATE-9: root must read the onemind-owned
// 0600 CA key and tokens file). A root process that execs a program gets its bounding set as permitted caps,
// so a shell started directly would inherit DAC_READ_SEARCH and could read every file on the box. The helper
// clears its permitted, effective, inheritable and ambient sets and keeps no_new_privs on; with no_new_privs
// the kernel never grants a program more than its parent permitted, so the shell starts with none.
// Go cannot run code between fork and exec, hence a re-exec of onemindd itself.
const ShellHelperCommand = "rescue-shell"

// shellArgv is the command the pty runs for a shell: onemindd's helper mode, then the shell, absolute only.
func shellArgv(self, shell string) ([]string, error) {
	if !filepath.IsAbs(self) || !filepath.IsAbs(shell) {
		return nil, fmt.Errorf("rescue shell: helper %q and shell %q must be absolute paths", self, shell)
	}
	return []string{self, ShellHelperCommand, "--", shell}, nil
}

// helperShell reads the helper's own arguments (what follows ShellHelperCommand): exactly "--" and an
// absolute shell path.
func helperShell(args []string) (string, error) {
	if len(args) != 2 || args[0] != "--" || !filepath.IsAbs(args[1]) {
		return "", fmt.Errorf("usage: onemindd %s -- /absolute/shell", ShellHelperCommand)
	}
	return args[1], nil
}
