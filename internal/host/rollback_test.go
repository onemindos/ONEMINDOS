// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/update"
)

// raucJSON is `rauc status --output-format=json` of a box running bootedVer in slot A (or B) with
// otherVersion in the other slot, whose boot status is other.
func raucJSON(bootedA bool, other, otherVersion string) []byte {
	return raucJSONv("1.2.0", bootedA, other, otherVersion)
}

func raucJSONv(bootedVer string, bootedA bool, other, otherVersion string) []byte {
	slot := func(name, boot, state, status, ver string) string {
		return `{"` + name + `": {"class": "rootfs", "bootname": "` + boot + `", "state": "` + state + `", "boot_status": "` + status +
			`", "slot_status": {"bundle": {"version": "` + ver + `"}}}}`
	}
	efi := `{"efi.0": {"class": "efi", "bootname": "", "state": "inactive"}}`
	b := "A"
	booted := slot("rootfs.0", "A", "booted", "good", bootedVer)
	inactive := slot("rootfs.1", "B", "inactive", other, otherVersion)
	if !bootedA {
		b = "B"
		booted = slot("rootfs.1", "B", "booted", "good", bootedVer)
		inactive = slot("rootfs.0", "A", "inactive", other, otherVersion)
	}
	return []byte(`{"compatible": "onemind-vm", "booted": "` + b + `", "slots": [` + booted + `,` + inactive + `,` + efi + `]}`)
}

type rollbackBox struct {
	r     *SlotRollback
	conf  *update.Config
	calls []string
	json  []byte
	fail  string // a rauc subcommand that fails
}

