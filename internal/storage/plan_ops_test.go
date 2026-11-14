// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strings"
	"testing"
)

func stepIDs(p Plan) string {
	var ids []string
	for _, s := range p.Steps {
		ids = append(ids, s.ID)
	}
	return strings.Join(ids, ",")
}

// encryptedSet is the lab's encrypted two-member set with LUKS facts filled
// in the way Collector.LUKS does, plus a blank third disk.
func encryptedSet(t *testing.T) ([]Disk, *Mirror) {
	t.Helper()
	set := mirror(t, "repaired")
	ds := disks(t, "repaired.lsblk.json", set)
	for i := range set.Members {
		set.Members[i].Backing = BackingOf(ds, set.Members[i].Path)
		set.Members[i].LUKSUUID = "luks-" + set.Members[i].Backing
		set.Members[i].PartUUID = "part-" + set.Members[i].Backing
	}
	set.Encrypted, set.Generation = true, 4
	ds = append(ds, Disk{Path: "/dev/vde", ID: "/dev/vde", Role: RoleUnused, SizeBytes: 8 << 30})
	return ds, set
}

func TestBackingOf(t *testing.T) {
	noMarker(t)
	set := mirror(t, "repaired")
	ds := disks(t, "repaired.lsblk.json", set)
	if b := BackingOf(ds, "/dev/mapper/onemind-data-vdc"); b != "/dev/vdc1" {
		t.Errorf("backing %q", b)
	}
	if b := BackingOf(ds, "/dev/vda1"); b != "" {
		t.Errorf("plain partition has no backing, got %q", b)
	}
}

func TestPlanProtectEncryptedClonesHeader(t *testing.T) {
	noMarker(t)
	ds, set := encryptedSet(t)
	p := PlanProtect(ds, set, "/dev/vde", PlanOptions{})
	if p.Blocked || !p.Encrypted {
		t.Fatalf("%+v", p.Checks)
	}
	want := "wipe,partition,settle,rundir,luks-header-drop,luks-header-backup,luks-header-restore,luks-header-drop,luks-uuid,luks-open,token,token-member,token-member,device-add,balance,verify"
	if got := stepIDs(p); got != want {
		t.Fatalf("steps\n got %s\nwant %s", got, want)
	}
	c := cmds(p)
	for _, w := range []string{
		"cryptsetup luksHeaderBackup /dev/vdb1 --header-backup-file /run/onemind/storage/header-",
		"cryptsetup luksHeaderRestore --batch-mode /dev/vde1",
		"cryptsetup open --key-file /data/onemind/secrets/storage-set.key /dev/vde1 onemind-data-vde",
		"btrfs device add /dev/mapper/onemind-data-vde /data",
		"btrfs balance start -dconvert=raid1,soft -mconvert=raid1c3,soft /data",
	} {
		if !strings.Contains(c, w) {
			t.Errorf("missing %q in\n%s", w, c)
		}
	}
	// Every member and the new one move to generation 5; keys never appear.
	for _, s := range p.Steps {
		if strings.HasPrefix(s.ID, "token") {
			var tok Token
			if err := json.Unmarshal([]byte(s.Stdin), &tok); err != nil || tok.Generation != 5 || tok.SetUUID != set.UUID || tok.Type != TokenType || tok.PartUUID == "" {
				t.Errorf("token %q: %+v %v", s.Stdin, tok, err)
			}
		}
	}
	// Phases: prepare until device-add (join), balance commits.
	for _, s := range p.Steps {
		want := PhasePrepare
		switch s.ID {
		case "token-member", "device-add":
			want = PhaseJoin
		case "balance":
			want = PhaseCommit
		case "verify":
			want = PhaseVerify
		}
		if s.Phase != want {
			t.Errorf("%s phase %s, want %s", s.ID, s.Phase, want)
		}
	}
	// Same facts, same plan: request, approval and run agree.
	if PlanProtect(ds, set, "/dev/vde", PlanOptions{}).SHA256 != p.SHA256 {
		t.Error("plan_sha256 not reproducible")
	}
}

