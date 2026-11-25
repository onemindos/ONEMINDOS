// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/update"
)

// OSRoller goes back to the previous OS version (P-16). An owner approves it
// with a passkey; the host never decides that for itself.
type OSRoller interface {
	// RollbackUnavailable says why this box cannot go back now (no A/B image,
	// no other slot, the other slot is not known good, an update is running), or "".
	RollbackUnavailable() string
	// Prepare checks that version is still the version of the other slot and
	// that the slot is known good, then makes it the one the box boots next.
	// It does not reboot. A *Refusal is returned when it must not go back.
	Prepare(ctx context.Context, version string) error
	// Cancel undoes Prepare when the reboot that was meant to follow failed or never came.
	Cancel(ctx context.Context)
	// Hold keeps the update engine from running (its timer would clear the version being left from
	// the bad-releases list: it is still the running, committed one) until release is called or the
	// process ends. A *Refusal (engine_busy) is returned when a run is in progress.
	Hold() (release func(), err error)
	// RunningVersion is the OS version booted now, or "" when it cannot be read.
	RunningVersion() string
}

// RollbackTarget is the slot a rollback would boot.
type RollbackTarget struct {
	Bootname string // "A" or "B": RAUC's name for the slot in its boot chooser
	Version  string // the bundle version installed in it
}

// SlotRollback implements OSRoller with RAUC. It never runs `rauc install`, so
// it needs no bundle and no network: it only flips which already installed,
// already committed slot boots next. The health gate then sees no trial marker
// and commits the slot it booted ("committed" mode, os/gate/onemind-health-gate).
type SlotRollback struct {
	ConfigPath string
	// Run runs `rauc args...` and returns its output. Tests replace it.
	Run func(ctx context.Context, bin string, args ...string) ([]byte, error)
}

func (r *SlotRollback) config() (*update.Config, string) {
	return (&UpdateEngine{ConfigPath: r.ConfigPath}).config()
}

