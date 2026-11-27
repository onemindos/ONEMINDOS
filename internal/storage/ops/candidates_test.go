// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/storage"
)

// lsblkBox answers lsblk with one system disk (whose data partition is
// described by sysData) and optionally a second disk, and `cryptsetup token
// export` with the tokens in toks (by partition path).
type lsblkBox struct {
	sysData, other map[string]any
	toks           map[string]*storage.Token
}

func (b lsblkBox) Exec(_ context.Context, _ string, name string, args ...string) ([]byte, int, error) {
	line := name + " " + strings.Join(args, " ")
	switch {
	case name == "lsblk":
		sys := map[string]any{"name": "/dev/vda", "type": "disk", "children": []any{
			map[string]any{"name": "/dev/vda2", "type": "part", "pkname": "/dev/vda", "fstype": "ext4", "mountpoints": []string{"/"}},
			b.sysData,
		}}
		devs := []any{sys}
		if b.other != nil {
			devs = append(devs, map[string]any{"name": "/dev/sdb", "type": "disk", "children": []any{b.other}})
		}
		bs, _ := json.Marshal(map[string]any{"blockdevices": devs})
		return bs, 0, nil
	case strings.HasPrefix(line, "cryptsetup token export"):
		if t := b.toks[args[len(args)-1]]; t != nil {
			bs, _ := json.Marshal(t)
			return bs, 0, nil
		}
		return nil, 1, nil
	}
	return nil, 0, nil
}

func dataPart(path, fstype, label, uuid, partuuid string) map[string]any {
	return map[string]any{"name": path, "type": "part", "pkname": "/dev/vda", "fstype": fstype, "label": label,
		"uuid": uuid, "partlabel": "onemind-data", "partuuid": partuuid}
}

// The default box without a TPM keeps /data as plain btrfs: the reset must
// list it, as a plain member of a set named by the btrfs UUID.
func TestCandidatesListsThePlainBtrfsDataOfTheSystemDisk(t *testing.T) {
	b := lsblkBox{sysData: dataPart("/dev/vda7", "btrfs", "onemind-data", "5E7A0000-0000-4000-8000-000000000001", "aaaa1111")}
	cands, err := Candidates(context.Background(), b)
	if err != nil || len(cands) != 1 {
		t.Fatalf("%+v %v", cands, err)
	}
	c := cands[0]
	if !c.Plain || !c.System || c.Token == nil || c.Token.SetUUID != "5e7a0000-0000-4000-8000-000000000001" || c.Token.PartUUID != "aaaa1111" || c.Token.Generation != 0 {
		t.Fatalf("%+v %+v", c, c.Token)
	}
	set, current, _, _ := Choose(cands)
	if set != c.Token.SetUUID || len(current) != 1 {
		t.Fatalf("Choose: %q %v", set, current)
	}
}

// Only the system disk's partition with the OneMind names counts as plain data.
func TestCandidatesNeverListsForeignPlainBtrfs(t *testing.T) {
	sysOK := dataPart("/dev/vda7", "btrfs", "onemind-data", "5e7a0000-0000-4000-8000-000000000001", "aaaa1111")
	cases := map[string]lsblkBox{
		"another disk with the label": {sysData: dataPart("/dev/vda7", "", "", "", ""),
			other: map[string]any{"name": "/dev/sdb1", "type": "part", "pkname": "/dev/sdb", "fstype": "btrfs", "label": "onemind-data",
				"uuid": "5e7a0000-0000-4000-8000-0000000000ff", "partlabel": "onemind-data", "partuuid": "bbbb2222"}},
		"another btrfs label on the system disk": {sysData: dataPart("/dev/vda7", "btrfs", "backup", "5e7a0000-0000-4000-8000-000000000001", "aaaa1111")},
		"ext4 data (installed before btrfs)":     {sysData: dataPart("/dev/vda7", "ext4", "onemind-data", "5e7a0000-0000-4000-8000-000000000001", "aaaa1111")},
	}
	for name, b := range cases {
		cands, err := Candidates(context.Background(), b)
		if err != nil {
			t.Fatal(name, err)
		}
		for _, c := range cands {
			if c.Plain {
				t.Errorf("%s: listed %+v", name, c)
			}
		}
	}
	// the boot assembly (not the reset) never sees a plain partition
	b := lsblkBox{sysData: sysOK}
	got, _, err := candidates(context.Background(), &storage.Collector{Run: stdoutOf{b}}, b, false)
	if err != nil || len(got) != 0 {
		t.Fatalf("assembly saw %+v %v", got, err)
	}
}

// Every program the new layout steps run is one the engine allows.
func TestLayoutStepsUseOnlyAllowedPrograms(t *testing.T) {
	for _, st := range append(storage.LayoutSteps("/top", storage.PhaseCommit), storage.InitSteps(storage.InitOptions{Part: "/dev/vdb1", SetUUID: "x"})...) {
		if !allowed[st.Cmd[0]] {
			t.Errorf("step %s runs %s, which the engine refuses", st.ID, st.Cmd[0])
		}
	}
}
