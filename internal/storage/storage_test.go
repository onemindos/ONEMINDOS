// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fixtureRunner replays recorded output from testdata/<prefix>.*.
type fixtureRunner struct {
	t      *testing.T
	prefix string // findmnt/btrfs fixtures
	lsblk  string // lsblk fixture file
	smart  map[string]string
}

func (f fixtureRunner) Run(_ context.Context, name string, args ...string) ([]byte, int, error) {
	file, exit := "", 0
	switch {
	case name == "lsblk":
		file = f.lsblk
	case name == "findmnt":
		file = f.prefix + ".findmnt.json"
	case name == "btrfs" && args[0] == "filesystem" && args[1] == "show":
		file = f.prefix + ".show.txt"
	case name == "btrfs" && args[0] == "filesystem" && args[1] == "df":
		file = f.prefix + ".df.txt"
	case name == "btrfs" && args[0] == "device" && args[1] == "stats":
		file = f.prefix + ".stats.txt"
	case name == "smartctl":
		file = f.smart[args[len(args)-1]]
		if file == "" {
			file = "virtio.smartctl.json"
		}
	default:
		f.t.Fatalf("unexpected command %s %v", name, args)
	}
	b, err := os.ReadFile(filepath.Join("testdata", file))
	if err != nil {
		f.t.Fatal(err)
	}
	if name == "smartctl" && strings.HasPrefix(file, "virtio") {
		exit = 1
	}
	return b, exit, nil
}

func noMarker(t *testing.T) {
	old := statFile
	statFile = func(string) (fs.FileInfo, error) { return nil, os.ErrNotExist }
	t.Cleanup(func() { statFile = old })
}

func withMarker(t *testing.T) {
	old := statFile
	statFile = func(p string) (fs.FileInfo, error) {
		if strings.HasSuffix(p, NeedsScrubMarker) {
			return nil, nil
		}
		return nil, os.ErrNotExist
	}
	t.Cleanup(func() { statFile = old })
}

func mirror(t *testing.T, prefix string) *Mirror {
	t.Helper()
	c := &Collector{Run: fixtureRunner{t: t, prefix: prefix, lsblk: "blank.lsblk.json"}}
	m, err := c.MirrorStatus(context.Background(), "/data")
	if err != nil {
		t.Fatal(err)
	}
	return m
}

func disks(t *testing.T, file string, set *Mirror) []Disk {
	t.Helper()
	c := &Collector{Run: fixtureRunner{t: t, lsblk: file}}
	d, err := c.Inventory(context.Background(), set)
	if err != nil {
		t.Fatal(err)
	}
	return d
}

func TestInventoryRoles(t *testing.T) {
	want := map[string]Role{"/dev/vda": RoleSystem, "/dev/vdb": RoleUnused, "/dev/vdc": RoleUnused, "/dev/vdd": RoleInUse}
	got := disks(t, "blank.lsblk.json", nil)
	if len(got) != len(want) {
		t.Fatalf("got %d disks, want %d", len(got), len(want))
	}
	for _, d := range got {
		if d.Role != want[d.Path] {
			t.Errorf("%s: role %s, want %s", d.Path, d.Role, want[d.Path])
		}
		if d.ID != d.Path { // virtio: no WWN or serial
			t.Errorf("%s: id %q", d.Path, d.ID)
		}
	}
	if d, _ := Find(got, "vdd"); !d.ReadOnly || d.SizeBytes != 290637824 {
		t.Errorf("vdd: %+v", d)
	}
}

// After `btrfs device add` lsblk can lag; members are matched by path too.
func TestInventoryMembers(t *testing.T) {
	noMarker(t)
	m := mirror(t, "repaired")
	for _, d := range disks(t, "repaired.lsblk.json", m) {
		want := RoleMember
		if d.Path == "/dev/vda" {
			want = RoleSystem
		} else if d.Path == "/dev/vdd" {
			want = RoleInUse
		}
		if d.Role != want {
			t.Errorf("%s: role %s, want %s", d.Path, d.Role, want)
		}
	}
}

