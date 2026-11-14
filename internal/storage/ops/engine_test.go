// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
)

// box simulates the parts of a machine the engine touches: disks with one
// partition each, a btrfs set, a kernel balance, dm-crypt mappings. Commands
// mutate it; Facts read it. A "power cut" cancels the engine's context while
// a chosen command runs, before or after its effect.
type box struct {
	mu       sync.Mutex
	disks    map[string]*fdisk
	members  []string // devid = index+1; "" = missing
	profiles map[string]string
	balance  string // "", "running", "paused"
	pending  map[string]string
	polls    int
	mapped   map[string]string
	log      []string
	cutOn    string // command substring that cuts power
	cutAfter bool   // apply the command's effect before the cut
	cutBal   string // a cut during "balance start" leaves the kernel balance in this state
	fail     map[string]int
	cancel   context.CancelFunc
	// lastReplace: btrfs replace status keeps reporting the last replace
	// ever run ("finished"), which the lab found the engine trusting.
	lastReplace string
	ids         map[string]string // stable disk ids (WWN, serial); default the path
}

type fdisk struct {
	size     uint64
	part     string
	partuuid string
}

func newBox() *box {
	return &box{
		disks: map[string]*fdisk{
			"/dev/vdb": {size: 4 << 30, part: "/dev/vdb1", partuuid: "aaaaaaaa-0000-4000-8000-000000000001"},
			"/dev/vdc": {size: 4 << 30},
			"/dev/vdd": {size: 4 << 30},
		},
		members:  []string{"/dev/vdb1"},
		profiles: map[string]string{"Data": "single", "Metadata": "dup", "System": "dup"},
		mapped:   map[string]string{},
		fail:     map[string]int{},
	}
}

func (b *box) Mirror(_ context.Context, mount string) (*storage.Mirror, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	m := &storage.Mirror{Mount: mount, UUID: "5e7a0000-0000-4000-8000-0000000000aa", Label: "onemind-data"}
	for i, p := range b.members {
		m.Members = append(m.Members, storage.Member{DevID: i + 1, Path: p, Missing: p == "", SizeBytes: 4 << 30, UsedBytes: 1 << 30, Errors: map[string]int64{}})
	}
	for _, k := range []string{"Data", "Metadata", "System"} {
		m.Profiles = append(m.Profiles, storage.Profile{Kind: k, Profile: b.profiles[k]})
	}
	storage.Evaluate(m)
	return m, nil
}

func (b *box) Disks(_ context.Context, m *storage.Mirror) ([]storage.Disk, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := []storage.Disk{{Path: "/dev/vda", ID: "/dev/vda", SizeBytes: 12 << 30, Role: storage.RoleSystem,
		Holds: []storage.Signature{{Path: "/dev/vda1", Type: "part", Mountpoints: []string{"/"}}}}}
	for _, path := range []string{"/dev/vdb", "/dev/vdc", "/dev/vdd", "/dev/vde", "/dev/vdf"} {
		d := b.disks[path]
		if d == nil {
			continue
		}
		disk := storage.Disk{Path: path, ID: path, SizeBytes: d.size, Role: storage.RoleUnused}
		if id := b.ids[path]; id != "" {
			disk.ID = id
		}
		if d.part != "" {
			disk.Role = storage.RoleHasData
			disk.Holds = append(disk.Holds, storage.Signature{Path: d.part, Type: "part", Parent: path, PartUUID: d.partuuid, FSType: "btrfs"})
			for name, part := range b.mapped {
				if part == d.part {
					disk.Holds = append(disk.Holds, storage.Signature{Path: "/dev/mapper/" + name, Type: "crypt", Parent: d.part})
				}
			}
			for _, mem := range b.members {
				if mem == d.part {
					disk.Role = storage.RoleMember
				}
			}
		}
		out = append(out, disk)
	}
	return out, nil
}

func (b *box) Health(context.Context, storage.Disk) (storage.Health, error) {
	return storage.Health{Verdict: storage.VerdictUnknown}, nil
}