func TestPlanReplace(t *testing.T) {
	noMarker(t)
	ds, set := encryptedSet(t)
	p := PlanReplace(ds, set, "/dev/vdc", "/dev/vde", true, PlanOptions{})
	if p.Blocked {
		t.Fatalf("%+v", p.Checks)
	}
	c := cmds(p)
	for _, w := range []string{
		"cryptsetup luksHeaderBackup /dev/vdb1", // clones from the member that stays
		"btrfs replace start -B -f 2 /dev/mapper/onemind-data-vde /data",
		"btrfs filesystem resize 2:max /data",
		"cryptsetup close /dev/mapper/onemind-data-vdc",
		"cryptsetup erase --batch-mode /dev/vdc1",
		"sgdisk --zap-all /dev/vdc",
	} {
		if !strings.Contains(c, w) {
			t.Errorf("missing %q in\n%s", w, c)
		}
	}
	// Before the replace every member (the old one too) moves to generation
	// 5; after it, the others move to 6 without the old one, which becomes
	// stale for the boot assembly only once the replace has finished.
	replaced := false
	for _, s := range p.Steps {
		if s.ID == "replace" {
			replaced = true
		}
		if !strings.HasPrefix(s.ID, "token") {
			continue
		}
		var tok Token
		_ = json.Unmarshal([]byte(s.Stdin), &tok)
		onOld := strings.Contains(strings.Join(s.Cmd, " "), "/dev/vdc1")
		switch {
		case !replaced && tok.Generation != 5, replaced && tok.Generation != 6:
			t.Errorf("%s gen %d (after replace: %t)", s.ID, tok.Generation, replaced)
		case replaced && onOld:
			t.Error("old member promoted after the replace")
		}
	}
	if !strings.Contains(stepIDs(p), "luks-open,token,token-member,token-member,replace,resize,balance,token-member,token-member,old-close") {
		t.Error(stepIDs(p))
	}
	// No headroom on the member that stays: blocked before anything runs.
	full := *set
	full.Members = append([]Member(nil), set.Members...)
	full.Members[0].UsedBytes = full.Members[0].SizeBytes - 100<<20
	if bad := PlanReplace(ds, &full, "2", "/dev/vde", false, PlanOptions{}); !bad.Blocked || !strings.Contains(fmt.Sprint(bad.Checks), "headroom:devid1") {
		t.Errorf("full member not blocked: %+v", bad.Checks)
	}
	// Too small, a member as target, unknown member: blocked.
	small := append([]Disk(nil), ds...)
	small[len(small)-1].SizeBytes = 1 << 30
	for _, bad := range []Plan{
		PlanReplace(small, set, "2", "/dev/vde", false, PlanOptions{}),
		PlanReplace(ds, set, "2", "/dev/vdb", false, PlanOptions{}),
		PlanReplace(ds, set, "devid:9", "/dev/vde", false, PlanOptions{}),
	} {
		if !bad.Blocked || len(bad.Steps) != 0 {
			t.Errorf("not blocked: %+v", bad.Checks)
		}
	}
}

func TestPlanReplaceMissingMember(t *testing.T) {
	noMarker(t)
	m := mirror(t, "degraded-mounted")
	ds := disks(t, "degraded-mounted.lsblk.json", m)
	ds = append(ds, Disk{Path: "/dev/vdx", ID: "/dev/vdx", Role: RoleUnused, SizeBytes: 8 << 30})
	p := PlanReplace(ds, m, "missing", "/dev/vdx", false, PlanOptions{})
	if p.Blocked {
		t.Fatalf("%+v", p.Checks)
	}
	if !regexp.MustCompile(`btrfs replace start -B -f \d /dev/\S+ /data`).MatchString(cmds(p)) || strings.Contains(cmds(p), "old-") {
		t.Error(cmds(p))
	}
}