func TestMirrorStates(t *testing.T) {
	cases := []struct {
		prefix   string
		marker   bool
		state    State
		degraded bool
		missing  int
		repair   string
	}{
		{"unprotected", false, StateUnprotected, false, 0, ""},
		{"degraded-mounted", false, StateDegraded, true, 1, "reconnect,scrub,soft-convert"},
		{"degraded-written", false, StateDegraded, true, 1, "reconnect,scrub,soft-convert"},
		{"returned", false, StateDegraded, false, 0, "scrub,soft-convert"},
		{"repaired", false, StateProtected, false, 0, ""},
		// The lab's key finding: btrfs alone looks protected here.
		{"stale-no-marker", false, StateProtected, false, 0, ""},
		{"stale-no-marker", true, StateDegraded, false, 0, "scrub,soft-convert"},
	}
	for _, tc := range cases {
		t.Run(tc.prefix, func(t *testing.T) {
			if tc.marker {
				withMarker(t)
			} else {
				noMarker(t)
			}
			m := mirror(t, tc.prefix)
			missing := 0
			for _, mem := range m.Members {
				if mem.Missing {
					missing++
				}
			}
			if m.State != tc.state || m.Degraded != tc.degraded || missing != tc.missing || strings.Join(m.Repair, ",") != tc.repair {
				t.Errorf("state=%s degraded=%t missing=%d repair=%v reasons=%v", m.State, m.Degraded, missing, m.Repair, m.Reasons)
			}
			if m.UUID == "" || m.Label != "onemind-data" {
				t.Errorf("uuid %q label %q", m.UUID, m.Label)
			}
		})
	}
}

func TestDegradedWrittenShowsSingleChunks(t *testing.T) {
	noMarker(t)
	m := mirror(t, "degraded-written")
	if !strings.Contains(strings.Join(m.Reasons, "|"), "Data single") {
		t.Errorf("reasons %v", m.Reasons)
	}
	if m.Members[1].DevID != 2 || m.Members[1].Path != "" || m.Members[1].Errors["write_io_errs"] != 0 {
		t.Errorf("missing member %+v", m.Members[1])
	}
}

func TestEvaluateRaid5AndErrors(t *testing.T) {
	m := &Mirror{Members: []Member{{DevID: 1, Path: "/dev/a"}, {DevID: 2, Path: "/dev/b"}, {DevID: 3, Path: "/dev/c"}},
		Profiles: []Profile{{Kind: "Data", Profile: "raid5"}, {Kind: "Metadata", Profile: "raid1c3"}}}
	Evaluate(m)
	if m.State != StateUnsupported {
		t.Errorf("raid5: %s", m.State)
	}
	m = &Mirror{Members: []Member{{DevID: 1, Path: "/dev/a", Errors: map[string]int64{"corruption_errs": 3}}, {DevID: 2, Path: "/dev/b"}},
		Profiles: []Profile{{Kind: "Data", Profile: "raid1"}, {Kind: "Metadata", Profile: "raid1"}, {Kind: "System", Profile: "raid1"}}}
	Evaluate(m)
	if m.State != StateProtected || len(m.Reasons) != 1 || !strings.Contains(m.Reasons[0], "corruption_errs=3") {
		t.Errorf("errors: %s %v", m.State, m.Reasons)
	}
}

func TestMirrorUnavailable(t *testing.T) {
	c := &Collector{Run: runFunc(func(string, ...string) ([]byte, int, error) { return nil, 1, nil })}
	m, err := c.MirrorStatus(context.Background(), "/data")
	if err != nil || m.State != StateUnavailable {
		t.Fatalf("%v %+v", err, m)
	}
}

type runFunc func(string, ...string) ([]byte, int, error)

func (f runFunc) Run(_ context.Context, n string, a ...string) ([]byte, int, error) {
	return f(n, a...)
}

func TestSmart(t *testing.T) {
	cases := []struct {
		file    string
		exit    int
		verdict Verdict
		reason  string
	}{
		{"virtio.smartctl.json", 1, VerdictUnknown, "Unable to detect device type"},
		{"synthetic-nvme-ok.smartctl.json", 0, VerdictOK, ""},
		{"synthetic-nvme-worn.smartctl.json", 0, VerdictWarning, "wear 86%"},
		{"synthetic-sata-failing.smartctl.json", 8, VerdictCritical, "SMART overall health check failed"},
	}
	for _, tc := range cases {
		b, err := os.ReadFile(filepath.Join("testdata", tc.file))
		if err != nil {
			t.Fatal(err)
		}
		h, err := ParseSmart(b, tc.exit, DefaultThresholds)
		if err != nil {
			t.Fatal(err)
		}
		if h.Verdict != tc.verdict || !strings.Contains(strings.Join(h.Reasons, "|"), tc.reason) {
			t.Errorf("%s: %s %v", tc.file, h.Verdict, h.Reasons)
		}
	}
	b, _ := os.ReadFile("testdata/synthetic-nvme-worn.smartctl.json")
	h, _ := ParseSmart(b, 0, DefaultThresholds)
	// 64°C is above the 60°C warning; 2 media errors warn; wear 86% warns.
	if len(h.Reasons) != 3 || *h.WearPercent != 86 || *h.TemperatureC != 64 {
		t.Errorf("worn: %+v", h)
	}
	b, _ = os.ReadFile("testdata/synthetic-sata-failing.smartctl.json")
	h, _ = ParseSmart(b, 8, DefaultThresholds)
	if *h.Reallocated != 12 || *h.Pending != 3 || *h.Uncorrectable != 0 {
		t.Errorf("sata: %+v", h)
	}
}