func arg(args []string, prefix string) string {
	for _, a := range args {
		if v, ok := strings.CutPrefix(a, prefix); ok {
			return v
		}
	}
	return ""
}

func (b *box) Exec(ctx context.Context, stdin, name string, args ...string) ([]byte, int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	line := name + " " + strings.Join(args, " ")
	b.log = append(b.log, line)
	cut := b.cutOn != "" && strings.Contains(line, b.cutOn)
	if cut && !b.cutAfter && b.cutBal == "" {
		b.cutOn = ""
		b.cancel()
		return nil, -1, context.Canceled
	}
	for k, code := range b.fail {
		if strings.Contains(line, k) {
			return []byte("simulated failure"), code, nil
		}
	}
	out, code := b.apply(name, args)
	if cut {
		b.cutOn = ""
		b.cancel()
		return nil, -1, context.Canceled
	}
	return []byte(out), code, nil
}

func (b *box) apply(name string, args []string) (string, int) {
	last := args[len(args)-1]
	switch {
	case name == "sgdisk" && args[0] == "--zap-all":
		if d := b.disks[last]; d != nil {
			d.part, d.partuuid = "", ""
		}
	case name == "sgdisk":
		d := b.disks[last]
		if d == nil {
			return "no such disk", 2
		}
		if d.part != "" {
			return "partition exists", 4
		}
		d.part, d.partuuid = last+"1", arg(args, "--partition-guid=1:")
	case name == "btrfs" && args[0] == "device" && args[1] == "add":
		b.members = append(b.members, args[2])
	case name == "btrfs" && args[0] == "device" && args[1] == "remove":
		for i, mem := range b.members {
			if fmt.Sprint(i+1) == args[2] || mem == args[2] {
				b.members = append(b.members[:i], b.members[i+1:]...)
				break
			}
		}
	case name == "btrfs" && args[0] == "balance" && args[1] == "status":
		switch b.balance {
		case "running":
			if b.polls++; b.polls >= 3 { // the kernel finishes on its own
				b.convert(b.pending)
				b.balance = ""
			}
			return "Balance on '/data' is running", 1
		case "paused":
			return "Balance on '/data' is paused", 1
		}
		return "No balance found on '/data'", 0
	case name == "btrfs" && args[0] == "balance" && args[1] == "resume":
		b.convert(b.pending)
		b.balance = ""
	case name == "btrfs" && args[0] == "balance" && args[1] == "start":
		conv := map[string]string{"Data": arg(args, "-dconvert="), "Metadata": arg(args, "-mconvert="), "System": arg(args, "-mconvert=")}
		if b.cutBal != "" && b.cutOn != "" && strings.Contains("btrfs balance start", b.cutOn) {
			b.balance, b.pending, b.cutBal = b.cutBal, conv, ""
			return "", 0
		}
		b.convert(conv)
	case name == "btrfs" && args[0] == "filesystem" && args[1] == "df":
		var sb strings.Builder
		for _, k := range []string{"Data", "Metadata", "System"} {
			fmt.Fprintf(&sb, "%s, %s: total=1, used=1\n", k, strings.ToUpper(b.profiles[k]))
		}
		return sb.String(), 0
	case name == "btrfs" && args[0] == "replace" && args[1] == "status":
		if b.lastReplace != "" {
			return "Started on 12.Nov 05:23:35, finished on 12.Nov 05:23:37, 0 write errs, 0 uncorr. read errs", 0
		}
		return "Never started", 0
	case name == "btrfs" && args[0] == "replace" && args[1] == "start":
		var devid int
		fmt.Sscan(args[len(args)-3], &devid)
		b.members[devid-1] = args[len(args)-2]
		b.lastReplace = args[len(args)-2]
	case name == "cryptsetup" && args[0] == "status":
		if _, ok := b.mapped[last]; ok {
			return last + " is active", 0
		}
		return last + " is inactive", 4
	case name == "cryptsetup" && args[0] == "open":
		b.mapped[last] = args[len(args)-2]
	case name == "cryptsetup" && args[0] == "close":
		delete(b.mapped, strings.TrimPrefix(last, "/dev/mapper/"))
	}
	return "", 0
}

