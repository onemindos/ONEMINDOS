// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
)

// Role says what a disk is used for, and so whether a plan may touch it.
type Role string

const (
	RoleSystem  Role = "system"   // holds /, /boot, /boot/efi, /usr or swap: never offered
	RoleMember  Role = "member"   // part of the btrfs data set being inspected
	RoleInUse   Role = "in-use"   // something on it is mounted
	RoleHasData Role = "has-data" // partitions or filesystem signatures, nothing mounted
	RoleUnused  Role = "unused"   // blank: the only role a plan may wipe
)

// Signature is a filesystem, partition or encryption layer found on a disk.
type Signature struct {
	Path        string   `json:"path"`
	Type        string   `json:"type"` // lsblk TYPE: part, crypt, ...
	FSType      string   `json:"fstype,omitempty"`
	Label       string   `json:"label,omitempty"`
	UUID        string   `json:"uuid,omitempty"`
	PartLabel   string   `json:"partlabel,omitempty"`
	Mountpoints []string `json:"mountpoints,omitempty"`
}

// Disk is one whole disk and everything stacked on it.
type Disk struct {
	ID         string      `json:"id"` // WWN, else serial, else the kernel path
	Path       string      `json:"path"`
	Model      string      `json:"model,omitempty"`
	Serial     string      `json:"serial,omitempty"`
	SerialTail string      `json:"serial_tail,omitempty"` // last 4 characters, what the UI shows
	WWN        string      `json:"wwn,omitempty"`
	Transport  string      `json:"transport,omitempty"` // nvme, sata, sas, usb, virtio, mmc...
	SizeBytes  uint64      `json:"size_bytes"`
	Rotational bool        `json:"rotational"`
	Removable  bool        `json:"removable"`
	ReadOnly   bool        `json:"read_only"`
	Role       Role        `json:"role"`
	Holds      []Signature `json:"holds,omitempty"` // the disk itself (if it has a signature) and every layer below it
}

// systemMounts mark a disk as the system disk.
var systemMounts = map[string]bool{"/": true, "/boot": true, "/boot/efi": true, "/efi": true, "/usr": true, "[SWAP]": true}

// LsblkArgs is the exact lsblk call (util-linux 2.37+ for MOUNTPOINTS).
var LsblkArgs = []string{"--json", "--bytes", "--paths", "-o",
	"NAME,KNAME,PKNAME,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,ROTA,RM,RO,FSTYPE,LABEL,UUID,PARTLABEL,MOUNTPOINTS"}

// Inventory lists whole disks. set (may be nil) marks the disks of the
// mounted data set as RoleMember, by filesystem UUID or by member device
// path: after `btrfs device add` udev does not re-probe the new member, so
// lsblk can still show it without a filesystem (seen in the lab).
func (c *Collector) Inventory(ctx context.Context, set *Mirror) ([]Disk, error) {
	out, code, err := c.Run.Run(ctx, "lsblk", LsblkArgs...)
	if err != nil {
		return nil, fmt.Errorf("lsblk: %w", err)
	}
	if code != 0 {
		return nil, fmt.Errorf("lsblk exited %d", code)
	}
	return ParseLsblk(out, set)
}

// flexBool accepts lsblk's booleans (true/false) and older "0"/"1" strings.
type flexBool bool

func (b *flexBool) UnmarshalJSON(p []byte) error {
	s := strings.Trim(string(p), `"`)
	*b = flexBool(s == "true" || s == "1")
	return nil
}

// flexUint accepts a number or a numeric string.
type flexUint uint64

func (u *flexUint) UnmarshalJSON(p []byte) error {
	s := strings.Trim(string(p), `"`)
	if s == "null" || s == "" {
		return nil
	}
	var v uint64
	if _, err := fmt.Sscan(s, &v); err != nil {
		return fmt.Errorf("size %q: %w", s, err)
	}
	*u = flexUint(v)
	return nil
}

