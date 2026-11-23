// SPDX-License-Identifier: Apache-2.0

package watchdog

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
	"time"
)

// Hook runs an operator-configured program for each event: a siren relay, a speaker script. The
// program is started directly (no shell), with a fixed environment, and killed after Timeout.
// The configuration is root-owned; nothing from a network packet reaches the command line.
type Hook struct {
	Command []string      // program and fixed arguments
	Timeout time.Duration // default 10 s
}

func (Hook) Name() string { return "hook" }

func (h Hook) Alert(ctx context.Context, e Event) error {
	if len(h.Command) == 0 {
		return errors.New("no hook command")
	}
	to := h.Timeout
	if to <= 0 {
		to = 10 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, to)
	defer cancel()
	cmd := exec.CommandContext(ctx, h.Command[0], h.Command[1:]...)
	cmd.Env = []string{
		"PATH=/usr/sbin:/usr/bin:/sbin:/bin",
		"ONEMIND_WATCHDOG_EVENT=" + e.Kind,
		fmt.Sprintf("ONEMIND_WATCHDOG_SILENT_S=%d", int64(e.Silent/time.Second)),
	}
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("hook failed: %w", err)
	}
	return nil
}