func TestPlanRemove(t *testing.T) {
	noMarker(t)
	ds, set := encryptedSet(t)
	if p := PlanRemove(ds, set, "2", false, false, PlanOptions{}); !p.Blocked {
		t.Error("2 → 1 without unprotect must be blocked")
	}
	p := PlanRemove(ds, set, "/dev/vdc", true, true, PlanOptions{})
	if p.Blocked {
		t.Fatalf("%+v", p.Checks)
	}
	if got, want := stepIDs(p), "balance,device-remove,token-member,old-close,old-erase,old-wipefs,old-zap,verify"; got != want {
		t.Errorf("steps\n got %s\nwant %s", got, want)
	}
	c := cmds(p)
	for _, w := range []string{"btrfs balance start -f -dconvert=single,soft -mconvert=dup,soft -sconvert=dup,soft /data", "btrfs device remove 2 /data"} {
		if !strings.Contains(c, w) {
			t.Errorf("missing %q in\n%s", w, c)
		}
	}
	if p.DataProfile != "single" || p.MetaProfile != "dup" || len(p.Warnings) == 0 {
		t.Errorf("%+v", p)
	}
	// Three to two converts metadata first; four to three needs no balance.
	three := *set
	three.Members = append(append([]Member(nil), set.Members...), Member{DevID: 3, Path: "/dev/vde1", SizeBytes: 6424604672})
	if c := cmds(PlanRemove(ds, &three, "3", false, false, PlanOptions{})); !strings.HasPrefix(c, "btrfs balance start -f -mconvert=raid1,soft -sconvert=raid1,soft /data\nbtrfs device remove 3 /data") {
		t.Errorf("3 → 2:\n%s", c)
	}
	// Not enough room on the others.
	full := *set
	full.Members = append([]Member(nil), set.Members...)
	full.Members[0].UsedBytes, full.Members[1].UsedBytes = full.Members[0].SizeBytes, full.Members[1].SizeBytes
	if p := PlanRemove(ds, &full, "2", true, false, PlanOptions{}); !p.Blocked {
		t.Error("full set: remove not blocked")
	}
}

func TestDerivedUUIDAndRecoveryKey(t *testing.T) {
	a, b := DerivedUUID("set", "disk", "part"), DerivedUUID("set", "disk", "luks")
	re := regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
	if !re.MatchString(a) || a == b || a != DerivedUUID("set", "disk", "part") {
		t.Errorf("%s %s", a, b)
	}
	k1, err := NewRecoveryKey()
	k2, _ := NewRecoveryKey()
	if err != nil || k1 == k2 || !regexp.MustCompile(`^([cbdefghijklnrtuv]{8}-){7}[cbdefghijklnrtuv]{8}$`).MatchString(k1) {
		t.Errorf("recovery key %q %v", k1, err)
	}
}

func TestParseLUKSDump(t *testing.T) {
	dump := `{"keyslots":{"0":{},"1":{}},"tokens":{"0":{"type":"systemd-tpm2","keyslots":["2"]},"30":{"type":"onemind-storage","keyslots":[],"set_uuid":"s","member_uuid":"m","generation":7}}}`
	tok, err := ParseLUKSDump([]byte(dump))
	if err != nil || tok == nil || tok.Generation != 7 || tok.MemberUUID != "m" {
		t.Fatalf("%+v %v", tok, err)
	}
	if tok, _ := ParseLUKSDump([]byte(`{"tokens":{}}`)); tok != nil {
		t.Error("no token expected")
	}
}

func TestInitStepsKeepKeysOffDisk(t *testing.T) {
	steps := InitSteps(InitOptions{Part: "/dev/vdb1", SetUUID: "5e7a0000-0000-4000-8000-000000000001", TPM2: true, PCRKey: PCRPublicKey})
	var ids []string
	for _, s := range steps {
		ids = append(ids, s.ID)
		if strings.Contains(s.Stdin, "key") && s.ID != "token" {
			t.Errorf("%s carries a key on stdin", s.ID)
		}
	}
	got := strings.Join(ids, ",")
	if got != "luks-format,luks-setkey,luks-tpm2,token,luks-open,mkfs,top,mount,subvolume,subvolume,subvolume,keydir,keymove,keydrop,umount" {
		t.Error(got)
	}
	c := cmds(Plan{Steps: steps})
	for _, w := range []string{"--key-file /run/onemind/storage/recovery-key /dev/vdb1", "--tpm2-public-key-pcrs=11", "install -m 0600 /run/onemind/storage/set.key /run/onemind/storage/top/@/onemind/secrets/storage-set.key", "--uuid 5e7a0000-0000-4000-8000-000000000001"} {
		if !strings.Contains(c, w) {
			t.Errorf("missing %q in\n%s", w, c)
		}
	}
}