func (b *box) convert(c map[string]string) {
	for k, v := range c {
		if v != "" {
			b.profiles[k] = strings.TrimSuffix(v, ",soft")
		}
	}
}

func (b *box) ran(sub string) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	for _, l := range b.log {
		if strings.Contains(l, sub) {
			return true
		}
	}
	return false
}

func newEngine(t *testing.T, b *box, dir string) *Engine {
	t.Helper()
	st, err := OpenStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	b.mu.Lock()
	b.cancel = cancel
	b.mu.Unlock()
	t.Cleanup(func() { cancel(); st.Close() })
	return &Engine{Facts: b, Run: b, Store: st, Mount: "/data", Context: ctx, Poll: time.Millisecond,
		Log: slog.New(slog.NewTextHandler(io.Discard, nil))}
}

// powerCut stops the engine as a power cut would and releases the journal.
func powerCut(e *Engine) {
	e.Wait()
	e.Store.Close()
}

func approved(t *testing.T, e *Engine, req Request) Request {
	t.Helper()
	p, err := e.Plan(context.Background(), req)
	if err != nil || p.Blocked {
		t.Fatalf("plan: %v %+v", err, p.Checks)
	}
	req.PlanSHA256 = p.SHA256
	return req
}

func finished(t *testing.T, e *Engine, id string) *Op {
	t.Helper()
	e.Wait()
	op, err := e.Get(id)
	if err != nil {
		t.Fatal(err)
	}
	return op
}

func TestCreateMirrorRunsEveryStep(t *testing.T) {
	b := newBox()
	e := newEngine(t, b, t.TempDir())
	op, err := e.Start(context.Background(), approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "a1"}))
	if err != nil {
		t.Fatal(err)
	}
	op = finished(t, e, op.ID)
	if op.State != StateSucceeded || op.Next != len(op.Steps) {
		t.Fatalf("%s: %s", op.State, op.Error)
	}
	if len(b.members) != 2 || b.profiles["Data"] != "raid1" || b.profiles["Metadata"] != "raid1" {
		t.Errorf("box: %v %v", b.members, b.profiles)
	}
	if again, err := e.Start(context.Background(), Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "a1"}); err != nil || again.State != StateSucceeded {
		t.Errorf("same action id must replay the operation: %v %v", again, err)
	}
	if len(op.Targets) != 1 || op.Targets[0].PartUUID == "" || op.Refs["/dev/vdc"].Kind != "disk" {
		t.Errorf("targets %+v refs %+v", op.Targets, op.Refs)
	}
}

func TestRefusals(t *testing.T) {
	b := newBox()
	e := newEngine(t, b, t.TempDir())
	ctx := context.Background()
	if _, err := e.Start(ctx, Request{Kind: KindCreate, Device: "/dev/vdc"}); !errors.Is(err, ErrNoPlanSHA) {
		t.Errorf("no sha: %v", err)
	}
	var pe *PlanError
	if _, err := e.Start(ctx, Request{Kind: KindCreate, Device: "/dev/vdc", PlanSHA256: "00"}); !errors.As(err, &pe) || pe.Code != "stale_precondition" {
		t.Errorf("stale: %v", err)
	}
	// Approved for vdc, but the request names vdd: a different plan.
	req := approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdc"})
	req.Device = "/dev/vdd"
	if _, err := e.Start(ctx, req); !errors.As(err, &pe) || pe.Code != "stale_precondition" {
		t.Errorf("other disk: %v", err)
	}
	if _, err := e.Start(ctx, Request{Kind: KindCreate, Device: "/dev/vdb", PlanSHA256: "x"}); !errors.As(err, &pe) || pe.Code != "blocked" {
		t.Errorf("member as target: %v", err)
	}
	if _, err := e.Start(ctx, Request{Kind: KindAdd, Device: "/dev/vdc", PlanSHA256: "x"}); !errors.As(err, &pe) || pe.Code != "blocked" {
		t.Errorf("add on one disk: %v", err)
	}
	// A second operation while one runs.
	b.mu.Lock()
	b.balance, b.pending, b.polls = "running", map[string]string{}, -1_000_000
	b.mu.Unlock()
	if _, err := e.Start(ctx, approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "busy1"})); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Start(ctx, approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdd"})); !errors.Is(err, ErrBusy) {
		t.Errorf("second operation: %v", err)
	}
	b.mu.Lock()
	b.polls = 10
	b.mu.Unlock()
	if op := finished(t, e, "busy1"); op.State != StateSucceeded {
		t.Errorf("%s %s", op.State, op.Error)
	}
}

