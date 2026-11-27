// SPDX-License-Identifier: Apache-2.0

// Package host runs owner-approved host actions (#146, #142): restart,
// shutdown, OS install, factory reset, restarting one service (#636) and renaming the box (P-05). It is `onemindd host serve`, its own
// privileged unit, reached by the gateway over a Unix socket
// (docs/leap/core/HOST-ACTIONS.md).
//
// It never decides policy: the gateway approves (an owner, never an agent
// alone), then sends the approved action's id. This service checks the request
// is well formed and that the box can do it, journals it by action id before
// anything happens (so a retry never runs it twice and the result survives the
// reboot it causes), and reports what happened.
package host

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"regexp"
	"sync"
	"time"

	"github.com/onemindos/onemindos/internal/keymap"
)

// Kinds of host action. The gateway's action types map onto them:
// system.restart, system.shutdown, system.factory_reset, os.update.install,
// os.rollback, service.restart, system.set_timezone, instance.rename, storage.eject, system.set_keymap.
const (
	KindRestart        = "restart"
	KindShutdown       = "shutdown"
	KindFactoryReset   = "factory-reset"
	KindOSInstall      = "os-install"
	KindOSRollback     = "os-rollback"
	KindServiceRestart = "service-restart"
	KindSetTimezone    = "set-timezone"
	KindSetHostname    = "set-hostname"
	KindEject          = "eject"      // P-10: unmount and power off one USB drive
	KindSetKeymap      = "set-keymap" // P-11: the console and kiosk keyboard layout (keymap.go)
)

// Kinds lists every kind in a stable order (GET /v1/status).
var Kinds = []string{KindRestart, KindShutdown, KindFactoryReset, KindOSInstall, KindOSRollback, KindServiceRestart, KindSetTimezone, KindSetHostname, KindEject, KindSetKeymap}

// Operation states. going_down: the box was told to reboot or power off; the
// next boot turns it into succeeded.
const (
	StateAccepted  = "accepted"
	StateRunning   = "running"
	StateGoingDown = "going_down"
	StateSucceeded = "succeeded"
	StateFailed    = "failed"
)

// Terminal reports whether an operation state is final.
func Terminal(state string) bool { return state == StateSucceeded || state == StateFailed }