func TestSmartArgsUSB(t *testing.T) {
	if got := strings.Join(SmartArgs(Disk{Path: "/dev/sda", Transport: "usb"}), " "); got != "--json=c -a -d sat /dev/sda" {
		t.Error(got)
	}
}

func cmds(p Plan) string {
	var s []string
	for _, st := range p.Steps {
		s = append(s, st.String())
	}
	return strings.Join(s, "\n")
}

func TestPlanCreate(t *testing.T) {
	ds := disks(t, "blank.lsblk.json", nil)
	p := PlanCreate(ds, []string{"/dev/vdb", "vdc"}, PlanOptions{Encrypt: true, KeyFile: "/run/k"})
	if p.Blocked || p.DataProfile != "raid1" || p.MetaProfile != "raid1" || len(p.Targets) != 2 {
		t.Fatalf("%+v", p)
	}
	c := cmds(p)
	for _, want := range []string{
		"sgdisk --new=1:0:0 --typecode=1:8309 --change-name=1:onemind-data --partition-guid=1:" + DerivedUUID("onemind-data", "/dev/vdb", "part") + " /dev/vdb",
		"cryptsetup luksFormat --type luks2 --batch-mode --uuid " + DerivedUUID("onemind-data", "/dev/vdc", "luks") + " --key-file /run/k /dev/vdc1",
		"mkfs.btrfs --label onemind-data --data raid1 --metadata raid1 /dev/mapper/onemind-data-vdb /dev/mapper/onemind-data-vdc",
		"mount -o noatime,compress=zstd:1,space_cache=v2,discard=async /dev/mapper/onemind-data-vdb /data",
		"btrfs subvolume create /data/@snapshots",
	} {
		if !strings.Contains(c, want) {
			t.Errorf("missing %q in\n%s", want, c)
		}
	}
	for _, bad := range []string{"raid5", "raid6", "raid0"} {
		if strings.Contains(c, bad) {
			t.Errorf("plan mentions %s", bad)
		}
	}

	// Refusals: the system disk, a read-only disk, a disk listed twice.
	for _, devs := range [][]string{{"/dev/vda", "/dev/vdb"}, {"/dev/vdd", "/dev/vdb"}, {"/dev/vdb", "/dev/vdb"}, {"/dev/nope"}} {
		if p := PlanCreate(ds, devs, PlanOptions{}); !p.Blocked || len(p.Steps) != 0 {
			t.Errorf("%v: not blocked", devs)
		}
	}
	// A critical SMART verdict blocks.
	h := map[string]Health{"/dev/vdc": {Verdict: VerdictCritical, Reasons: []string{"SMART failed"}}}
	if p := PlanCreate(ds, []string{"/dev/vdb", "/dev/vdc"}, PlanOptions{Health: h}); !p.Blocked {
		t.Error("failing disk not blocked")
	}
}

func TestPlanCreateProfilesAndPaths(t *testing.T) {
	ds := []Disk{
		{Path: "/dev/nvme0n1", ID: "a", Role: RoleUnused, SizeBytes: 1 << 40, SerialTail: "AB12"},
		{Path: "/dev/nvme1n1", ID: "b", Role: RoleUnused, SizeBytes: 1 << 40},
		{Path: "/dev/sda", ID: "c", Role: RoleUnused, SizeBytes: 1 << 39, Transport: "usb"},
	}
	p := PlanCreate(ds, []string{"a", "b", "c"}, PlanOptions{})
	if p.MetaProfile != "raid1c3" || p.DataProfile != "raid1" {
		t.Errorf("profiles %s/%s", p.DataProfile, p.MetaProfile)
	}
	c := cmds(p)
	if !strings.Contains(c, "/dev/nvme0n1p1") || !strings.Contains(c, "/dev/sda1") || strings.Contains(c, "cryptsetup") {
		t.Errorf("paths:\n%s", c)
	}
	p = PlanCreate(ds, []string{"a"}, PlanOptions{Encrypt: true})
	if p.DataProfile != "single" || p.MetaProfile != "dup" || len(p.Warnings) == 0 || !strings.Contains(cmds(p), "onemind-data-ab12") {
		t.Errorf("one disk: %+v", p)
	}
}

