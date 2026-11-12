// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"unicode"

	"github.com/onemindos/onemindos/internal/storage"
)

func partOf(disk string) string {
	if r := []rune(disk); len(r) > 0 && unicode.IsDigit(r[len(r)-1]) {
		return disk + "p1"
	}
	return disk + "1"
}

// targetsAndRefs records the disks the plan prepares and, for every device
// path in its commands, a key that finds the same device after a reboot:
// GPT partition ids (written by the plan for new members, read from lsblk for
// existing ones) and stable disk ids (WWN, serial). Kernel names are not
// stable: two virtio disks can swap vdb and vdc across a boot.
func targetsAndRefs(p storage.Plan, disks []storage.Disk) ([]Target, map[string]Ref) {
	var targets []Target
	refs := map[string]Ref{}
	newMappers := map[string]bool{}
	for _, s := range p.Steps {
		if s.ID == "luks-open" {
			newMappers["/dev/mapper/"+s.Cmd[len(s.Cmd)-1]] = true
		}
		if s.ID != "partition" {
			continue
		}
		disk := s.Cmd[len(s.Cmd)-1]
		t := Target{Path: disk, Part: partOf(disk), DiskID: disk}
		for _, a := range s.Cmd {
			if g, ok := strings.CutPrefix(a, "--partition-guid=1:"); ok {
				t.PartUUID = strings.ToLower(g)
			}
		}
		if d, ok := storage.Find(disks, disk); ok {
			t.DiskID, t.Size, t.Model = d.ID, d.SizeBytes, d.Model
		}
		targets = append(targets, t)
		refs[t.Path] = Ref{Kind: "disk", Key: t.PartUUID}
		refs[t.Part] = Ref{Kind: "part", Key: t.PartUUID}
	}
	for _, s := range p.Steps {
		for _, a := range s.Cmd {
			if !strings.HasPrefix(a, "/dev/") || newMappers[a] {
				continue
			}
			if _, ok := refs[a]; ok {
				continue
			}
			for _, d := range disks {
				if d.Path == a && d.ID != d.Path {
					refs[a] = Ref{Kind: "disk-id", Key: d.ID}
				}
				for _, sig := range d.Holds {
					if sig.Path != a {
						continue
					}
					switch {
					case sig.Type == "part" && sig.PartUUID != "":
						refs[a] = Ref{Kind: "part", Key: sig.PartUUID}
					case sig.Type == "crypt":
						if pu := partUUIDOf(disks, sig.Parent); pu != "" {
							refs[a] = Ref{Kind: "mapper", Key: pu}
						}
					}
				}
			}
		}
	}
	return targets, refs
}

func partUUIDOf(disks []storage.Disk, part string) string {
	for _, d := range disks {
		for _, s := range d.Holds {
			if s.Path == part {
				return s.PartUUID
			}
		}
	}
	return ""
}

func resolveRef(disks []storage.Disk, r Ref) (string, bool) {
	switch r.Kind {
	case "part", "disk", "mapper":
		d, s, ok := storage.PartitionByUUID(disks, r.Key)
		if !ok {
			return "", false
		}
		switch r.Kind {
		case "part":
			return s.Path, true
		case "disk":
			return d.Path, true
		default:
			c, ok := storage.CryptChild(d, s.Path)
			return c.Path, ok
		}
	case "disk-id":
		d, ok := storage.Find(disks, r.Key)
		return d.Path, ok
	}
	return "", false
}

// relocate rewrites the operation's device paths to where the same devices
// are now. A target whose partition was not created yet is found only at
// its old path, blank, with the same size and model. Anything else missing
// is an error: the caller rolls back or asks for attention.
func (e *Engine) relocate(ctx context.Context, op *Op) error {
	if len(op.Refs) == 0 {
		return nil
	}
	m, err := e.Facts.Mirror(ctx, e.Mount)
	if err != nil {
		return err
	}
	disks, err := e.Facts.Disks(ctx, m)
	if err != nil {
		return err
	}
	subst := map[string]string{}
	var gone []string
	for old, r := range op.Refs {
		cur, ok := resolveRef(disks, r)
		if ok {
			if cur != old {
				subst[old] = cur
			}
			continue
		}
		switch r.Kind {
		case "disk", "part":
			if t, isTarget := targetFor(op, old); isTarget {
				if d, ok := storage.Find(disks, t.Path); ok && d.SizeBytes == t.Size && d.Model == t.Model && d.Role == storage.RoleUnused {
					continue // not partitioned yet; same blank disk at the same path
				}
				gone = append(gone, fmt.Sprintf("target disk %s (%s)", t.Path, t.DiskID))
				continue
			}
			gone = append(gone, old)
		case "mapper":
			// an existing member's mapping: the boot may not have opened it
			// under this name; its partition ref is checked separately
		default:
			gone = append(gone, old)
		}
	}
	if len(gone) > 0 {
		sort.Strings(gone)
		return fmt.Errorf("not found any more: %s", strings.Join(dedupe(gone), ", "))
	}
	if len(subst) == 0 {
		return nil
	}
	e.substitute(op, subst)
	return nil
}

