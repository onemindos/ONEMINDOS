// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
)

func tok(set, partuuid string, gen int) *storage.Token {
	return &storage.Token{Type: storage.TokenType, SetUUID: set, PartUUID: partuuid, Generation: gen}
}

func TestChooseMembers(t *testing.T) {
	cands := []Candidate{
		{Part: "/dev/vda7", PartUUID: "p-sys", System: true, Token: tok("set-a", "p-sys", 4)},
		{Part: "/dev/vdb1", PartUUID: "p-b", Token: tok("set-a", "p-b", 4)},
		{Part: "/dev/vdc1", PartUUID: "p-c", Token: tok("set-a", "p-c", 3)},     // left the set
		{Part: "/dev/vdd1", PartUUID: "p-d", Token: tok("set-a", "p-sys", 4)},   // a copied header
		{Part: "/dev/vde1", PartUUID: "p-e", Token: tok("set-other", "p-e", 9)}, // another box's disk
		{Part: "/dev/vdf1", PartUUID: "p-f"},                                    // no token
	}
	set, current, stale, skipped := Choose(cands)
	if set != "set-a" {
		t.Fatalf("set %q: the system disk's set wins over a newer foreign one", set)
	}
	parts := func(cs []Candidate) string {
		var s []string
		for _, c := range cs {
			s = append(s, c.Part)
		}
		return strings.Join(s, ",")
	}
	if parts(current) != "/dev/vda7,/dev/vdb1" || parts(stale) != "/dev/vdc1" || parts(skipped) != "/dev/vdd1,/dev/vdf1,/dev/vde1" {
		t.Errorf("current %s stale %s skipped %s", parts(current), parts(stale), parts(skipped))
	}
	for _, c := range skipped {
		if c.Skip == "" {
			t.Errorf("%s skipped without a reason", c.Part)
		}
	}
	// No system member (its disk died): the newest set is taken.
	set, current, _, _ = Choose(cands[1:3])
	if set != "set-a" || parts(current) != "/dev/vdb1" {
		t.Errorf("%s %s", set, parts(current))
	}
	if MapperName(cands[0]) != "onemind-data" || MapperName(cands[1]) != "onemind-data-p-b" {
		t.Error(MapperName(cands[1]))
	}
}

// bootBox scripts the commands of one boot.
type bootBox struct {
	parts    []fakePart
	members  map[string]bool // mapper paths btrfs knows, false = missing
	opened   map[string]bool
	asks     int
	key      string
	mountErr map[string]bool // mount option sets that fail ("" normal, "degraded")
	mounted  string
	late     int // calls to lsblk before the late disk appears
	lsblk    int
}

type fakePart struct {
	path, partuuid, disk string
	system, late         bool
	tok                  *storage.Token
}

func (b *bootBox) Exec(_ context.Context, stdin, name string, args ...string) ([]byte, int, error) {
	line := name + " " + strings.Join(args, " ")
	switch {
	case name == "lsblk":
		b.lsblk++
		type dev struct {
			Name      string   `json:"name"`
			Type      string   `json:"type"`
			PKName    string   `json:"pkname,omitempty"`
			FSType    string   `json:"fstype,omitempty"`
			PartLabel string   `json:"partlabel,omitempty"`
			PartUUID  string   `json:"partuuid,omitempty"`
			Children  []dev    `json:"children,omitempty"`
			Mounts    []string `json:"mountpoints,omitempty"`
		}
		var out []dev
		disks := map[string]*dev{}
		var order []string
		for _, p := range b.parts {
			if p.late && b.lsblk <= b.late {
				continue
			}
			d := disks[p.disk]
			if d == nil {
				d = &dev{Name: p.disk, Type: "disk"}
				if p.system {
					d.Children = append(d.Children, dev{Name: p.disk + "2", Type: "part", PKName: p.disk, FSType: "ext4", Mounts: []string{"/"}})
				}
				disks[p.disk] = d
				order = append(order, p.disk)
			}
			d.Children = append(d.Children, dev{Name: p.path, Type: "part", PKName: p.disk, FSType: "crypto_LUKS", PartLabel: "onemind-data", PartUUID: p.partuuid})
		}
		for _, n := range order {
			out = append(out, *disks[n])
		}
		bs, _ := json.Marshal(map[string]any{"blockdevices": out})
		return bs, 0, nil
	case strings.HasPrefix(line, "cryptsetup token export"):
		for _, p := range b.parts {
			if p.path == args[len(args)-1] && p.tok != nil {
				bs, _ := json.Marshal(p.tok)
				return bs, 0, nil
			}
		}
		return nil, 1, nil
	case strings.HasPrefix(line, "cryptsetup status"):
		if b.opened[args[1]] {
			return nil, 0, nil
		}
		return nil, 4, nil
	case strings.HasPrefix(line, "cryptsetup open --token-only"):
		return nil, 1, nil // no TPM2 in this box
	case strings.HasPrefix(line, "cryptsetup open"):
		if strings.Contains(line, "--key-file=-") && stdin != b.key {
			return []byte("No key available with this passphrase."), 2, nil
		}
		b.opened[args[len(args)-1]] = true
		return nil, 0, nil
	case name == "systemd-ask-password":
		b.asks++
		return []byte(b.key + "\n"), 0, nil
	case strings.HasPrefix(line, "btrfs device scan"):
		return nil, 0, nil
	case strings.HasPrefix(line, "btrfs filesystem show"):
		// An unmounted set: btrfs-progs omits a missing device and says so once.
		var sb strings.Builder
		fmt.Fprintf(&sb, "Label: 'onemind-data'  uuid: set-a\n\tTotal devices %d FS bytes used 1\n", len(b.members))
		i, gone := 1, false
		for dev, present := range b.members {
			if !present || !b.opened[strings.TrimPrefix(dev, "/dev/mapper/")] {
				gone = true
				continue
			}
			fmt.Fprintf(&sb, "\tdevid    %d size 100 used 10 path %s\n", i, dev)
			i++
		}
		if gone {
			sb.WriteString("\t*** Some devices missing\n")
		}
		return []byte(sb.String()), 0, nil
	case name == "mount":
		opts := ""
		if strings.Contains(line, "degraded") {
			opts = "degraded"
		}
		if strings.Contains(line, "tmpfs") {
			b.mounted = "tmpfs"
			return nil, 0, nil
		}
		if b.mountErr[opts] {
			return []byte("wrong fs type, bad superblock"), 32, nil
		}
		b.mounted = opts + ":" + args[len(args)-2]
		return nil, 0, nil
	}
	return nil, 0, nil
}