type lsblkDev struct {
	Name        string     `json:"name"`
	Type        string     `json:"type"`
	Size        flexUint   `json:"size"`
	Model       *string    `json:"model"`
	Serial      *string    `json:"serial"`
	WWN         *string    `json:"wwn"`
	Tran        *string    `json:"tran"`
	Rota        flexBool   `json:"rota"`
	RM          flexBool   `json:"rm"`
	RO          flexBool   `json:"ro"`
	FSType      *string    `json:"fstype"`
	Label       *string    `json:"label"`
	UUID        *string    `json:"uuid"`
	PartLabel   *string    `json:"partlabel"`
	Mountpoints []*string  `json:"mountpoints"`
	Children    []lsblkDev `json:"children"`
}

func str(p *string) string {
	if p == nil {
		return ""
	}
	return strings.TrimSpace(*p)
}

// ParseLsblk turns `lsblk` JSON (LsblkArgs) into whole disks with roles.
// Loop, ROM and zram devices are left out.
func ParseLsblk(data []byte, set *Mirror) ([]Disk, error) {
	var doc struct {
		BlockDevices []lsblkDev `json:"blockdevices"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf("lsblk JSON: %w", err)
	}
	members := map[string]bool{}
	if set != nil && set.State != StateUnavailable {
		if set.UUID != "" {
			members[set.UUID] = true
		}
		for _, m := range set.Members {
			if m.Path != "" {
				members[m.Path] = true
			}
		}
	}
	var disks []Disk
	for _, d := range doc.BlockDevices {
		if d.Type != "disk" || strings.HasPrefix(d.Name, "/dev/zram") {
			continue
		}
		disk := Disk{
			Path: d.Name, Model: str(d.Model), Serial: str(d.Serial), WWN: str(d.WWN),
			Transport: str(d.Tran), SizeBytes: uint64(d.Size),
			Rotational: bool(d.Rota), Removable: bool(d.RM), ReadOnly: bool(d.RO),
		}
		disk.ID = firstNonEmpty(disk.WWN, disk.Serial, disk.Path)
		disk.SerialTail = tail(firstNonEmpty(disk.Serial, disk.WWN), 4)
		collect(d, &disk.Holds, true)
		disk.Role = roleOf(disk.Holds, members)
		disks = append(disks, disk)
	}
	return disks, nil
}

// collect records d (when it carries anything) and all its children.
func collect(d lsblkDev, out *[]Signature, top bool) {
	s := Signature{Path: d.Name, Type: d.Type, FSType: str(d.FSType), Label: str(d.Label), UUID: str(d.UUID), PartLabel: str(d.PartLabel)}
	for _, m := range d.Mountpoints {
		if v := str(m); v != "" {
			s.Mountpoints = append(s.Mountpoints, v)
		}
	}
	if !top || s.FSType != "" || len(s.Mountpoints) > 0 {
		*out = append(*out, s)
	}
	for _, c := range d.Children {
		collect(c, out, false)
	}
}

func roleOf(holds []Signature, members map[string]bool) Role {
	role := RoleUnused
	if len(holds) > 0 {
		role = RoleHasData
	}
	for _, s := range holds {
		for _, m := range s.Mountpoints {
			if systemMounts[m] {
				return RoleSystem
			}
		}
	}
	for _, s := range holds {
		if (s.FSType == "btrfs" && members[s.UUID]) || members[s.Path] {
			return RoleMember
		}
		if len(s.Mountpoints) > 0 {
			role = RoleInUse
		}
	}
	return role
}

// Find returns the disk whose path, kernel name or ID matches ref.
func Find(disks []Disk, ref string) (Disk, bool) {
	for _, d := range disks {
		if d.Path == ref || d.ID == ref || "/dev/"+ref == d.Path {
			return d, true
		}
	}
	return Disk{}, false
}

// containing returns the whole disk that holds device path p (a partition
// or a dm-crypt mapping), and the layer that matched.
func containing(disks []Disk, p string) (Disk, Signature, bool) {
	for _, d := range disks {
		if d.Path == p {
			return d, Signature{Path: p, Type: "disk"}, true
		}
		for _, s := range d.Holds {
			if s.Path == p {
				return d, s, true
			}
		}
	}
	return Disk{}, Signature{}, false
}

func firstNonEmpty(v ...string) string {
	for _, s := range v {
		if s != "" {
			return s
		}
	}
	return ""
}

func tail(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[len(s)-n:]
}
