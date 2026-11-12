// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"encoding/json"
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
		"cryptsetup open --key-file /data/onemind/storage/keys/set.key /dev/vde1 onemind-data-vde",
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
			if err := json.Unmarshal([]byte(s.Stdin), &tok); err != nil || tok.Generation != 5 || tok.SetUUID != set.UUID || tok.Type != TokenType {
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
	// The replaced member's token is not rewritten (it becomes stale).
	n := 0
	for _, s := range p.Steps {
		if s.ID == "token-member" {
			n++
			if strings.Contains(strings.Join(s.Cmd, " "), "/dev/vdc1") {
				t.Error("token rewritten on the replaced member")
			}
		}
	}
	if n != 1 {
		t.Errorf("%d token-member steps", n)
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
	for _, w := range []string{"--key-file /run/onemind/storage/recovery-key /dev/vdb1", "--tpm2-public-key-pcrs=11", "install -m 0600 /run/onemind/storage/set.key /run/onemind/storage/top/@/onemind/storage/keys/set.key", "--uuid 5e7a0000-0000-4000-8000-000000000001"} {
		if !strings.Contains(c, w) {
			t.Errorf("missing %q in\n%s", w, c)
		}
	}
}
