// SPDX-License-Identifier: Apache-2.0

package update

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

// Installer installs a verified bundle into the inactive slot.
type Installer interface {
	Install(ctx context.Context, bundle string) error
}

// Snapshotter takes the pre-update backup of /data and returns its id.
type Snapshotter interface {
	Snapshot(ctx context.Context, from, to string) (string, error)
}

// Rebooter restarts the box into the newly installed slot.
type Rebooter interface {
	Reboot(ctx context.Context) error
}

// RAUC runs `rauc install`. RAUC itself re-verifies the bundle signature
// against /etc/rauc/keyring.pem and the compatible string, and its
// pre-install handler writes the gate's trial marker (os/rauc/handlers).
type RAUC struct{ Binary string }

// Install implements Installer.
func (r RAUC) Install(ctx context.Context, bundle string) error {
	out, err := exec.CommandContext(ctx, r.Binary, "install", bundle).CombinedOutput()
	if err != nil {
		return fmt.Errorf("rauc install: %w: %s", err, lastLine(out))
	}
	return nil
}

// Restic snapshots paths into the configured repository.
type Restic struct {
	Binary, Repository, PasswordFile string
	Paths, Excludes                  []string
}

// Snapshot implements Snapshotter.
func (r Restic) Snapshot(ctx context.Context, from, to string) (string, error) {
	args := []string{"backup", "--json", "--tag", "onemind-pre-update", "--tag", "from=" + from, "--tag", "to=" + to}
	for _, e := range r.Excludes {
		args = append(args, "--exclude", e)
	}
	args = append(args, r.Paths...)
	cmd := exec.CommandContext(ctx, r.Binary, args...)
	cmd.Env = append(os.Environ(), "RESTIC_REPOSITORY="+r.Repository)
	if r.PasswordFile != "" {
		cmd.Env = append(cmd.Env, "RESTIC_PASSWORD_FILE="+r.PasswordFile)
	}
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("restic backup: %w: %s", err, lastLine(stderr.Bytes()))
	}
	return parseResticSummary(out)
}

// parseResticSummary finds the snapshot id in `restic backup --json` output
// (one JSON object per line; the last has message_type "summary").
func parseResticSummary(out []byte) (string, error) {
	sc := bufio.NewScanner(bytes.NewReader(out))
	sc.Buffer(make([]byte, 64<<10), 1<<20)
	for sc.Scan() {
		var m struct {
			MessageType string `json:"message_type"`
			SnapshotID  string `json:"snapshot_id"`
		}
		if json.Unmarshal(sc.Bytes(), &m) == nil && m.MessageType == "summary" && m.SnapshotID != "" {
			return m.SnapshotID, nil
		}
	}
	return "", fmt.Errorf("restic backup: no summary with snapshot_id in output")
}

// Command reboots by running argv (default `systemctl reboot`).
type Command struct{ Argv []string }

// Reboot implements Rebooter.
func (c Command) Reboot(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, c.Argv[0], c.Argv[1:]...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("%s: %w: %s", strings.Join(c.Argv, " "), err, lastLine(out))
	}
	return nil
}

func lastLine(b []byte) string {
	s := strings.TrimSpace(string(b))
	if i := strings.LastIndexByte(s, '\n'); i >= 0 {
		s = s[i+1:]
	}
	if len(s) > 300 {
		s = s[:300]
	}
	return s
}