func TestPowerCutDuringBalanceResumes(t *testing.T) {
	for _, kernel := range []string{"running", "paused"} {
		t.Run(kernel, func(t *testing.T) {
			b, dir := newBox(), t.TempDir()
			e := newEngine(t, b, dir)
			b.cutOn, b.cutBal = "btrfs balance start", kernel
			if _, err := e.Start(context.Background(), approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "cut1"})); err != nil {
				t.Fatal(err)
			}
			powerCut(e)
			op, _ := e.Store.Load("cut1")
			if op.State != StateRunning || op.Plan.Steps[op.Next].ID != "balance" || op.Steps[op.Next].State != StepRunning {
				t.Fatalf("journal after the cut: %s next=%d", op.State, op.Next)
			}
			e2 := newEngine(t, b, dir) // the box boots again
			if err := e2.Resume(context.Background()); err != nil {
				t.Fatal(err)
			}
			op = finished(t, e2, "cut1")
			if op.State != StateSucceeded || op.Resumes != 1 || b.profiles["Data"] != "raid1" {
				t.Fatalf("%s %s %v", op.State, op.Error, b.profiles)
			}
			for i, s := range op.Plan.Steps {
				if s.ID == "balance" && !strings.Contains(op.Steps[i].Note, "balance") {
					t.Errorf("balance note %q", op.Steps[i].Note)
				}
			}
		})
	}
}

func TestPowerCutAfterDeviceAddSkipsIt(t *testing.T) {
	b, dir := newBox(), t.TempDir()
	e := newEngine(t, b, dir)
	b.cutOn, b.cutAfter = "btrfs device add", true
	if _, err := e.Start(context.Background(), approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "cut2"})); err != nil {
		t.Fatal(err)
	}
	powerCut(e)
	e2 := newEngine(t, b, dir)
	_ = e2.Resume(context.Background())
	op := finished(t, e2, "cut2")
	if op.State != StateSucceeded || len(b.members) != 2 {
		t.Fatalf("%s %s members=%v", op.State, op.Error, b.members)
	}
	for i, s := range op.Plan.Steps {
		if s.ID == "device-add" && op.Steps[i].State != StepSkipped {
			t.Errorf("device-add %s: the disk was added before the cut and must not be added twice", op.Steps[i].State)
		}
	}
}

func TestPowerCutInPrepareWithRenamedDisks(t *testing.T) {
	b, dir := newBox(), t.TempDir()
	e := newEngine(t, b, dir)
	b.cutOn, b.cutAfter = "udevadm settle", true
	if _, err := e.Start(context.Background(), approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "cut3"})); err != nil {
		t.Fatal(err)
	}
	powerCut(e)
	// The box boots and the kernel hands out the names the other way round.
	b.mu.Lock()
	b.disks["/dev/vdc"], b.disks["/dev/vdd"] = b.disks["/dev/vdd"], b.disks["/dev/vdc"]
	b.disks["/dev/vdd"].part = "/dev/vdd1"
	b.log = nil
	b.mu.Unlock()
	e2 := newEngine(t, b, dir)
	_ = e2.Resume(context.Background())
	op := finished(t, e2, "cut3")
	if op.State != StateSucceeded {
		t.Fatalf("%s %s", op.State, op.Error)
	}
	if len(op.Relocated) == 0 || b.members[1] != "/dev/vdd1" {
		t.Errorf("relocated %v members %v", op.Relocated, b.members)
	}
	if b.ran("/dev/vdc") {
		t.Errorf("touched the other disk after the reboot:\n%s", strings.Join(b.log, "\n"))
	}
	if !b.ran("sgdisk --zap-all /dev/vdd") {
		t.Error("prepare phase not restarted on the target")
	}
}