var (
	actionIDRe = regexp.MustCompile(`^[A-Za-z0-9_.:-]{1,128}$`)
	planHashRe = regexp.MustCompile(`^[0-9a-f]{64}$`)
	versionRe  = regexp.MustCompile(`^[0-9A-Za-z.+-]{1,64}$`) // the gateway's InstallParams.version
	// One lower-case DNS label: the name avahi publishes as <name>.local (the gateway derives it from the box name).
	hostnameRe = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`)
	serialRe   = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,64}$`)
	driveRe    = regexp.MustCompile(`^/dev/[a-z][a-z0-9]{1,15}$`)
	unitRe     = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.@-]{0,90}\.(service|socket|timer|path)$`)
)

// ErrNoJournal: the journal is not open, so nothing may start (a result that
// cannot be recorded must not be acted on).
var ErrNoJournal = errors.New("the host action journal is not available (is /data mounted?)")

// Refusal is a well-formed request the box will not run now. Reason is a
// stable code for the gateway; Message is for the owner.
type Refusal struct{ Reason, Message string }

func (r *Refusal) Error() string { return r.Reason + ": " + r.Message }

// Request is POST /v1/operations: the action the owner approved.
type Request struct {
	ActionID string `json:"action_id"`
	Kind     string `json:"kind"`
	Version  string `json:"version,omitempty"` // os-install only: the version the owner approved
	// PlanSHA256 (factory-reset only, required) is the hash of the plan the
	// owner approved (GET /v1/plans/factory-reset). The box wipes only if its
	// disks still match that exact plan.
	PlanSHA256 string `json:"plan_sha256,omitempty"`
	// Unit (service-restart only, required) is the systemd unit the owner approved restarting.
	Unit string `json:"unit,omitempty"`
	// Zone (set-timezone only, required) is the IANA zone name the owner approved, e.g. Europe/Berlin.
	Zone string `json:"zone,omitempty"`
	// Hostname (set-hostname only, required) is the DNS label the owner approved for the box.
	Hostname string `json:"hostname,omitempty"`
	// Device (eject only, required) is the removable disk the owner approved ejecting, e.g. /dev/sdb.
	Device string `json:"device,omitempty"`
	// Serial (eject only, optional) is the serial number the drive had when the owner was asked. If the stick was
	// swapped for another one before approval, the serial differs and the host refuses. Empty: the drive reports none.
	Serial string `json:"serial,omitempty"`
	// Layout and Variant (set-keymap only; Layout required) are the xkb names the owner approved ("de", "nodeadkeys").
	Layout  string `json:"layout,omitempty"`
	Variant string `json:"variant,omitempty"`
}

// Validate refuses a malformed request (HTTP 400).
func (r Request) Validate() error {
	if !actionIDRe.MatchString(r.ActionID) {
		return errors.New("action_id must be 1-128 characters of A-Z a-z 0-9 _ . : -")
	}
	if (r.Kind == KindServiceRestart) != (r.Unit != "") {
		return fmt.Errorf("unit is required for %s and only for it", KindServiceRestart)
	}
	if (r.Kind == KindSetTimezone) != (r.Zone != "") {
		return fmt.Errorf("zone is required for %s and only for it", KindSetTimezone)
	}
	if (r.Kind == KindSetHostname) != (r.Hostname != "") {
		return fmt.Errorf("hostname is required for %s and only for it", KindSetHostname)
	}
	if (r.Kind == KindEject) != (r.Device != "") {
		return fmt.Errorf("device is required for %s and only for it", KindEject)
	}
	if r.Serial != "" && (r.Kind != KindEject || !serialRe.MatchString(r.Serial)) {
		return errors.New("serial is only for eject and is 1-64 characters of A-Z a-z 0-9 . _ : -")
	}
	if (r.Kind == KindSetKeymap) != (r.Layout != "") || (r.Kind != KindSetKeymap && r.Variant != "") {
		return fmt.Errorf("layout is required for %s and only for it (variant too)", KindSetKeymap)
	}
	switch r.Kind {
	case KindEject:
		if r.Version != "" || r.PlanSHA256 != "" {
			return errors.New("eject takes only a device")
		}
		if !driveRe.MatchString(r.Device) {
			return errors.New("device must be a disk path such as /dev/sdb")
		}
	case KindSetTimezone:
		if r.Version != "" || r.PlanSHA256 != "" {
			return errors.New("set-timezone takes only a zone")
		}
		if !ZoneName(r.Zone) {
			return errors.New("zone must be an IANA time zone name such as Europe/Berlin")
		}
	case KindRestart, KindShutdown, KindFactoryReset:
		if r.Version != "" {
			return fmt.Errorf("%s takes no version", r.Kind)
		}
		if r.Kind == KindFactoryReset && !planHashRe.MatchString(r.PlanSHA256) {
			return errors.New("factory-reset needs plan_sha256, the hash of the plan the owner approved (64 hex characters)")
		}
		if r.Kind != KindFactoryReset && r.PlanSHA256 != "" {
			return fmt.Errorf("%s takes no plan_sha256", r.Kind)
		}
	case KindOSInstall:
		if r.PlanSHA256 != "" {
			return errors.New("os-install takes no plan_sha256")
		}
		if !versionRe.MatchString(r.Version) {
			return errors.New("os-install needs the approved version (1-64 characters of 0-9 A-Z a-z . + -)")
		}
	case KindOSRollback:
		if r.PlanSHA256 != "" {
			return errors.New("os-rollback takes no plan_sha256")
		}
		if !versionRe.MatchString(r.Version) {
			return errors.New("os-rollback needs the approved version to go back to (1-64 characters of 0-9 A-Z a-z . + -)")
		}
	case KindServiceRestart:
		if r.Version != "" || r.PlanSHA256 != "" {
			return errors.New("service-restart takes only a unit")
		}
		if !unitRe.MatchString(r.Unit) {
			return errors.New("unit must be a systemd unit name")
		}
	case KindSetHostname:
		if r.Version != "" || r.PlanSHA256 != "" {
			return errors.New("set-hostname takes only a hostname")
		}
		if !hostnameRe.MatchString(r.Hostname) {
			return errors.New("hostname must be one lower-case DNS label (a-z, 0-9 and -, at most 63 characters)")
		}
	case KindSetKeymap:
		if r.Version != "" || r.PlanSHA256 != "" {
			return errors.New("set-keymap takes only a layout and a variant")
		}
		if err := keymap.ValidID(r.Layout, r.Variant); err != nil {
			return err
		}
	default:
		return fmt.Errorf("unknown kind %q (restart, shutdown, factory-reset, os-install, os-rollback, service-restart, set-timezone, set-hostname, eject, set-keymap)", r.Kind)
	}
	return nil
}

// Op is the journal record of one action, keyed by the gateway's action id.
type Op struct {
	ID         string     `json:"action_id"`
	Kind       string     `json:"kind"`
	Version    string     `json:"version,omitempty"`
	PlanSHA256 string     `json:"plan_sha256,omitempty"` // factory-reset: the approved plan
	Unit       string     `json:"unit,omitempty"`        // service-restart: the approved unit
	Zone       string     `json:"zone,omitempty"`        // set-timezone: the approved zone
	Hostname   string     `json:"hostname,omitempty"`    // set-hostname: the approved name
	Device     string     `json:"device,omitempty"`      // eject: the approved drive
	Serial     string     `json:"serial,omitempty"`      // eject: its serial when approved
	Layout     string     `json:"layout,omitempty"`      // set-keymap: the approved layout
	Variant    string     `json:"variant,omitempty"`     // set-keymap: the approved variant
	State      string     `json:"state"`
	Reason     string     `json:"reason,omitempty"` // failed: a stable code
	Message    string     `json:"message,omitempty"`
	BootID     string     `json:"boot_id"` // the boot it was accepted on
	AcceptedAt time.Time  `json:"accepted_at"`
	UpdatedAt  time.Time  `json:"updated_at"`
	FinishedAt *time.Time `json:"finished_at,omitempty"`
}

// Power turns the box off or restarts it (systemd in production).
type Power interface {
	Reboot(ctx context.Context) error
	PowerOff(ctx context.Context) error
}

// OSInstaller hands an approved version to the update engine (internal/update).
type OSInstaller interface {
	// Unavailable says why this box cannot install OS updates, or "".
	Unavailable() string
	// UpdateBusy says why the box must not go down now (an install is
	// downloading, installing, waiting to reboot or on its health-gate trial), or "".
	UpdateBusy() string
	// Install installs version through the engine's normal path (snapshot,
	// RAUC into the other slot, health-gated trial). goingDown is called just
	// before the engine reboots. A *Refusal is returned when version is not the
	// update on offer. With rebooted false, note says why the box stays up.
	Install(ctx context.Context, version string, goingDown func()) (note string, rebooted bool, err error)
}

// Resetter arms the two-phase factory reset (HOST-ACTIONS.md §4).
type Resetter interface {
	Unavailable() string
	// Plan inspects the disks now and returns exactly what a reset would erase.
	Plan(ctx context.Context) ResetPlan
	// Arm re-plans, refuses unless op.PlanSHA256 still matches, and writes the
	// marker the next boot's wipe unit acts on.
	Arm(ctx context.Context, op Op) error
}

// Units restarts one service (internal/svcregistry.Reader in production).
// CheckRestart refuses a unit the image's registry does not list or does not
// mark restartable, and the rescue, first-boot, host and data-layout units.
type Units interface {
	CheckRestart(unit string) error
	Restart(ctx context.Context, unit string) error
}

// Zones sets the box's time zone (Timezone in timezone.go in production). Check refuses a name this
// box has no zone file for; Set makes the zone the box's, now and after every reboot and A/B update.
type Zones interface {
	Check(zone string) error
	Set(ctx context.Context, zone string) error
}

// Hostnamer gives the box a new name (SystemHostname in production, rename.go).
type Hostnamer interface {
	Set(ctx context.Context, name string) error
	// Reload runs after the answer is journaled and Delay has passed: it restarts what only reads the name at start
	// (the gateway's box certificate and join QR). A failure is logged; the box is already renamed.
	Reload(ctx context.Context) error
}

// Keymap reads and changes the keyboard layout of the text console and the kiosk screen (keymap.go).
type Keymap interface {
	// Unavailable says why this image cannot change the layout (no list of layouts), or "".
	Unavailable() string
	// View is what the owner can pick from and what is picked now.
	View() (KeymapView, error)
	// Check refuses a layout or variant the image does not offer (wrapping keymap.ErrUnknown).
	Check(layout, variant string) error
	// Set writes the layout to /data and applies it to the console and the kiosk. When applying fails it puts the
	// previous layout back, so a bad choice never leaves a box with a keyboard it cannot type on.
	Set(ctx context.Context, layout, variant string) error
}

// Service runs the actions. Power, OS and Reset may be nil: that kind is then
// reported unavailable and refused.
type Service struct {
	Store   *Store // nil: status only, every action refused
	Power   Power
	OS      OSInstaller
	Roll    OSRoller // os-rollback; nil: refused
	Reset   Resetter
	SMB     SMBManager     // file sharing (smb.go); nil: not on this box
	Flatpak FlatpakManager // Flathub desktop apps (flatpak.go); nil: not on this box
	SSH     SSHManager     // the owner's SSH keys and switch (ssh.go); nil: not on this box
	Net     NetManager     // wired network changes with rollback (netset.go); nil: not on this box
	Units   Units          // service-restart; nil: refused
	Zones   Zones          // set-timezone; nil: refused
	Names   Hostnamer      // set-hostname; nil: refused
	Media   Media          // storage housekeeping and eject (housekeeping.go); nil: not on this box
	Keymap  Keymap         // set-keymap; nil: refused
	BootID  string         // /proc/sys/kernel/random/boot_id
	Delay   time.Duration  // before the box goes down, so the gateway records "accepted" first
	Now     func() time.Time
	Log     *slog.Logger

	mu     sync.Mutex
	active *Op
	wg     sync.WaitGroup
}

func (s *Service) now() time.Time {
	if s.Now != nil {
		return s.Now().UTC()
	}
	return time.Now().UTC()
}

func (s *Service) log() *slog.Logger {
	if s.Log != nil {
		return s.Log
	}
	return slog.New(slog.DiscardHandler)
}

// Unavailable says why kind cannot run on this box now, or "".
func (s *Service) Unavailable(kind string) string {
	if s.Store == nil {
		return ErrNoJournal.Error()
	}
	switch kind {
	case KindRestart, KindShutdown:
		if s.Power == nil {
			return "this host service has no power control"
		}
	case KindOSInstall:
		if s.OS == nil {
			return "this box has no OS update engine"
		}
		return s.OS.Unavailable()
	case KindOSRollback:
		if s.Roll == nil {
			return "this box has no OS rollback"
		}
		return s.Roll.RollbackUnavailable()
	case KindServiceRestart:
		if s.Units == nil {
			return "this host service cannot restart services"
		}
	case KindSetTimezone:
		if s.Zones == nil {
			return "this host service cannot set the time zone"
		}
	case KindSetHostname:
		if s.Names == nil {
			return "this host service cannot rename the box"
		}
	case KindEject:
		if s.Media == nil {
			return "this host service cannot eject drives"
		}
		return s.Media.Unavailable()
	case KindSetKeymap:
		if s.Keymap == nil {
			return "this host service cannot change the keyboard layout"
		}
		return s.Keymap.Unavailable()
	case KindFactoryReset:
		if s.Reset == nil {
			return "factory reset is not in this OneMind version yet: the early-boot wipe ships separately (HOST-ACTIONS.md §4)"
		}
		return s.Reset.Unavailable()
	}
	return ""
}

// Active is the action running or taking the box down, or nil.
func (s *Service) Active() *Op {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.active == nil {
		return nil
	}
	c := *s.active
	return &c
}

// Submit records and starts an approved action. A repeat of a known action id
// with the same request returns the journaled operation (created false) and
// starts nothing.
func (s *Service) Submit(ctx context.Context, req Request) (op Op, created bool, err error) {
	if err := req.Validate(); err != nil {
		return Op{}, false, err
	}
	if s.Store == nil {
		return Op{}, false, ErrNoJournal
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if old, err := s.Store.Get(req.ActionID); err == nil {
		if old.Kind != req.Kind || old.Version != req.Version || old.PlanSHA256 != req.PlanSHA256 || old.Unit != req.Unit || old.Zone != req.Zone || old.Hostname != req.Hostname || old.Device != req.Device || old.Serial != req.Serial || old.Layout != req.Layout || old.Variant != req.Variant {
			return Op{}, false, &Refusal{"action_id_reused", "action " + req.ActionID + " was already sent as a different request"}
		}
		if s.active != nil && s.active.ID == old.ID {
			return *s.active, false, nil
		}
		return old, false, nil
	} else if !errors.Is(err, ErrNotFound) {
		return Op{}, false, err
	}
	if s.active != nil {
		return Op{}, false, &Refusal{"busy", fmt.Sprintf("%s (action %s) is still %s", s.active.Kind, s.active.ID, s.active.State)}
	}
	if why := s.Unavailable(req.Kind); why != "" {
		return Op{}, false, &Refusal{"unavailable", why}
	}
	// A restart, shutdown or reset in the middle of an OS update would cut the
	// install short or spend one of the health gate's trial boots.
	// A keyboard layout change touches no update state, so it is allowed during one.
	if req.Kind != KindOSInstall && req.Kind != KindSetKeymap && s.OS != nil {
		if why := s.OS.UpdateBusy(); why != "" {
			return Op{}, false, &Refusal{"update_in_progress", why}
		}
	}
	if req.Kind == KindServiceRestart {
		// Checked again here, whatever the gateway said: the registry on the signed image decides.
		if err := s.Units.CheckRestart(req.Unit); err != nil {
			return Op{}, false, &Refusal{"not_restartable", req.Unit + ": " + err.Error()}
		}
	}
	if req.Kind == KindSetTimezone {
		if err := s.Zones.Check(req.Zone); err != nil {
			return Op{}, false, &Refusal{"unknown_zone", err.Error()}
		}
	}
	if req.Kind == KindEject {
		// Checked again here, whatever the gateway said: only a removable disk the box is not using.
		if err := s.Media.CheckEject(ctx, req.Device, req.Serial); err != nil {
			var ref *Refusal
			if errors.As(err, &ref) {
				return Op{}, false, ref
			}
			return Op{}, false, &Refusal{"unavailable", err.Error()}
		}
	}
	if req.Kind == KindSetKeymap {
		// Checked again here, whatever the gateway said: the layouts the signed image ships decide.
		if err := s.Keymap.Check(req.Layout, req.Variant); err != nil {
			reason := "unavailable"
			if errors.Is(err, keymap.ErrUnknown) {
				reason = "unknown_layout"
			}
			return Op{}, false, &Refusal{reason, err.Error()}
		}
	}
	if req.Kind == KindFactoryReset {
		// The owner approved one plan. If the disks changed since (a member
		// added or pulled), nothing is armed: the owner must see the new plan.
		if p := s.Reset.Plan(ctx); p.SHA256 != req.PlanSHA256 {
			return Op{}, false, &Refusal{"plan_changed", "the disks changed since the plan you approved; request the factory reset again to see the new plan"}
		}
	}
	now := s.now()
	op = Op{ID: req.ActionID, Kind: req.Kind, Version: req.Version, PlanSHA256: req.PlanSHA256, Unit: req.Unit, Zone: req.Zone, Hostname: req.Hostname, Device: req.Device, Serial: req.Serial, Layout: req.Layout, Variant: req.Variant, State: StateAccepted, BootID: s.BootID,
		AcceptedAt: now, UpdatedAt: now, Message: "accepted"}
	if err := s.Store.Put(op); err != nil {
		return Op{}, false, err
	}
	s.active = &op
	cp := op
	s.wg.Add(1)
	go func() {
		defer s.wg.Done()
		s.run(ctx, cp)
	}()
	s.log().Info("host action accepted", "action_id", op.ID, "kind", op.Kind, "version", op.Version, "unit", op.Unit, "hostname", op.Hostname)
	return op, true, nil
}

// Wait blocks until running actions return (tests, shutdown).
func (s *Service) Wait() { s.wg.Wait() }

// set journals a state change of the active operation.
func (s *Service) set(op *Op, state, reason, msg string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	op.State, op.Reason, op.Message, op.UpdatedAt = state, reason, msg, s.now()
	if Terminal(state) {
		t := op.UpdatedAt
		op.FinishedAt = &t
	}
	if err := s.Store.Put(*op); err != nil {
		s.log().Error("host journal write failed", "action_id", op.ID, "err", err)
	}
	if Terminal(state) {
		s.active = nil
	} else {
		c := *op
		s.active = &c
	}
	s.log().Info("host action", "action_id", op.ID, "kind", op.Kind, "state", state, "reason", reason, "message", msg)
}

func (s *Service) run(ctx context.Context, op Op) {
	switch op.Kind {
	case KindRestart, KindShutdown:
		select {
		case <-ctx.Done(): // the service is stopping: Resume reports it on the next start
			return
		case <-time.After(s.Delay):
		}
		down, msg := s.Power.Reboot, "restarting"
		if op.Kind == KindShutdown {
			down, msg = s.Power.PowerOff, "shutting down"
		}
		s.set(&op, StateGoingDown, "", msg)
		if err := down(ctx); err != nil {
			s.set(&op, StateFailed, "host_error", msg+" failed: "+err.Error())
		}
	case KindOSInstall:
		s.set(&op, StateRunning, "", "installing "+op.Version+" through the update engine")
		note, rebooted, err := s.OS.Install(ctx, op.Version, func() {
			s.set(&op, StateGoingDown, "", "installed "+op.Version+"; rebooting into it for the health gate's trial")
		})
		var r *Refusal
		switch {
		case errors.As(err, &r):
			s.set(&op, StateFailed, r.Reason, r.Message)
		case err != nil:
			s.set(&op, StateFailed, "engine_error", err.Error())
		case !rebooted:
			s.set(&op, StateSucceeded, "", note)
		}
	case KindOSRollback:
		s.set(&op, StateRunning, "", "going back to "+op.Version)
		// Hold the update engine's lock from before Prepare until the box is down: an engine run in
		// the delay would clear the version being left from bad-releases (it is still the running,
		// committed one), and the security channel could then install it again.
		release, err := s.Roll.Hold()
		if err != nil {
			var r *Refusal
			if errors.As(err, &r) {
				s.set(&op, StateFailed, r.Reason, r.Message)
			} else {
				s.set(&op, StateFailed, "host_error", "the rollback could not start; nothing changed: "+err.Error())
			}
			return
		}
		held := true
		defer func() {
			if held {
				release()
			}
		}()
		if err := s.Roll.Prepare(ctx, op.Version); err != nil {
			var r *Refusal
			if errors.As(err, &r) {
				s.set(&op, StateFailed, r.Reason, r.Message)
			} else {
				s.set(&op, StateFailed, "host_error", "the rollback could not be prepared; nothing changed: "+err.Error())
			}
			return
		}
		select {
		case <-ctx.Done():
			// Stopping with the boot order already flipped: put it back (and the version we were
			// leaving), or the box would go back at some later reboot while the request says failed.
			s.Roll.Cancel(context.Background())
			s.set(&op, StateFailed, "interrupted", "the host service stopped before the box went back; nothing changed")
			return
		case <-time.After(s.Delay):
		}
		s.set(&op, StateGoingDown, "", "going back to "+op.Version+"; rebooting into the previous system")
		if err := s.Power.Reboot(ctx); err != nil {
			s.Roll.Cancel(context.Background())
			s.set(&op, StateFailed, "host_error", "restart failed: "+err.Error()+"; the box stays on the current version")
			return
		}
		held = false // keep the lock until the box is down
	case KindServiceRestart:
		s.set(&op, StateRunning, "", "restarting "+op.Unit)
		if err := s.Units.Restart(ctx, op.Unit); err != nil {
			s.set(&op, StateFailed, "host_error", "restarting "+op.Unit+" failed: "+err.Error())
			return
		}
		s.set(&op, StateSucceeded, "", op.Unit+" restarted")
	case KindSetTimezone:
		s.set(&op, StateRunning, "", "setting the time zone to "+op.Zone)
		if err := s.Zones.Set(ctx, op.Zone); err != nil {
			s.set(&op, StateFailed, "host_error", "setting the time zone failed: "+err.Error())
			return
		}
		s.set(&op, StateSucceeded, "", "time zone set to "+op.Zone)
	case KindSetHostname:
		s.set(&op, StateRunning, "", "renaming the box to "+op.Hostname)
		if err := s.Names.Set(ctx, op.Hostname); err != nil {
			s.set(&op, StateFailed, "host_error", "renaming the box failed: "+err.Error())
			return
		}
		s.set(&op, StateSucceeded, "", "the box is now called "+op.Hostname+" (reachable as "+op.Hostname+".local)")
		select {
		case <-ctx.Done():
			return
		case <-time.After(s.Delay): // the gateway records the answer first: it is restarted next
		}
		if err := s.Names.Reload(ctx); err != nil {
			s.log().Warn("restarting the gateway after a rename failed", "err", err)
		}
	case KindEject:
		s.set(&op, StateRunning, "", "unmounting "+op.Device)
		if err := s.Media.Eject(ctx, op.Device, op.Serial); err != nil {
			var ref *Refusal
			if errors.As(err, &ref) {
				s.set(&op, StateFailed, ref.Reason, ref.Message)
				return
			}
			s.set(&op, StateFailed, "host_error", err.Error())
			return
		}
		s.set(&op, StateSucceeded, "", op.Device+" is safe to remove")
	case KindSetKeymap:
		label := keymap.Label(op.Layout, op.Variant)
		s.set(&op, StateRunning, "", "setting the keyboard layout to "+label)
		if err := s.Keymap.Set(ctx, op.Layout, op.Variant); err != nil {
			s.set(&op, StateFailed, "host_error", "the keyboard layout was not changed: "+err.Error())
			return
		}
		s.set(&op, StateSucceeded, "", "the keyboard layout is now "+label)
	case KindFactoryReset:
		s.set(&op, StateRunning, "", "arming the factory reset")
		if err := s.Reset.Arm(ctx, op); err != nil {
			s.set(&op, StateFailed, "host_error", "the factory reset could not be armed; nothing was wiped: "+err.Error())
			return
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(s.Delay):
		}
		s.set(&op, StateGoingDown, "", "restarting to wipe the box")
		if err := s.Power.Reboot(ctx); err != nil {
			s.set(&op, StateFailed, "host_error", "restart failed: "+err.Error()+"; the reset stays armed for the next boot")
		}
	}
}

// resumeRollback settles an os-rollback left open. Prepare has flipped the boot order, so every way
// out must either confirm the box went back or flip it again: otherwise the box goes back at some
// later reboot while the request says failed. Succeeded only when the running version is the one
// the owner approved.
func (s *Service) resumeRollback(op *Op, earlier bool) {
	running := s.Roll.RunningVersion()
	if earlier && running == op.Version {
		s.set(op, StateSucceeded, "", "rebooted into the previous version "+op.Version+"; the health gate commits it (OS updates screen)")
		return
	}
	// Still on the version being left (or something else): undo the flip, so nothing happens unasked.
	s.Roll.Cancel(context.Background())
	switch {
	case op.State == StateGoingDown && earlier:
		s.set(op, StateFailed, "not_rolled_back", fmt.Sprintf("the box restarted but runs %s, not the approved %s; the boot order was put back", orNone(running), op.Version))
	case earlier:
		s.set(op, StateFailed, "interrupted", "the box restarted before it went back (a power cut?); the boot order was put back")
	default:
		s.set(op, StateFailed, "interrupted", "the host service restarted before the box went back; the boot order was put back")
	}
}

// Resume settles what the last run left open, at start: an action that took
// the box down on an earlier boot succeeded; anything else left open was
// interrupted, and is reported failed rather than run again unasked.
func (s *Service) Resume() error {
	if s.Store == nil {
		return nil
	}
	all, err := s.Store.List()
	if err != nil {
		return err
	}
	for i := range all {
		op := all[i]
		if Terminal(op.State) {
			continue
		}
		earlier := op.BootID != s.BootID
		switch {
		case op.Kind == KindFactoryReset && earlier:
			// The journal lives on /data, which the wipe erases: a record that
			// survived a reboot means the box was not wiped.
			s.set(&op, StateFailed, "not_wiped", "the box restarted but was not wiped (the early-boot wipe did not run)")
		case op.Kind == KindOSRollback && s.Roll != nil:
			s.resumeRollback(&op, earlier)
		case op.State == StateGoingDown && earlier:
			msg := map[string]string{
				KindRestart:  "the box restarted",
				KindShutdown: "the box shut down (and has been started again)",
				KindOSInstall: "rebooted into " + op.Version +
					"; the health gate decides whether it is kept (OS updates screen)",
				KindOSRollback: "rebooted into the previous version " + op.Version +
					"; the health gate commits it (OS updates screen)",
			}[op.Kind]
			s.set(&op, StateSucceeded, "", msg)
		case earlier:
			s.set(&op, StateFailed, "interrupted", "the box restarted before this action finished (a power cut?)")
		default:
			s.set(&op, StateFailed, "interrupted", "the host service restarted before this action finished")
		}
	}
	return nil
}