// substitute rewrites device paths in the operation (all steps, targets and
// refs) and records it.
func (e *Engine) substitute(op *Op, subst map[string]string) {
	var moved []string
	for o, n := range subst {
		moved = append(moved, o+"→"+n)
	}
	sort.Strings(moved)
	e.update(op, func() {
		for i := range op.Plan.Steps {
			for j, a := range op.Plan.Steps[i].Cmd {
				if n, ok := subst[a]; ok {
					op.Plan.Steps[i].Cmd[j] = n
				}
			}
		}
		for i := range op.Targets {
			if n, ok := subst[op.Targets[i].Path]; ok {
				op.Targets[i].Path = n
			}
			if n, ok := subst[op.Targets[i].Part]; ok {
				op.Targets[i].Part = n
			}
		}
		refs := map[string]Ref{}
		for o, r := range op.Refs {
			if n, ok := subst[o]; ok {
				o = n
			}
			refs[o] = r
		}
		op.Refs = refs
		op.Relocated = append(op.Relocated, moved...)
	})
	e.log().Warn("storage operation: device paths changed since the plan was made", "op", op.ID, "moved", strings.Join(moved, ", "))
}

func targetFor(op *Op, path string) (Target, bool) {
	for _, t := range op.Targets {
		if t.Path == path || t.Part == path {
			return t, true
		}
	}
	return Target{}, false
}

func dedupe(s []string) []string {
	var out []string
	for i, v := range s {
		if i == 0 || v != s[i-1] {
			out = append(out, v)
		}
	}
	return out
}

// rollback returns the set and the target disks to how they were before the
// operation: the new member leaves the set (nothing was moved onto it yet),
// its mapping closes, and the target is blanked again. It only blanks a disk
// that provably is the target (our partition id, or its stable disk id).
func (e *Engine) rollback(ctx context.Context, op *Op, why string) {
	e.update(op, func() {
		op.State = StateRollingBack
		if op.Error == "" {
			op.Error = why
		}
	})
	e.log().Warn("storage operation rolling back", "op", op.ID, "why", why)
	mount := op.Plan.Mount
	undo := func(args ...string) bool {
		out, code, err := e.Run.Exec(ctx, "", args[0], args[1:]...)
		if ctx.Err() != nil {
			return false
		}
		e.update(op, func() { op.Rollback = append(op.Rollback, RollbackRun{Cmd: args, Exit: code, Output: tail(out, 500)}) })
		return err == nil && code == 0
	}
	stuck := func(msg string) { e.finish(op, StateNeedsAttention, why+"; rollback: "+msg) }

	m, err := e.Facts.Mirror(ctx, mount)
	if err != nil {
		stuck(err.Error())
		return
	}
	for _, s := range op.Plan.Steps {
		if s.ID == "device-add" && isMember(m, s.Cmd[3]) {
			if !undo("btrfs", "device", "remove", s.Cmd[3], mount) {
				if ctx.Err() == nil {
					stuck("could not take " + s.Cmd[3] + " out of the set")
				}
				return
			}
		}
	}
	for _, s := range op.Plan.Steps {
		if s.ID != "luks-open" {
			continue
		}
		name := s.Cmd[len(s.Cmd)-1]
		if _, code, err := e.Run.Exec(ctx, "", "cryptsetup", "status", name); err == nil && code == 0 {
			if !undo("cryptsetup", "close", name) {
				if ctx.Err() == nil {
					stuck("could not close " + name)
				}
				return
			}
		}
	}
	if m, err = e.Facts.Mirror(ctx, mount); err != nil {
		stuck(err.Error())
		return
	}
	disks, err := e.Facts.Disks(ctx, m)
	if err != nil {
		stuck(err.Error())
		return
	}
	for _, t := range op.Targets {
		d, s, ours := storage.PartitionByUUID(disks, t.PartUUID)
		if !ours && t.DiskID != t.Path {
			d, ours = storage.Find(disks, t.DiskID)
		}
		if !ours {
			continue // gone, or never partitioned: nothing of ours on it
		}
		if d.Role == storage.RoleMember || d.Role == storage.RoleSystem || d.Role == storage.RoleInUse {
			stuck(fmt.Sprintf("%s is %s; not wiping it", d.Path, d.Role))
			return
		}
		if s.Path != "" && !undo("wipefs", "--all", s.Path) {
			if ctx.Err() == nil {
				stuck("wipefs " + s.Path)
			}
			return
		}
		if !undo("sgdisk", "--zap-all", d.Path) {
			if ctx.Err() == nil {
				stuck("sgdisk " + d.Path)
			}
			return
		}
	}
	e.finish(op, StateRolledBack, why)
}