func (r *SlotRollback) rauc(ctx context.Context, c *update.Config, args ...string) ([]byte, error) {
	bin := c.RAUCBinary
	if bin == "" {
		bin = "rauc"
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if r.Run != nil {
		return r.Run(ctx, bin, args...)
	}
	out, err := exec.CommandContext(ctx, bin, args...).CombinedOutput()
	if err != nil {
		return out, fmt.Errorf("rauc %s: %w: %s", strings.Join(args, " "), err, lastOutputLine(out))
	}
	return out, nil
}

func lastOutputLine(b []byte) string {
	s := strings.TrimSpace(string(b))
	if i := strings.LastIndexByte(s, '\n'); i >= 0 {
		s = s[i+1:]
	}
	if len(s) > 300 {
		s = s[:300]
	}
	return s
}

// Target finds the slot a rollback would boot, or says why there is none.
func (r *SlotRollback) Target(ctx context.Context) (RollbackTarget, *update.Config, *Refusal) {
	c, why := r.config()
	if why != "" {
		return RollbackTarget{}, nil, &Refusal{"unavailable", why}
	}
	box, err := update.ReadBox(c)
	if err != nil {
		return RollbackTarget{}, nil, &Refusal{"unavailable", "this box's OS version cannot be read: " + err.Error()}
	}
	// A trial marker means an update is waiting for its health gate verdict: the
	// gate decides that slot, not the owner (the same rule as an install).
	if box.MarkerPresent {
		return RollbackTarget{}, nil, &Refusal{"update_pending", "an OS update is waiting for the health gate's verdict; wait for it before going back"}
	}
	st, err := update.LoadStatus(c)
	if err != nil {
		return RollbackTarget{}, nil, &Refusal{"unavailable", "the OS update status cannot be read: " + err.Error()}
	}
	if busy(st.State) {
		return RollbackTarget{}, nil, &Refusal{"update_in_progress", "an OS update is " + st.State + "; wait for the health gate's verdict"}
	}
	// --detailed adds each slot's own record (the bundle version it was installed from).
	out, err := r.rauc(ctx, c, "status", "--detailed", "--output-format=json")
	if err != nil {
		return RollbackTarget{}, nil, &Refusal{"unavailable", "RAUC does not answer: " + err.Error()}
	}
	t, rf := PreviousSlot(out, box.Version, st.PreviousVersion)
	if rf != nil {
		return t, c, rf
	}
	// A version the owner (or the gate) already turned away is not "the previous version": going back
	// twice would otherwise swap the two slots and roll forward into what was just left.
	if bad, err := update.ReadBadReleases(c); err == nil && bad.Verdict(t.Version) != "" {
		return RollbackTarget{}, c, &Refusal{"previous_rolled_back", fmt.Sprintf("the other slot holds %s, which was rolled back earlier; the box will not boot it again until a newer release replaces it", t.Version)}
	}
	return t, c, nil
}

// PreviousSlot reads `rauc status --output-format=json` and returns the one
// rootfs slot that is not booted, when it is bootable: marked good (it passed
// the health gate once) and holding a known version other than the running one.
//
// A slot written by the image builder has no record of its own, so its version is taken from
// known (the update engine's note of the version it replaced, update.Status.PreviousVersion).
func PreviousSlot(raucJSON []byte, running, known string) (RollbackTarget, *Refusal) {
	st := detect.ParseRAUC(raucJSON)
	if st.BootedSlot == nil {
		return RollbackTarget{}, &Refusal{"no_previous_slot", "RAUC does not say which slot booted"}
	}
	booted := *st.BootedSlot
	var others []heartbeat.Slot
	for _, s := range st.Slots {
		isRoot := s.Class == "rootfs" || (s.Class == "" && strings.HasPrefix(s.Name, "rootfs."))
		if isRoot && s.Bootname != booted && s.Name != booted {
			others = append(others, s)
		}
	}
	if len(others) != 1 {
		return RollbackTarget{}, &Refusal{"no_previous_slot", "this box has no single other system slot to go back to"}
	}
	o := others[0]
	if o.BundleVersion == "" {
		o.BundleVersion = known
	}
	switch {
	case o.BootStatus != "good":
		return RollbackTarget{}, &Refusal{"previous_not_good", fmt.Sprintf("slot %s is not marked good (%s): it did not pass the health gate, so the box will not boot it", o.Bootname, orNone(o.BootStatus))}
	case o.BundleVersion == "":
		return RollbackTarget{}, &Refusal{"previous_unknown", fmt.Sprintf("slot %s holds no known OneMind version", o.Bootname)}
	case o.BundleVersion == running:
		return RollbackTarget{}, &Refusal{"same_version", fmt.Sprintf("the other slot holds %s, the version already running", running)}
	case o.Bootname == "":
		return RollbackTarget{}, &Refusal{"previous_unknown", "the other slot has no boot name"}
	}
	return RollbackTarget{Bootname: o.Bootname, Version: o.BundleVersion}, nil
}

func orNone(s string) string {
	if s == "" {
		return "no status"
	}
	return s
}

// RollbackUnavailable implements OSRoller.
func (r *SlotRollback) RollbackUnavailable() string {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if _, _, rf := r.Target(ctx); rf != nil {
		return rf.Message
	}
	return ""
}

// Prepare implements OSRoller.
func (r *SlotRollback) Prepare(ctx context.Context, version string) error {
	t, c, rf := r.Target(ctx)
	if rf != nil {
		return rf
	}
	if t.Version != version {
		return &Refusal{"version_changed", fmt.Sprintf("the previous version is %s, not the approved %s; nothing was changed", t.Version, version)}
	}
	box, err := update.ReadBox(c)
	if err != nil {
		return err
	}
	// Remember the version we leave, so the update service does not put it straight back
	// (the security channel installs on its own). The gate's own list, same format:
	// an unknown verdict is "never retried" (update.ReadBadReleases).
	if err := appendBadRelease(c, box.Version); err != nil {
		return fmt.Errorf("could not record that %s was rolled back: %w", box.Version, err)
	}
	if _, err := r.rauc(ctx, c, "status", "mark-active", "other"); err != nil {
		_, _ = update.ClearBadRelease(c, box.Version)
		return err
	}
	return nil
}

// Hold implements OSRoller with the update engine's own lock.
func (r *SlotRollback) Hold() (func(), error) {
	c, why := r.config()
	if why != "" {
		return nil, &Refusal{"unavailable", why}
	}
	unlock, err := update.Lock(c)
	if errors.Is(err, update.ErrBusy) {
		return nil, &Refusal{"engine_busy", "the update service is in the middle of a cycle; ask again in a minute"}
	} else if err != nil {
		return nil, err
	}
	return unlock, nil
}

// RunningVersion implements OSRoller.
func (r *SlotRollback) RunningVersion() string {
	c, why := r.config()
	if why != "" {
		return ""
	}
	box, err := update.ReadBox(c)
	if err != nil {
		return ""
	}
	return box.Version
}

// Cancel implements OSRoller: make the running slot the next boot again.
func (r *SlotRollback) Cancel(ctx context.Context) {
	if c, why := r.config(); why == "" {
		_, _ = r.rauc(ctx, c, "status", "mark-active", "booted")
		if box, err := update.ReadBox(c); err == nil {
			_, _ = update.ClearBadRelease(c, box.Version)
		}
	}
}

func appendBadRelease(c *update.Config, version string) error {
	if err := os.MkdirAll(c.GateDir, 0o755); err != nil {
		return err
	}
	f, err := os.OpenFile(filepath.Join(c.GateDir, "bad-releases"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(f, "%s version=%s verdict=owner-rollback\n", time.Now().UTC().Format(time.RFC3339), version)
	if err2 := f.Sync(); err == nil {
		err = err2
	}
	if err2 := f.Close(); err == nil {
		err = err2
	}
	return err
}
