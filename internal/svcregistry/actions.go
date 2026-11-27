// SPDX-License-Identifier: Apache-2.0

package svcregistry

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// Service logs and restart (#636). Both act only on units the image's registry lists. A restart is the
// host half of an owner-approved service.restart action: the gateway sends the approved action's id and
// the unit, internal/host journals it, then calls Restart here. Logs are read with journalctl; the
// gateway redacts every line (core/onemind_core/monitoring/redact.py) before anyone sees it.

// ErrUnknownUnit: the registry does not list the unit (or the image has no valid registry).
var ErrUnknownUnit = errors.New("the services registry on this image does not list that unit")

// ErrNotRestartable: the registry marks the unit not restartable, or it is a unit that never gets a
// restart (NeverRestart), or a template.
var ErrNotRestartable = errors.New("that unit is not restartable from OneMind")

// neverRestart are unit name prefixes that never get a restart, whatever the registry says: the rescue
// and recovery consoles, first boot, the host action service itself, and the units that lay out,
// encrypt, grow, check or wipe the data disk. A wrong registry edit cannot give them a button.
var neverRestart = []string{
	"onemind-rescue", "onemind-recovery", "onemind-firstboot", "onemind-host.", "onemind-data-",
	"onemind-factory-reset", "onemind-jetson-data", "onemind-rpi5-grow",
}

// NeverRestart reports whether unit is one of the rescue, first-boot, host or data-layout units.
func NeverRestart(unit string) bool {
	for _, p := range neverRestart {
		if strings.HasPrefix(unit, p) {
			return true
		}
	}
	return false
}

// MaxLogLines caps one logs request; FollowMax caps one follow stream.
const (
	MaxLogLines = 2000
	FollowMax   = 15 * time.Minute
)

func (r *Reader) path() string {
	if r.Path == "" {
		return DefaultPath
	}
	return r.Path
}

// Lookup returns the registry entry for unit.
func (r *Reader) Lookup(unit string) (Entry, error) {
	if !unitRE.MatchString(unit) {
		return Entry{}, ErrUnknownUnit
	}
	reg, err := Load(r.path())
	if err != nil {
		return Entry{}, ErrUnknownUnit // missing or invalid registry: nothing is vouched for
	}
	for _, e := range reg.Services {
		if e.Unit == unit {
			return e, nil
		}
	}
	return Entry{}, ErrUnknownUnit
}

// CheckRestart says whether unit may be restarted now: listed, restartable, not a template, not on the
// never list. It reads the registry again each time (only an OS update changes it).
func (r *Reader) CheckRestart(unit string) error {
	e, err := r.Lookup(unit)
	if err != nil {
		return err
	}
	if !e.Restartable || NeverRestart(unit) || strings.Contains(unit, "@.") {
		return ErrNotRestartable
	}
	return nil
}

// Restart restarts unit after CheckRestart passes.
func (r *Reader) Restart(ctx context.Context, unit string) error {
	if err := r.CheckRestart(unit); err != nil {
		return err
	}
	restart := r.Restarter
	if restart == nil {
		restart = SystemctlRestart
	}
	return restart(ctx, unit)
}

// SystemctlRestart runs `systemctl restart -- unit` and waits for it, at most two minutes.
func SystemctlRestart(ctx context.Context, unit string) error {
	if !unitRE.MatchString(unit) {
		return ErrUnknownUnit
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()
	out, err := exec.CommandContext(ctx, "systemctl", "restart", "--no-ask-password", "--", unit).CombinedOutput()
	if err != nil {
		msg := strings.TrimSpace(string(out))
		if len(msg) > 200 {
			msg = msg[:200]
		}
		return fmt.Errorf("systemctl restart %s: %v %s", unit, err, msg)
	}
	return nil
}

// Logs writes the last lines of unit's journal to w and, with follow, new lines as they come, for at
// most FollowMax or until ctx ends. ErrUnknownUnit is returned before anything is written.
func (r *Reader) Logs(ctx context.Context, unit string, lines int, follow bool, w io.Writer) error {
	if _, err := r.Lookup(unit); err != nil {
		return err
	}
	if lines < 1 || lines > MaxLogLines {
		return fmt.Errorf("lines must be 1-%d", MaxLogLines)
	}
	args := []string{"--no-pager", "--quiet", "--output=short-iso", "--lines=" + strconv.Itoa(lines), "--unit=" + unit}
	if follow {
		args = append(args, "--follow")
	}
	journal := r.Journal
	if journal == nil {
		journal = Journalctl
	}
	limit := 30 * time.Second
	if follow {
		limit = FollowMax
	}
	ctx, cancel := context.WithTimeout(ctx, limit)
	defer cancel()
	return journal(ctx, args, w)
}

// Journalctl runs journalctl with args, its output streamed to w. Ending ctx stops it, which is how a
// follow ends; that is not an error.
func Journalctl(ctx context.Context, args []string, w io.Writer) error {
	cmd := exec.CommandContext(ctx, "journalctl", args...)
	cmd.Stdout = w
	err := cmd.Run()
	if ctx.Err() != nil {
		return nil
	}
	return err
}
