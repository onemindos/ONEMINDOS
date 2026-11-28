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

	"github.com/onemindos/onemindos/internal/heartbeat"
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

// UpdateBusy implements OSInstaller.
func (u *UpdateEngine) UpdateBusy() string {
	c, why := u.config()
	if why != "" {
		return "" // no A/B updates on this box: nothing to cut short
	}
	st, err := update.LoadStatus(c)
	if err != nil {
		return "the OS update status cannot be read: " + err.Error()
	}
	if busy(st.State) {
		return "an OS update is " + st.State + " (" + st.TargetVersion + "); wait for the health gate's verdict"
	}
	return ""
}

func busy(state string) bool {
	switch state {
	case heartbeat.UpdateDownloading, heartbeat.UpdateInstalling, heartbeat.UpdatePendingReboot, heartbeat.UpdateTrial:
		return true
	}
	return false
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
	// An install already waiting to reboot (or on trial) would be rebooted into
	// by ModeApply without the installer running: never on this approval.
	if st := res.Status; st != nil && (st.State == heartbeat.UpdatePendingReboot || st.State == heartbeat.UpdateTrial) {
		return "", false, &Refusal{"update_pending", fmt.Sprintf("%s is already %s; wait for the health gate's verdict", st.TargetVersion, st.State)}
	}
	if res.Candidate == nil || res.Candidate.Meta.Version != version {
		offered := "none"
		if res.Candidate != nil {
			offered = res.Candidate.Meta.Version
		}
		return "", false, &Refusal{"version_not_offered", fmt.Sprintf("the channel offers %s, not the approved %s; nothing was installed", offered, version)}
	}
	e.Installer = pinnedInstaller{inner: e.Installer, cfg: c, want: version}
	rb := &announceRebooter{inner: e.Rebooter, before: goingDown, cfg: c, want: version}
	e.Rebooter = rb
	res, err = run(ctx, e, update.ModeApply)
	if rb.refused != nil {
		return "", false, &Refusal{"update_pending", rb.refused.Error()}
	}
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

// announceRebooter reboots only into the approved version, and journals
// going_down first. The engine reboots without installing when an install is
// already pending, so the target version is checked again here.
type announceRebooter struct {
	inner   update.Rebooter
	before  func()
	cfg     *update.Config
	want    string
	refused error
}

func (a *announceRebooter) Reboot(ctx context.Context) error {
	st, err := update.LoadStatus(a.cfg)
	if err != nil {
		a.refused = fmt.Errorf("the update status cannot be read, so the box was not rebooted: %w", err)
		return a.refused
	}
	if st.TargetVersion != a.want {
		a.refused = fmt.Errorf("the update engine would reboot into %s, but the owner approved %s; the box was not rebooted", st.TargetVersion, a.want)
		return a.refused
	}
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

// SettingsUnavailable implements OSSettings: a box without update.conf has no OS updates to set.
func (u *UpdateEngine) SettingsUnavailable() string {
	_, why := u.config()
	return why
}

// SetSettings implements OSSettings (REL-02, #154): it stores the owner's approved policy and
// window under the update state directory (/data); the read-only image file stays as shipped.
// The update service and the heartbeat read it from their next cycle, without a restart.
func (u *UpdateEngine) SetSettings(policy, window string) (string, error) {
	c, why := u.config()
	if why != "" {
		return "", &Refusal{"unavailable", why}
	}
	p, err := update.ParsePolicy(policy)
	if err != nil {
		return "", &Refusal{"bad_request", err.Error()}
	}
	w, err := update.ParseWindow(window)
	if err != nil {
		return "", &Refusal{"bad_request", "window: " + err.Error()}
	}
	if err := update.WriteOwner(c, update.OwnerSettings{Policy: p, Window: w}); err != nil {
		return "", err
	}
	if u.Log != nil {
		u.Log.Info("owner update settings saved", "policy", p, "window", w.String())
	}
	what := map[update.Policy]string{
		update.PolicyAuto:   "updates install by themselves inside the window",
		update.PolicyNotify: "updates wait for your approval",
		update.PolicyOff:    "automatic updates are off; you install them yourself",
	}[p]
	return fmt.Sprintf("update policy %s, window %s: %s (from the next check)", p, w, what), nil
}
