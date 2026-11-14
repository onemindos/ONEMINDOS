// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"bytes"
	"context"
	"errors"
	"os"
	"os/exec"
	"strings"

	"github.com/onemindos/onemindos/internal/storage"
)

// Runner runs one command with optional stdin and returns stdout and stderr
// together. A non-zero exit is not an error; err means it could not run or
// ctx ended.
type Runner interface {
	Exec(ctx context.Context, stdin string, name string, args ...string) (out []byte, exit int, err error)
}

// ExecRunner runs real commands with LC_ALL=C (tool output is parsed).
type ExecRunner struct{}

// Exec implements Runner.
func (ExecRunner) Exec(ctx context.Context, stdin, name string, args ...string) ([]byte, int, error) {
	var buf bytes.Buffer
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout, cmd.Stderr = &buf, &buf
	cmd.Env = append(os.Environ(), "LC_ALL=C")
	if stdin != "" {
		cmd.Stdin = strings.NewReader(stdin)
	}
	err := cmd.Run()
	if ctx.Err() != nil {
		return buf.Bytes(), -1, ctx.Err()
	}
	var ee *exec.ExitError
	if errors.As(err, &ee) {
		return buf.Bytes(), ee.ExitCode(), nil
	}
	if err != nil {
		return nil, -1, err
	}
	return buf.Bytes(), 0, nil
}

// Run lets an ExecRunner serve storage.Collector (stdout only there).
func (r ExecRunner) Run(ctx context.Context, name string, args ...string) ([]byte, int, error) {
	return storage.ExecRunner{}.Run(ctx, name, args...)
}

// allowed are the only programs a plan step may start (defence in depth: the
// engine renders every plan itself).
var allowed = map[string]bool{
	"sgdisk": true, "udevadm": true, "cryptsetup": true, "btrfs": true, "wipefs": true, "mkdir": true,
	"rm": true, "mount": true, "umount": true, "install": true, "systemd-cryptenroll": true, "mkfs.btrfs": true,
}

func tail(b []byte, n int) string {
	s := strings.TrimSpace(string(b))
	if len(s) > n {
		s = "…" + s[len(s)-n:]
	}
	return s
}