func newBoot() *bootBox {
	return &bootBox{
		key:    "recovery-key-123",
		opened: map[string]bool{}, mountErr: map[string]bool{},
		parts: []fakePart{
			{path: "/dev/vda7", partuuid: "aaaa1111", disk: "/dev/vda", system: true, tok: tok("set-a", "aaaa1111", 5)},
			{path: "/dev/vdb1", partuuid: "bbbb2222", disk: "/dev/vdb", tok: tok("set-a", "bbbb2222", 5)},
		},
		members: map[string]bool{"/dev/mapper/onemind-data": true, "/dev/mapper/onemind-data-bbbb2222": true},
	}
}

func assembleOpts(t *testing.T) AssembleOptions {
	t.Helper()
	return AssembleOptions{Mount: t.TempDir(), RunDir: t.TempDir(), Wait: 1500 * time.Millisecond, MountNormal: true, Log: slog.New(slog.NewTextHandler(io.Discard, nil))}
}

func TestAssembleNormalAsksOnce(t *testing.T) {
	b := newBoot()
	res, err := Assemble(context.Background(), b, assembleOpts(t))
	if err != nil || res.State != "mounted" || b.asks != 1 || len(res.Members) != 2 {
		t.Fatalf("%+v asks=%d err=%v", res, b.asks, err)
	}
	if !strings.HasPrefix(b.mounted, ":/dev/mapper/onemind-data") {
		t.Errorf("mounted %q: fstab's device is the system member", b.mounted)
	}
}

func TestAssembleWaitsForALateDisk(t *testing.T) {
	b := newBoot()
	b.parts[1].late, b.late = true, 1 // the USB disk shows up on the second look
	res, _ := Assemble(context.Background(), b, assembleOpts(t))
	if res.State != "mounted" || len(res.Members) != 2 {
		t.Fatalf("%+v", res)
	}
}

func TestAssembleOpensStaleMembersBeforeDegrading(t *testing.T) {
	b := newBoot()
	b.parts = append(b.parts, fakePart{path: "/dev/vdc1", partuuid: "cccc3333", disk: "/dev/vdc", tok: tok("set-a", "cccc3333", 4)})
	b.members["/dev/mapper/onemind-data-cccc3333"] = true // still holds chunks (its token fell behind)
	res, _ := Assemble(context.Background(), b, assembleOpts(t))
	if res.State != "mounted" || len(res.Stale) != 1 || !strings.Contains(res.Detail, "repair") {
		t.Fatalf("%+v", res)
	}
}

func TestAssembleDegradedAndUnavailable(t *testing.T) {
	b := newBoot()
	b.members["/dev/mapper/onemind-data-gone"] = false // a member that is not attached
	o := assembleOpts(t)
	res, _ := Assemble(context.Background(), b, o)
	if res.State != "degraded" || !strings.HasPrefix(b.mounted, "degraded:") {
		t.Fatalf("%+v mounted=%q", res, b.mounted)
	}
	b2 := newBoot()
	b2.members["/dev/mapper/onemind-data-gone"] = false
	b2.mountErr["degraded"] = true // too many missing for the profile
	res, _ = Assemble(context.Background(), b2, assembleOpts(t))
	if res.State != "unavailable" || b2.mounted != "tmpfs" {
		t.Fatalf("%+v mounted=%q", res, b2.mounted)
	}
	b3 := newBoot()
	b3.key = "something else"
	b3.parts[0].tok, b3.parts[1].tok = nil, nil // nothing that is ours
	res, _ = Assemble(context.Background(), b3, assembleOpts(t))
	if res.State != "unavailable" || b3.asks != 0 {
		t.Fatalf("no set: %+v asks=%d", res, b3.asks)
	}
}