func TestFailureBeforeCommitRollsBack(t *testing.T) {
	b := newBox()
	e := newEngine(t, b, t.TempDir())
	b.fail["btrfs balance start"] = 1
	// Fail at balance (commit): forward-only, the disk stays in the set.
	op, _ := e.Start(context.Background(), approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "f1"}))
	if op = finished(t, e, op.ID); op.State != StateFailed || len(b.members) != 2 {
		t.Fatalf("commit failure: %s members=%v", op.State, b.members)
	}

	// Fail at the join step (device add): nothing moved, so it rolls back.
	b2 := newBox()
	e2 := newEngine(t, b2, t.TempDir())
	b2.fail["btrfs device add"] = 1
	op, _ = e2.Start(context.Background(), approved(t, e2, Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "f2"}))
	op = finished(t, e2, op.ID)
	if op.State != StateRolledBack || len(b2.members) != 1 || b2.disks["/dev/vdc"].part != "" {
		t.Fatalf("join failure: %s %s members=%v part=%q", op.State, op.Error, b2.members, b2.disks["/dev/vdc"].part)
	}
	if len(op.Rollback) == 0 || !strings.Contains(op.Error, "device-add") {
		t.Errorf("rollback record %+v error %q", op.Rollback, op.Error)
	}
}

func TestTargetGoneAfterRebootRollsBack(t *testing.T) {
	b, dir := newBox(), t.TempDir()
	e := newEngine(t, b, dir)
	b.cutOn, b.cutAfter = "udevadm settle", true
	if _, err := e.Start(context.Background(), approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdc", ActionID: "gone"})); err != nil {
		t.Fatal(err)
	}
	powerCut(e)
	b.mu.Lock()
	delete(b.disks, "/dev/vdc") // unplugged while the box was off
	b.mu.Unlock()
	e2 := newEngine(t, b, dir)
	_ = e2.Resume(context.Background())
	op := finished(t, e2, "gone")
	if op.State != StateRolledBack || !strings.Contains(op.Error, "not found any more") || len(b.members) != 1 {
		t.Fatalf("%s %q %v", op.State, op.Error, b.members)
	}
}

func TestRemoveAndReplaceRun(t *testing.T) {
	b := newBox()
	b.members = []string{"/dev/vdb1", "/dev/vdc1"}
	b.disks["/dev/vdc"].part, b.disks["/dev/vdc"].partuuid = "/dev/vdc1", "aaaaaaaa-0000-4000-8000-000000000002"
	b.profiles = map[string]string{"Data": "raid1", "Metadata": "raid1", "System": "raid1"}
	e := newEngine(t, b, t.TempDir())
	op, err := e.Start(context.Background(), approved(t, e, Request{Kind: KindReplace, Member: "2", Device: "/dev/vdd", ActionID: "r1"}))
	if err != nil {
		t.Fatal(err)
	}
	if op = finished(t, e, op.ID); op.State != StateSucceeded || !b.ran("btrfs replace start -B -f 2 /dev/vdd1 /data") {
		t.Fatalf("replace: %s %s", op.State, op.Error)
	}
	// A second replace on the same filesystem: the status still says the
	// first one "finished"; the engine must run the new one anyway.
	b.disks["/dev/vde"] = &fdisk{size: 4 << 30}
	op, err = e.Start(context.Background(), approved(t, e, Request{Kind: KindReplace, Member: "2", Device: "/dev/vde", ActionID: "r2"}))
	if err != nil {
		t.Fatal(err)
	}
	if op = finished(t, e, op.ID); op.State != StateSucceeded || b.members[1] != "/dev/vde1" {
		t.Fatalf("second replace: %s %s members=%v", op.State, op.Error, b.members)
	}
	// A replace that fails before the new disk takes the devid rolls back.
	b.disks["/dev/vdf"] = &fdisk{size: 4 << 30}
	b.fail["btrfs replace start"] = 1
	op, _ = e.Start(context.Background(), approved(t, e, Request{Kind: KindReplace, Member: "2", Device: "/dev/vdf", ActionID: "r3"}))
	if op = finished(t, e, op.ID); op.State != StateRolledBack || b.disks["/dev/vdf"].part != "" || b.members[1] != "/dev/vde1" {
		t.Fatalf("failed replace: %s %s part=%q members=%v", op.State, op.Error, b.disks["/dev/vdf"].part, b.members)
	}
	delete(b.fail, "btrfs replace start")
	if _, err := e.Start(context.Background(), Request{Kind: KindRemove, Member: "2", PlanSHA256: "x"}); err == nil {
		t.Error("remove to one member without unprotect must be refused")
	}
	op, err = e.Start(context.Background(), approved(t, e, Request{Kind: KindRemove, Member: "2", Unprotect: true, ActionID: "rm1"}))
	if err != nil {
		t.Fatal(err)
	}
	if op = finished(t, e, op.ID); op.State != StateSucceeded || len(b.members) != 1 || b.profiles["Data"] != "single" {
		t.Fatalf("remove: %s %s %v %v", op.State, op.Error, b.members, b.profiles)
	}
}