func TestShowCountsUnmountedMissing(t *testing.T) {
	// Recorded in the Debian 13 VM lab (log 27): an unmounted set does not list the missing devid.
	out := "Label: 'onemind-data'  uuid: f587b105-7dd7-49f2-ae22-975c78079dbd\n" +
		"\tTotal devices 3 FS bytes used 2099625984\n" +
		"\tdevid    1 size 4277121024 used 3374252032 path /dev/mapper/onemind-data-64abeb67\n" +
		"\tdevid    3 size 4277121024 used 301989888 path /dev/mapper/onemind-data-a3e280b6\n" +
		"\t*** Some devices missing\n"
	if total, present, err := ShowCounts([]byte(out)); err != nil || total != 3 || present != 2 {
		t.Errorf("%d %d %v", total, present, err)
	}
	b, _ := os.ReadFile("testdata/degraded-mounted.show.txt") // mounted: listed as MISSING
	if total, present, err := ShowCounts(b); err != nil || total != 2 || present != 1 {
		t.Errorf("mounted: %d %d %v", total, present, err)
	}
}

// onSystemDisk puts the member partition backing devid 2 on the system disk,
// next to the OS partitions (the first member made by `storage init` lives
// there, docs/leap/core/STORAGE-ACT-os.patch.md).
func onSystemDisk(t *testing.T, ds []Disk, part string) []Disk {
	t.Helper()
	out := append([]Disk(nil), ds...)
	for i := range out {
		for _, s := range out[i].Holds {
			if s.Path == part {
				out[i].Role = RoleSystem
				out[i].Holds = append(append([]Signature(nil), out[i].Holds...),
					Signature{Path: out[i].Path + "9", Type: "part", FSType: "ext4", Mountpoints: []string{"/"}})
				return out
			}
		}
	}
	t.Fatalf("no disk holds %s", part)
	return nil
}

func TestWipeNeverTouchesTheSystemDisk(t *testing.T) {
	noMarker(t)
	ds, set := encryptedSet(t)
	var backing string
	for _, m := range set.Members {
		if m.DevID == 2 {
			backing = m.Backing
		}
	}
	sys := onSystemDisk(t, ds, backing)
	three := *set
	three.Members = append(append([]Member(nil), set.Members...), Member{DevID: 3, Path: "/dev/vde1", SizeBytes: 6424604672})
	for name, p := range map[string]Plan{
		"remove":  PlanRemove(sys, &three, "2", false, true, PlanOptions{}),
		"replace": PlanReplace(sys, set, "2", "/dev/vde", true, PlanOptions{}),
	} {
		if !p.Blocked || strings.Contains(cmds(p), "sgdisk --zap-all") {
			t.Errorf("%s with wipe of a member on the system disk must be blocked, got\n%s", name, cmds(p))
		}
	}
	// Without wipe the member may leave; its partition stays a OneMind partition.
	if p := PlanRemove(sys, &three, "2", false, false, PlanOptions{}); p.Blocked || strings.Contains(cmds(p), "--zap-all") {
		t.Errorf("remove without wipe: blocked=%t\n%s", p.Blocked, cmds(p))
	}
	// A data disk that also holds another partition: wipe the member, never the whole disk.
	other := append([]Disk(nil), ds...)
	for i := range other {
		for _, s := range other[i].Holds {
			if s.Path == backing {
				other[i].Holds = append(append([]Signature(nil), other[i].Holds...), Signature{Path: other[i].Path + "9", Type: "part", FSType: "ext4"})
			}
		}
	}
	p := PlanRemove(other, &three, "2", false, true, PlanOptions{})
	if p.Blocked || strings.Contains(cmds(p), "--zap-all") || !strings.Contains(cmds(p), "wipefs --all "+backing) {
		t.Errorf("remove with wipe on a shared disk: blocked=%t\n%s", p.Blocked, cmds(p))
	}
}

// The image mounts @storage at <data>/onemind/storage: a set key there would
// be hidden under that mount and every encrypted add or replace blocked.
func TestSetKeyIsNotUnderTheStorageSubvolume(t *testing.T) {
	if strings.HasPrefix(SetKeyPath, "onemind/storage/") || !strings.HasPrefix(SetKeyPath, "onemind/") {
		t.Errorf("SetKeyPath %q", SetKeyPath)
	}
}