func newRollbackBox(t *testing.T, version string) *rollbackBox {
	t.Helper()
	dir := t.TempDir()
	write := func(name, text string) {
		if err := os.MkdirAll(filepath.Dir(filepath.Join(dir, name)), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, name), []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("os-release", "ONEMIND_VERSION="+version+"\nONEMIND_BOARD=vm\n")
	write("system.conf", "compatible=onemind-vm\n")
	write("gate/.keep", "")
	conf := filepath.Join(dir, "update.conf")
	write("update.conf", strings.Join([]string{"channel = security", "url = https://example.org/tuf",
		"state_dir = " + dir + "/state", "gate_dir = " + dir + "/gate", "os_release = " + dir + "/os-release",
		"rauc_conf = " + dir + "/system.conf", ""}, "\n"))
	c, err := update.LoadConfig(conf)
	if err != nil {
		t.Fatal(err)
	}
	b := &rollbackBox{conf: c, json: raucJSON(true, "good", "1.1.0")}
	b.r = &SlotRollback{ConfigPath: conf, Run: func(_ context.Context, _ string, args ...string) ([]byte, error) {
		b.calls = append(b.calls, strings.Join(args, " "))
		if b.fail != "" && strings.Contains(strings.Join(args, " "), b.fail) {
			return nil, errors.New("rauc: boom")
		}
		if args[0] == "status" && len(args) > 2 && args[1] == "--detailed" && args[2] == "--output-format=json" {
			return b.json, nil
		}
		return nil, nil
	}}
	return b
}

func refusal(t *testing.T, err error, reason string) {
	t.Helper()
	var r *Refusal
	if !errors.As(err, &r) || r.Reason != reason {
		t.Fatalf("got %v, want refusal %s", err, reason)
	}
}

func TestPreviousSlotNeedsOneGoodKnownOtherVersion(t *testing.T) {
	got, rf := PreviousSlot(raucJSON(true, "good", "1.1.0"), "1.2.0", "")
	if rf != nil || got != (RollbackTarget{Bootname: "B", Version: "1.1.0"}) {
		t.Fatalf("slot A booted: %+v %v", got, rf)
	}
	got, rf = PreviousSlot(raucJSON(false, "good", "1.1.0"), "1.2.0", "")
	if rf != nil || got != (RollbackTarget{Bootname: "A", Version: "1.1.0"}) {
		t.Fatalf("slot B booted: %+v %v", got, rf)
	}
	for _, c := range []struct {
		name, reason string
		json         []byte
		running      string
	}{
		{"bad slot", "previous_not_good", raucJSON(true, "bad", "1.3.0"), "1.2.0"},
		{"no status", "previous_not_good", raucJSON(true, "", "1.1.0"), "1.2.0"},
		{"unknown version", "previous_unknown", raucJSON(true, "good", ""), "1.2.0"},
		{"same version", "same_version", raucJSON(true, "good", "1.2.0"), "1.2.0"},
		{"garbage", "no_previous_slot", []byte("not json"), "1.2.0"},
		{"no booted", "no_previous_slot", []byte(`{"slots": []}`), "1.2.0"},
	} {
		if _, rf := PreviousSlot(c.json, c.running, ""); rf == nil || rf.Reason != c.reason {
			t.Errorf("%s: got %v, want %s", c.name, rf, c.reason)
		}
	}
}

// A slot the image builder wrote has no record of its own in RAUC: its version is the one the update
// engine noted when it committed the update that replaced it.
func TestPreviousSlotFallsBackToTheEnginesNote(t *testing.T) {
	got, rf := PreviousSlot(raucJSON(true, "good", ""), "1.2.0", "1.1.0")
	if rf != nil || got != (RollbackTarget{Bootname: "B", Version: "1.1.0"}) {
		t.Fatalf("%+v %v", got, rf)
	}
	if _, rf := PreviousSlot(raucJSON(true, "good", ""), "1.2.0", ""); rf == nil || rf.Reason != "previous_unknown" {
		t.Fatalf("nothing known: %v", rf)
	}
	// RAUC's own record wins over the note.
	if got, _ := PreviousSlot(raucJSON(true, "good", "1.0.5"), "1.2.0", "1.1.0"); got.Version != "1.0.5" {
		t.Fatalf("%+v", got)
	}
	b := newRollbackBox(t, "1.2.0")
	b.json = raucJSON(true, "good", "")
	if why := b.r.RollbackUnavailable(); !strings.Contains(why, "no known OneMind version") {
		t.Fatalf("%q", why)
	}
	st := &update.Status{}
	st.State, st.PreviousVersion = "committed", "1.1.0"
	if err := st.Save(b.conf); err != nil {
		t.Fatal(err)
	}
	if err := b.r.Prepare(context.Background(), "1.1.0"); err != nil {
		t.Fatal(err)
	}
}

func TestRollbackMarksTheOtherSlotAndRemembersTheVersionItLeaves(t *testing.T) {
	b := newRollbackBox(t, "1.2.0")
	if why := b.r.RollbackUnavailable(); why != "" {
		t.Fatal(why)
	}
	if err := b.r.Prepare(context.Background(), "1.1.0"); err != nil {
		t.Fatal(err)
	}
	if last := b.calls[len(b.calls)-1]; last != "status mark-active other" {
		t.Fatalf("rauc calls %q", b.calls)
	}
	for _, c := range b.calls {
		if strings.HasPrefix(c, "install") {
			t.Fatalf("a rollback must never install: %q", b.calls)
		}
	}
	bad, err := update.ReadBadReleases(b.conf)
	if err != nil || bad.Verdict("1.2.0") == "" {
		t.Fatalf("1.2.0 not on the bad list: %v %v", bad, err)
	}
	// Reboot failed: the box stays where it is, and 1.2.0 is offered again.
	b.r.Cancel(context.Background())
	if last := b.calls[len(b.calls)-1]; last != "status mark-active booted" {
		t.Fatalf("cancel: %q", b.calls)
	}
	if bad, _ := update.ReadBadReleases(b.conf); bad.Verdict("1.2.0") != "" {
		t.Fatal("cancel left the version on the bad list")
	}
}

func TestRollbackRefusals(t *testing.T) {
	ctx := context.Background()
	b := newRollbackBox(t, "1.2.0")
	refusal(t, b.r.Prepare(ctx, "1.0.0"), "version_changed") // the approved version is no longer the previous one
	b.json = raucJSON(true, "bad", "1.1.0")
	refusal(t, b.r.Prepare(ctx, "1.1.0"), "previous_not_good")
	if why := b.r.RollbackUnavailable(); !strings.Contains(why, "not marked good") {
		t.Fatalf("%q", why)
	}
	for _, c := range b.calls {
		if strings.Contains(c, "mark-active") {
			t.Fatalf("a refused rollback touched the boot order: %q", b.calls)
		}
	}
	// An update waiting for the gate's verdict: the gate decides, not the owner.
	b = newRollbackBox(t, "1.2.0")
	if err := os.WriteFile(filepath.Join(b.conf.GateDir, "pending"), []byte("B 1.3.0\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	refusal(t, b.r.Prepare(ctx, "1.1.0"), "update_pending")
	// An install in progress.
	b = newRollbackBox(t, "1.2.0")
	st := &update.Status{}
	st.State = "installing"
	if err := st.Save(b.conf); err != nil {
		t.Fatal(err)
	}
	refusal(t, b.r.Prepare(ctx, "1.1.0"), "update_in_progress")
	// A failing rauc leaves nothing on the bad list.
	b = newRollbackBox(t, "1.2.0")
	b.fail = "mark-active other"
	if err := b.r.Prepare(ctx, "1.1.0"); err == nil {
		t.Fatal("rauc failed but Prepare said ok")
	}
	if bad, _ := update.ReadBadReleases(b.conf); bad.Verdict("1.2.0") != "" {
		t.Fatal("a failed rollback left the version on the bad list")
	}
	// Going back twice must not swap the slots and roll forward into the version just left.
	b = newRollbackBox(t, "1.2.0")
	if err := b.r.Prepare(ctx, "1.1.0"); err != nil {
		t.Fatal(err)
	}
	// After the reboot: slot B runs 1.1.0 and slot A still holds the 1.2.0 the box left.
	if err := os.WriteFile(filepath.Join(filepath.Dir(b.conf.OSRelease), "os-release"), []byte("ONEMIND_VERSION=1.1.0\nONEMIND_BOARD=vm\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	b.json = raucJSONv("1.1.0", false, "good", "1.2.0")
	refusal(t, b.r.Prepare(ctx, "1.2.0"), "previous_rolled_back")
	// Not an A/B image.
	none := &SlotRollback{ConfigPath: filepath.Join(t.TempDir(), "update.conf")}
	if why := none.RollbackUnavailable(); !strings.Contains(why, "not an A/B OneMind image") {
		t.Fatalf("%q", why)
	}
}

type fakeRoller struct {
	why       string
	prepared  []string
	cancelled int
	err       error
	holdErr   error         // Hold refuses
	holds     int           // Hold calls
	released  int           // release calls
	running   string        // RunningVersion
	preparedC chan struct{} // signalled by Prepare, when set
}

func (f *fakeRoller) Hold() (func(), error) {
	if f.holdErr != nil {
		return nil, f.holdErr
	}
	f.holds++
	return func() { f.released++ }, nil
}
func (f *fakeRoller) RunningVersion() string { return f.running }

func (f *fakeRoller) RollbackUnavailable() string { return f.why }
func (f *fakeRoller) Prepare(_ context.Context, v string) error {
	f.prepared = append(f.prepared, v)
	if f.preparedC != nil {
		f.preparedC <- struct{}{}
	}
	return f.err
}
func (f *fakeRoller) Cancel(context.Context) { f.cancelled++ }

func TestOSRollbackJournalsThenReboots(t *testing.T) {
	s, p := newService(t, t.TempDir(), "boot-1")
	roll := &fakeRoller{}
	s.Roll = roll
	op, created, err := s.Submit(context.Background(), Request{ActionID: "rb-1", Kind: KindOSRollback, Version: "1.1.0"})
	if err != nil || !created || op.State != StateAccepted {
		t.Fatalf("submit: %+v %v %v", op, created, err)
	}
	s.Wait()
	got, _ := s.Store.Get("rb-1")
	if got.State != StateGoingDown || p.reboots != 1 || len(roll.prepared) != 1 || roll.prepared[0] != "1.1.0" {
		t.Fatalf("op %+v reboots %d prepared %v", got, p.reboots, roll.prepared)
	}
	// The next boot settles the action as succeeded.
	s2 := &Service{Store: s.Store, BootID: "boot-2"}
	if err := s2.Resume(); err != nil {
		t.Fatal(err)
	}
	if done, _ := s.Store.Get("rb-1"); done.State != StateSucceeded || !strings.Contains(done.Message, "previous version 1.1.0") {
		t.Fatalf("after reboot: %+v", done)
	}
}

func TestOSRollbackRefusalsAndFailures(t *testing.T) {
	ctx := context.Background()
	s, p := newService(t, t.TempDir(), "b")
	// No roller: refused with a reason, never journaled.
	_, _, err := s.Submit(ctx, Request{ActionID: "n1", Kind: KindOSRollback, Version: "1.1.0"})
	refusal(t, err, "unavailable")
	if _, err := s.Store.Get("n1"); !errors.Is(err, ErrNotFound) {
		t.Fatal("a refused request was journaled")
	}
	// The slot is not bootable: refused before anything runs.
	s.Roll = &fakeRoller{why: "slot B is not marked good"}
	_, _, err = s.Submit(ctx, Request{ActionID: "n2", Kind: KindOSRollback, Version: "1.1.0"})
	refusal(t, err, "unavailable")
	// An update in progress.
	s.Roll = &fakeRoller{}
	s.OS = &fakeOS{busy: "an OS update is trial"}
	_, _, err = s.Submit(ctx, Request{ActionID: "n3", Kind: KindOSRollback, Version: "1.1.0"})
	refusal(t, err, "update_in_progress")
	s.OS = &fakeOS{}
	// The host's own check at run time wins over the approval: failed, no reboot.
	s.Roll = &fakeRoller{err: &Refusal{"version_changed", "the previous version is 1.0.0"}}
	if _, _, err := s.Submit(ctx, Request{ActionID: "n4", Kind: KindOSRollback, Version: "1.1.0"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if op, _ := s.Store.Get("n4"); op.State != StateFailed || op.Reason != "version_changed" || p.reboots != 0 {
		t.Fatalf("%+v reboots %d", op, p.reboots)
	}
	// A reboot that fails puts the boot order back.
	roll := &fakeRoller{}
	s.Roll, p.err = roll, errors.New("no systemd")
	if _, _, err := s.Submit(ctx, Request{ActionID: "n5", Kind: KindOSRollback, Version: "1.1.0"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if op, _ := s.Store.Get("n5"); op.State != StateFailed || roll.cancelled != 1 {
		t.Fatalf("%+v cancelled %d", op, roll.cancelled)
	}
	// The update engine is mid-cycle: refused before anything changes.
	s.Roll = &fakeRoller{holdErr: &Refusal{"engine_busy", "the update service is in the middle of a cycle"}}
	if _, _, err := s.Submit(ctx, Request{ActionID: "n6", Kind: KindOSRollback, Version: "1.1.0"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if op, _ := s.Store.Get("n6"); op.State != StateFailed || op.Reason != "engine_busy" {
		t.Fatalf("%+v", op)
	}
	for _, bad := range []Request{
		{ActionID: "ok", Kind: KindOSRollback},
		{ActionID: "ok", Kind: KindOSRollback, Version: "1.0; rm -rf /"},
		{ActionID: "ok", Kind: KindOSRollback, Version: "1.1.0", PlanSHA256: strings.Repeat("a", 64)},
	} {
		if bad.Validate() == nil {
			t.Errorf("accepted malformed %+v", bad)
		}
	}
	_ = time.Second
}

func TestOSRollbackHoldsTheEngineLockUntilTheBoxIsDown(t *testing.T) {
	ctx := context.Background()
	s, p := newService(t, t.TempDir(), "b")
	roll := &fakeRoller{}
	s.Roll = roll
	if _, _, err := s.Submit(ctx, Request{ActionID: "h1", Kind: KindOSRollback, Version: "1.1.0"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	// Going down: the lock stays held (the process ends with the box).
	if roll.holds != 1 || roll.released != 0 || p.reboots != 1 {
		t.Fatalf("holds %d released %d reboots %d", roll.holds, roll.released, p.reboots)
	}
	// A failed reboot or a refused Prepare lets go of it.
	roll2 := &fakeRoller{err: &Refusal{"version_changed", "x"}}
	s, _ = newService(t, t.TempDir(), "b")
	s.Roll = roll2
	if _, _, err := s.Submit(ctx, Request{ActionID: "h2", Kind: KindOSRollback, Version: "1.1.0"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if roll2.holds != 1 || roll2.released != 1 {
		t.Fatalf("holds %d released %d", roll2.holds, roll2.released)
	}
}

// The service stops during the delay: Prepare already flipped the boot order, so it is put back.
func TestOSRollbackStoppedDuringTheDelayPutsTheBootOrderBack(t *testing.T) {
	s, p := newService(t, t.TempDir(), "b")
	s.Delay = time.Hour
	roll := &fakeRoller{preparedC: make(chan struct{}, 1)}
	s.Roll = roll
	ctx, cancel := context.WithCancel(context.Background())
	if _, _, err := s.Submit(ctx, Request{ActionID: "c1", Kind: KindOSRollback, Version: "1.1.0"}); err != nil {
		t.Fatal(err)
	}
	<-roll.preparedC // Prepare ran: the boot order is flipped
	cancel()
	s.Wait()
	op, _ := s.Store.Get("c1")
	if op.State != StateFailed || op.Reason != "interrupted" || roll.cancelled != 1 || roll.released != 1 || p.reboots != 0 {
		t.Fatalf("%+v cancelled %d released %d reboots %d", op, roll.cancelled, roll.released, p.reboots)
	}
}

func TestResumeSettlesARollbackOnlyWhenTheBoxWentBack(t *testing.T) {
	open := func(dir string, op Op) *Store {
		st, err := OpenStore(dir)
		if err != nil {
			t.Fatal(err)
		}
		if err := st.Put(op); err != nil {
			t.Fatal(err)
		}
		return st
	}
	base := Op{ID: "r", Kind: KindOSRollback, Version: "1.1.0", BootID: "boot-1"}
	for _, c := range []struct {
		name, state, boot, running, want, reason string
		cancelled                                int
	}{
		{"went back", StateGoingDown, "boot-2", "1.1.0", StateSucceeded, "", 0},
		{"rebooted but still the old version", StateGoingDown, "boot-2", "1.2.0", StateFailed, "not_rolled_back", 1},
		{"power cut before the reboot", StateRunning, "boot-2", "1.2.0", StateFailed, "interrupted", 1},
		{"power cut, box did go back", StateRunning, "boot-2", "1.1.0", StateSucceeded, "", 0},
		{"host restarted on the same boot", StateRunning, "boot-1", "1.2.0", StateFailed, "interrupted", 1},
	} {
		t.Run(c.name, func(t *testing.T) {
			op := base
			op.State = c.state
			roll := &fakeRoller{running: c.running}
			s := &Service{Store: open(t.TempDir(), op), BootID: c.boot, Roll: roll}
			if err := s.Resume(); err != nil {
				t.Fatal(err)
			}
			got, _ := s.Store.Get("r")
			if got.State != c.want || got.Reason != c.reason || roll.cancelled != c.cancelled {
				t.Fatalf("%+v cancelled %d", got, roll.cancelled)
			}
		})
	}
}

func TestSlotRollbackHoldTakesTheEngineLock(t *testing.T) {
	b := newRollbackBox(t, "1.2.0")
	release, err := b.r.Hold()
	if err != nil {
		t.Fatal(err)
	}
	// While held, an engine run (the update timer's) cannot start.
	if _, err := update.Lock(b.conf); !errors.Is(err, update.ErrBusy) {
		t.Fatalf("engine lock not held: %v", err)
	}
	refusal(t, func() error { _, err := b.r.Hold(); return err }(), "engine_busy")
	release()
	unlock, err := update.Lock(b.conf)
	if err != nil {
		t.Fatalf("not released: %v", err)
	}
	unlock()
	if v := b.r.RunningVersion(); v != "1.2.0" {
		t.Fatalf("running %q", v)
	}
}