// The lab race (log 19): after a power cut the kernel resumes the replace at
// mount; the status text reads "finished" while the kernel still holds the
// replace lock, a second start fails, and only then does the devid move.
func TestResumedReplaceRaceCompletes(t *testing.T) {
	b := newBox()
	b.members = []string{"/dev/vdb1", "/dev/vdc1"}
	b.disks["/dev/vdc"].part, b.disks["/dev/vdc"].partuuid = "/dev/vdc1", "aaaaaaaa-0000-4000-8000-000000000002"
	b.profiles = map[string]string{"Data": "raid1", "Metadata": "raid1", "System": "raid1"}
	b.lastReplace = "earlier"
	e := newEngine(t, b, t.TempDir())
	req := approved(t, e, Request{Kind: KindReplace, Member: "2", Device: "/dev/vdd", ActionID: "race"})
	calls := 0
	e.Exclusive = func(string) string {
		calls++
		if calls == 3 { // the kernel finishes its resumed replace
			b.mu.Lock()
			b.members[1] = "/dev/vdd1"
			b.mu.Unlock()
		}
		if calls <= 3 {
			return "device replace"
		}
		return "none"
	}
	b.fail["btrfs replace start"] = 1 // "another exclusive operation in progress"
	op, err := e.Start(context.Background(), req)
	if err != nil {
		t.Fatal(err)
	}
	op = finished(t, e, op.ID)
	if op.State != StateSucceeded || b.members[1] != "/dev/vdd1" {
		t.Fatalf("%s %s members=%v", op.State, op.Error, b.members)
	}
}

func TestVerifyCatchesWrongProfile(t *testing.T) {
	if msg := verifyProfiles([]byte("Data, single: total=1, used=1\nMetadata, RAID1: total=1, used=1\nSystem, RAID1: total=1, used=1\nGlobalReserve, single: total=1, used=0\n"),
		storage.Plan{DataProfile: "raid1", MetaProfile: "raid1"}); !strings.Contains(msg, "Data is single") {
		t.Errorf("%q", msg)
	}
	if msg := verifyProfiles([]byte("Data, RAID1: total=1, used=1\nMetadata, RAID1C3: total=1, used=1\nSystem, RAID1C3: total=1, used=1\n"),
		storage.Plan{DataProfile: "raid1", MetaProfile: "raid1c3"}); msg != "" {
		t.Error(msg)
	}
}

func TestStoreLockAndIDs(t *testing.T) {
	dir := t.TempDir()
	s, err := OpenStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	if _, err := OpenStore(dir); err == nil {
		t.Error("second store on the same journal must fail")
	}
	if err := s.Save(&Op{ID: "../escape"}); err == nil {
		t.Error("path traversal id accepted")
	}
	if _, err := s.Load("../../etc/passwd"); !errors.Is(err, ErrNotFound) {
		t.Error(err)
	}
	if err := s.Save(&Op{ID: "x1", State: StateSucceeded}); err != nil {
		t.Fatal(err)
	}
	if ents, _ := os.ReadDir(dir); len(ents) != 2 { // lock + op-x1.json, no temp files left
		t.Errorf("%d files", len(ents))
	}
}