func TestPlanSHABindsDisk(t *testing.T) {
	a := []Disk{{Path: "/dev/sdb", ID: "wwn-1", SerialTail: "1111", Role: RoleUnused, SizeBytes: 100}, {Path: "/dev/sdc", ID: "wwn-2", Role: RoleUnused, SizeBytes: 100}}
	b := []Disk{{Path: "/dev/sdb", ID: "wwn-9", SerialTail: "9999", Role: RoleUnused, SizeBytes: 100}, a[1]}
	pa := PlanCreate(a, []string{"/dev/sdb", "/dev/sdc"}, PlanOptions{})
	pb := PlanCreate(b, []string{"/dev/sdb", "/dev/sdc"}, PlanOptions{})
	if pa.SHA256 == pb.SHA256 || len(pa.SHA256) != 64 {
		t.Error("a different disk on the same path must change plan_sha256")
	}
	if pa.SHA256 != PlanCreate(a, []string{"/dev/sdb", "/dev/sdc"}, PlanOptions{}).SHA256 {
		t.Error("plan_sha256 not deterministic")
	}
}

func TestPlanProtect(t *testing.T) {
	noMarker(t)
	ds := disks(t, "blank.lsblk.json", nil)
	m := mirror(t, "unprotected")
	p := PlanProtect(ds, m, "/dev/vdc", PlanOptions{})
	if p.Blocked {
		t.Fatalf("blocked: %+v", p.Checks)
	}
	c := cmds(p)
	for _, want := range []string{
		"btrfs device add /dev/vdc1 /data",
		"btrfs balance start -dconvert=raid1,soft -mconvert=raid1,soft /data",
	} {
		if !strings.Contains(c, want) {
			t.Errorf("missing %q in\n%s", want, c)
		}
	}
	if p.Encrypted || len(p.Warnings) == 0 {
		t.Errorf("unencrypted set: encrypted=%t warnings=%v", p.Encrypted, p.Warnings)
	}
	// A degraded set must be repaired first; a member cannot be re-added.
	if p := PlanProtect(ds, mirror(t, "degraded-mounted"), "/dev/vdc", PlanOptions{}); !p.Blocked {
		t.Error("degraded set not blocked")
	}
	set := mirror(t, "repaired")
	if p := PlanProtect(disks(t, "repaired.lsblk.json", set), set, "/dev/vdc", PlanOptions{}); !p.Blocked {
		t.Error("member re-added")
	}
	// Too small for what is already allocated.
	small := append([]Disk(nil), ds...)
	for i := range small {
		if small[i].Path == "/dev/vdc" {
			small[i].SizeBytes = 1 << 20
		}
	}
	if p := PlanProtect(small, m, "/dev/vdc", PlanOptions{}); !p.Blocked {
		t.Error("small disk not blocked")
	}
}

func TestPlanProtectFollowsEncryption(t *testing.T) {
	noMarker(t)
	set := mirror(t, "repaired")
	ds := disks(t, "repaired.lsblk.json", set)
	ds = append(ds, Disk{Path: "/dev/vde", ID: "/dev/vde", Role: RoleUnused, SizeBytes: 8 << 30})
	p := PlanProtect(ds, set, "/dev/vde", PlanOptions{KeyFile: "/run/k"})
	if p.Blocked || !p.Encrypted || p.MetaProfile != "raid1c3" {
		t.Fatalf("%+v", p)
	}
	if !strings.Contains(cmds(p), "btrfs device add /dev/mapper/onemind-data-vde /data") {
		t.Error(cmds(p))
	}
}

func TestPlanRepair(t *testing.T) {
	noMarker(t)
	if p := PlanRepair(mirror(t, "degraded-written")); !p.Blocked {
		t.Error("repair with a missing member must be blocked")
	}
	p := PlanRepair(mirror(t, "returned"))
	c := cmds(p)
	if p.Blocked || !strings.HasPrefix(c, "btrfs scrub start -B /data\nbtrfs balance start -dconvert=raid1,soft -mconvert=raid1,soft /data") {
		t.Errorf("order:\n%s", c)
	}
	if strings.Contains(c, NeedsScrubMarker) {
		t.Error("no marker, no rm")
	}
	withMarker(t)
	if c := cmds(PlanRepair(mirror(t, "stale-no-marker"))); !strings.HasSuffix(c, "rm -f /data/"+NeedsScrubMarker) {
		t.Errorf("marker not cleared last:\n%s", c)
	}
}

func TestStepQuoting(t *testing.T) {
	if s := (Step{Cmd: []string{"echo", "a b", "it's"}}).String(); s != `echo 'a b' 'it'\''s'` {
		t.Error(s)
	}
}
