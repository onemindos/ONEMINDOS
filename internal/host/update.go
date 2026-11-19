// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/update"
)

// UpdateEngine installs an approved OS version through internal/update: the
// same Run(ModeApply) as `onemind update apply` at the box, so the pre-update
// restic snapshot, RAUC's signature check, the install into the other A/B slot
// and the health-gated trial all stay in the path (D-007). It never runs
// `rauc install` itself. The engine's lock keeps it from racing the update
// service's own cycle.
type UpdateEngine struct {
	ConfigPath string
	Log        *slog.Logger
	// tests replace these
	newEngine func(*update.Config, *slog.Logger) *update.Engine
	run       func(context.Context, *update.Engine, update.Mode) (*update.Result, error)
}

func (u *UpdateEngine) config() (*update.Config, string) {
	c, err := update.LoadConfig(u.ConfigPath)
	if errors.Is(err, os.ErrNotExist) {
		return nil, "this box has no OS update settings (" + u.ConfigPath + "): it is not an A/B OneMind image"
	} else if err != nil {
		return nil, "the OS update settings are invalid: " + err.Error()
	}
	return c, ""
}

// Unavailable implements OSInstaller.
func (u *UpdateEngine) Unavailable() string {
	_, why := u.config()
	return why
}

// Install implements OSInstaller: check that version is the update on offer,
// then apply it with the installer pinned to that version.
func (u *UpdateEngine) Install(ctx context.Context, version string, goingDown func()) (string, bool, error) {
	c, why := u.config()
	if why != "" {
		return "", false, &Refusal{"unavailable", why}
	}
	newEngine, run := u.newEngine, u.run
	if newEngine == nil {
		newEngine = update.New
	}
	if run == nil {
		run = func(ctx context.Context, e *update.Engine, m update.Mode) (*update.Result, error) {
			return e.Run(ctx, m, false)
		}
	}
	e := newEngine(c, u.Log)
	res, err := run(ctx, e, update.ModeCheck)
	if errors.Is(err, update.ErrBusy) {
		return "", false, &Refusal{"engine_busy", "the update service is in the middle of a cycle; ask again in a minute"}
	} else if err != nil {
		return "", false, fmt.Errorf("update check: %w", err)
	}
	if res.Candidate == nil || res.Candidate.Meta.Version != version {
		offered := "none"
		if res.Candidate != nil {
			offered = res.Candidate.Meta.Version
		}
		return "", false, &Refusal{"version_not_offered", fmt.Sprintf("the channel offers %s, not the approved %s; nothing was installed", offered, version)}
	}
	e.Installer = pinnedInstaller{inner: e.Installer, cfg: c, want: version}
	e.Rebooter = announceRebooter{inner: e.Rebooter, before: goingDown}
	res, err = run(ctx, e, update.ModeApply)
	if errors.Is(err, update.ErrBusy) {
		return "", false, &Refusal{"engine_busy", "the update service started a cycle; ask again in a minute"}
	} else if err != nil {
		return "", false, err
	}
	if res.Decision != update.DecideInstall && !res.Rebooted {
		return "", false, &Refusal{"engine_declined", fmt.Sprintf("the update engine did not install: %s (%s)", res.Decision, res.Reason)}
	}
	if !res.Rebooted {
		return "installed " + version + "; the box has not rebooted yet: " + res.Status.LastResult, false, nil
	}
	return "", true, nil
}

// pinnedInstaller refuses to install anything but the approved version. The
// engine saves its target version before it installs, so a channel that moved
// on between the check and the apply cannot slip in another release.
type pinnedInstaller struct {
	inner update.Installer
	cfg   *update.Config
	want  string
}

func (p pinnedInstaller) Install(ctx context.Context, bundle string) error {
	st, err := update.LoadStatus(p.cfg)
	if err != nil {
		return err
	}
	if st.TargetVersion != p.want {
		return fmt.Errorf("the channel moved to %s; the owner approved %s, so nothing was installed", st.TargetVersion, p.want)
	}
	return p.inner.Install(ctx, bundle)
}

// announceRebooter journals going_down before the engine reboots.
type announceRebooter struct {
	inner  update.Rebooter
	before func()
}

func (a announceRebooter) Reboot(ctx context.Context) error {
	if a.before != nil {
		a.before()
	}
	return a.inner.Reboot(ctx)
}

// Systemd is the box's power control: `systemctl reboot` and `systemctl
// poweroff` (logind's normal path, so units stop cleanly and the journal is
// flushed).
type Systemd struct{ Binary string }

func (s Systemd) do(ctx context.Context, verb string) error {
	bin := s.Binary
	if bin == "" {
		bin = "systemctl"
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, bin, verb).CombinedOutput()
	if err != nil {
		return fmt.Errorf("systemctl %s: %w: %s", verb, err, strings.TrimSpace(string(out)))
	}
	return nil
}

// Reboot implements Power.
func (s Systemd) Reboot(ctx context.Context) error { return s.do(ctx, "reboot") }

// PowerOff implements Power.
func (s Systemd) PowerOff(ctx context.Context) error { return s.do(ctx, "poweroff") }

// BootID reads this boot's id, or "" off Linux.
func BootID() string {
	b, err := os.ReadFile("/proc/sys/kernel/random/boot_id")
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}