func TestServerAPI(t *testing.T) {
	b := newBox()
	e := newEngine(t, b, t.TempDir())
	keyFile := filepath.Join(t.TempDir(), "recovery-key")
	os.WriteFile(keyFile, []byte("cbdefghi-jklnrtuv"), 0o600)
	srv := httptest.NewServer((&Server{E: e, RecoveryKeyFile: keyFile, AllowUID: -1, AllowGID: -1}).Handler())
	defer srv.Close()
	post := func(path, body string) (int, map[string]any) {
		resp, err := http.Post(srv.URL+path, "application/json", strings.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		var m map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&m)
		return resp.StatusCode, m
	}
	code, plan := post("/v1/plans", `{"kind":"create","device":"/dev/vdc"}`)
	if code != 200 || plan["blocked"] != false {
		t.Fatalf("%d %v", code, plan)
	}
	if code, body := post("/v1/operations", `{"kind":"create","device":"/dev/vdc","plan_sha256":"bad","action_id":"s1"}`); code != 409 || body["reason"] != "plan_changed" {
		t.Errorf("%d %v", code, body)
	}
	if code, _ := post("/v1/operations", `{"kind":"create","device":"/dev/vdc","sneaky":1}`); code != 400 {
		t.Errorf("unknown field: %d", code)
	}
	code, body := post("/v1/operations", fmt.Sprintf(`{"kind":"create","device":"/dev/vdc","plan_sha256":%q,"action_id":"s1"}`, plan["plan_sha256"]))
	if code != 202 || body["id"] != "s1" {
		t.Fatalf("%d %v", code, body)
	}
	e.Wait()
	resp, _ := http.Get(srv.URL + "/v1/operations/s1")
	var op Op
	_ = json.NewDecoder(resp.Body).Decode(&op)
	resp.Body.Close()
	if op.State != StateSucceeded {
		t.Errorf("%+v", op)
	}
	if resp, _ := http.Get(srv.URL + "/v1/operations/nope"); resp.StatusCode != 404 {
		t.Errorf("unknown op: %d", resp.StatusCode)
	}
	resp, _ = http.Get(srv.URL + "/v1/status")
	var st Status
	_ = json.NewDecoder(resp.Body).Decode(&st)
	resp.Body.Close()
	if st.Mirror == nil || st.Mirror.State != storage.StateProtected || !st.RecoveryKeyPending || !st.Journal {
		t.Errorf("status %+v", st)
	}
	if code, body := post("/v1/recovery-key/take", ``); code != 200 || body["recovery_key"] != "cbdefghi-jklnrtuv" {
		t.Errorf("take: %d %v", code, body)
	}
	if code, _ := post("/v1/recovery-key/take", ``); code != 404 {
		t.Errorf("second take must find nothing: %d", code)
	}
	if _, err := os.Stat(keyFile); !errors.Is(err, os.ErrNotExist) {
		t.Error("recovery key file not removed")
	}
}

// Two disks behind cheap USB bridges can report the same serial. A rollback
// or a resumed step must never pick the other one by that id.
func TestDuplicateSerialNeverWipesTheOtherDisk(t *testing.T) {
	b := newBox()
	b.disks["/dev/vdc"] = &fdisk{size: 4 << 30, part: "/dev/vdc1", partuuid: "cccccccc-0000-4000-8000-00000000000c"}
	b.ids = map[string]string{"/dev/vdc": "SAME-SERIAL", "/dev/vdd": "SAME-SERIAL"}
	e := newEngine(t, b, t.TempDir())
	b.fail["sgdisk --new"] = 1 // the target's partition step fails: rollback
	op, err := e.Start(context.Background(), approved(t, e, Request{Kind: KindCreate, Device: "/dev/vdd", ActionID: "dup"}))
	if err != nil {
		t.Fatal(err)
	}
	op = finished(t, e, op.ID)
	if b.ran("--zap-all /dev/vdc") || b.disks["/dev/vdc"].part == "" {
		t.Fatalf("rollback wiped /dev/vdc, which only shares the target's serial: %s %q", op.State, op.Error)
	}
	if op.State != StateRolledBack {
		t.Errorf("nothing of ours is on any disk: want rolled_back, got %s %q", op.State, op.Error)
	}

	// The ref of a whole-disk path does not resolve to an ambiguous id.
	disks, _ := b.Disks(context.Background(), nil)
	if p, ok := resolveRef(disks, Ref{Kind: "disk-id", Key: "SAME-SERIAL"}); ok {
		t.Errorf("ambiguous disk id resolved to %s", p)
	}
}

