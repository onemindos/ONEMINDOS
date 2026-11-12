// SPDX-License-Identifier: Apache-2.0

// Package storage is the read-only first slice of OneMind storage safety
// (docs/umbrel2/storage.md, epics STOR-3 and the plan half of STOR-4).
//
// It answers four questions on a box, by running standard Linux tools as
// separate processes (no linking, so their GPL licences stay theirs):
//
//   - Which disks are attached, and which are safe to use?   (lsblk --json)
//   - Is each disk healthy?                                   (smartctl --json)
//   - Is the data mirror protected, degraded or unprotected?  (btrfs)
//   - What exactly would it take to protect the data?         (Plan*, dry run)
//
// Nothing here changes a disk. Plans list the exact commands and the safety
// checks they passed; running them is a later, owner-approved action
// (storage.protect and friends, STOR-4/STOR-5).
package storage

import (
	"bytes"
	"context"
	"errors"
	"os/exec"
)

// Runner runs a command and returns its standard output and exit code.
// A non-zero exit is not an error: smartctl, for one, reports findings in its
// exit-status bits. err is set only when the command could not run at all.
type Runner interface {
	Run(ctx context.Context, name string, args ...string) (stdout []byte, exit int, err error)
}

// ExecRunner runs real commands.
type ExecRunner struct{}

// Run implements Runner.
func (ExecRunner) Run(ctx context.Context, name string, args ...string) ([]byte, int, error) {
	var out bytes.Buffer
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout = &out
	err := cmd.Run()
	var ee *exec.ExitError
	if errors.As(err, &ee) {
		return out.Bytes(), ee.ExitCode(), nil
	}
	if err != nil {
		return nil, -1, err
	}
	return out.Bytes(), 0, nil
}

// Collector gathers storage facts through a Runner.
type Collector struct {
	Run Runner
}

// New returns a Collector that runs the real tools.
func New() *Collector { return &Collector{Run: ExecRunner{}} }