// A target matched only by its (unique) stable id is blanked only when what
// it holds can be ours: partitions udev has not given an id yet.
func TestRollbackByDiskIDOnlyBlanksWhatCanBeOurs(t *testing.T) {
	disks := []storage.Disk{{Path: "/dev/vdx", ID: "SER-X", SizeBytes: 4 << 30, Role: storage.RoleHasData,
		Holds: []storage.Signature{{Path: "/dev/vdx1", Type: "part", PartUUID: "dddddddd-0000-4000-8000-00000000000d", FSType: "ext4"}}}}
	tg := Target{Path: "/dev/vdx", Part: "/dev/vdx1", DiskID: "SER-X", PartUUID: "aaaaaaaa-0000-4000-8000-00000000000a", Size: 4 << 30}
	if _, ok, why := targetByID(disks, tg); ok || why == "" {
		t.Errorf("a disk holding another partition id must not count as the target (ok=%t why=%q)", ok, why)
	}
	disks[0].Holds[0].PartUUID, disks[0].Holds[0].FSType = "", ""
	if d, ok, why := targetByID(disks, tg); !ok || d.Path != "/dev/vdx" {
		t.Errorf("a partition without an id yet is ours to blank: ok=%t why=%q", ok, why)
	}
	disks[0].Role, disks[0].Holds = storage.RoleUnused, nil
	if _, ok, why := targetByID(disks, tg); ok || why != "" {
		t.Errorf("a blank disk needs nothing: ok=%t why=%q", ok, why)
	}
}

// The storage unit runs with UMask=0077 and the boot assembly may have made
// /run/onemind 0700: the gateway (group onemind) must still reach the socket.
func TestListenKeepsTheSocketReachable(t *testing.T) {
	old := syscall.Umask(0o077)
	defer syscall.Umask(old)
	base, err := os.MkdirTemp("/tmp", "om-sock-") // Unix socket paths are short
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(base)
	dir := filepath.Join(base, "onemind")
	if err := os.Mkdir(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	l, err := Listen(filepath.Join(dir, "storage.sock"), -1)
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	fi, _ := os.Stat(dir)
	sock, _ := os.Stat(filepath.Join(dir, "storage.sock"))
	if fi.Mode().Perm() != 0o755 || sock.Mode().Perm() != 0o660 {
		t.Errorf("folder %v socket %v", fi.Mode().Perm(), sock.Mode().Perm())
	}
	// A folder that already lets the group in is left as the image made it.
	if err := os.Chmod(dir, 0o750); err != nil {
		t.Fatal(err)
	}
	if err := searchableDir(dir); err != nil {
		t.Fatal(err)
	}
	if fi, _ := os.Stat(dir); fi.Mode().Perm() != 0o750 {
		t.Errorf("0750 changed to %v", fi.Mode().Perm())
	}
	// The boot assembly's markers folder: its parent stays enterable.
	run := filepath.Join(base, "run2", "storage")
	if err := storage.MakeRunDir(run); err != nil {
		t.Fatal(err)
	}
	p, _ := os.Stat(filepath.Dir(run))
	r, _ := os.Stat(run)
	if p.Mode().Perm() != 0o755 || r.Mode().Perm() != 0o700 {
		t.Errorf("parent %v run dir %v", p.Mode().Perm(), r.Mode().Perm())
	}
}
