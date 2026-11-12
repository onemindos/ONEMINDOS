// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"fmt"
	"strconv"
	"strings"
)

// FindMember resolves ref to a member of the set: "devid:2" or "2", the
// member's device path (/dev/mapper/x or /dev/vdb1), "missing" (the one
// missing member), or a whole disk (path or id) that holds the member.
func FindMember(disks []Disk, m *Mirror, ref string) (Member, bool) {
	if ref == "" {
		return Member{}, false
	}
	if ref == "missing" {
		var found []Member
		for _, mem := range m.Members {
			if mem.Missing {
				found = append(found, mem)
			}
		}
		if len(found) == 1 {
			return found[0], true
		}
		return Member{}, false
	}
	if id, err := strconv.Atoi(strings.TrimPrefix(ref, "devid:")); err == nil {
		for _, mem := range m.Members {
			if mem.DevID == id {
				return mem, true
			}
		}
		return Member{}, false
	}
	d, diskOK := Find(disks, ref)
	for _, mem := range m.Members {
		if mem.Path == "" {
			continue
		}
		if mem.Path == ref || mem.Backing == ref {
			return mem, true
		}
		if owner, _, ok := containing(disks, mem.Path); diskOK && ok && owner.Path == d.Path {
			return mem, true
		}
	}
	return Member{}, false
}

func describeMember(disks []Disk, mem Member) string {
	if mem.Missing {
		return fmt.Sprintf("devid %d (missing)", mem.DevID)
	}
	if d, _, ok := containing(disks, mem.Path); ok {
		return fmt.Sprintf("devid %d on %s", mem.DevID, label(d))
	}
	return fmt.Sprintf("devid %d at %s", mem.DevID, mem.Path)
}

// PlanReplace plans swapping one member (failed, missing or healthy) for a
// blank disk with `btrfs replace`, which copies the member's chunks straight
// onto the new disk (reading the mirror copy when the old one is gone). The
// new disk keeps the old devid. wipeOld erases the old member's LUKS2 header
// and signatures afterwards when it is still attached.
func PlanReplace(disks []Disk, m *Mirror, old, device string, wipeOld bool, o PlanOptions) Plan {
	o.Mount = m.Mount
	o.defaults()
	p := Plan{Kind: "replace", Mount: m.Mount}
	p.DataProfile, p.MetaProfile = profilesFor(len(m.Members))
	p.Checks = append(p.Checks,
		Check{ID: "set-mounted", OK: m.State != StateUnavailable, Detail: m.Mount + " " + string(m.State) + reasons(m.Reasons)},
		Check{ID: "no-parity-raid", OK: m.State != StateUnsupported, Detail: string(m.State)},
	)
	mem, memOK := FindMember(disks, m, old)
	p.Checks = append(p.Checks, Check{ID: "member:" + old, OK: memOK, Detail: "a member of the set (devid, device, disk or \"missing\")"})
	missingOthers := 0
	for _, x := range m.Members {
		if x.Missing && x.DevID != mem.DevID {
			missingOthers++
		}
	}
	p.Checks = append(p.Checks, Check{ID: "one-missing-at-most", OK: missingOthers == 0, Detail: fmt.Sprintf("%d other members missing", missingOthers)})
	if memOK && mem.Missing && len(m.Members) < 2 {
		p.Checks = append(p.Checks, Check{ID: "copy-exists", OK: false, Detail: "the only member is missing: nothing to copy from"})
	}
	d, ok := Find(disks, device)
	p.Checks = append(p.Checks, Check{ID: "exists:" + device, OK: ok, Detail: "whole disk from lsblk"})
	if !ok || !memOK {
		return finish(p)
	}
	p.Checks = append(p.Checks, targetChecks(d, o)...)
	p.Checks = append(p.Checks, Check{ID: "big-enough:" + d.Path, OK: d.SizeBytes >= mem.SizeBytes,
		Detail: fmt.Sprintf("disk %d bytes, the member it replaces is %d (btrfs replace needs at least that)", d.SizeBytes, mem.SizeBytes)})
	var clone string
	var encOK bool
	o.Encrypt, clone, encOK = followEncryption(disks, m, mem.DevID)
	p.Encrypted = o.Encrypt
	if o.Encrypt {
		p.Checks = append(p.Checks, Check{ID: "luks-source", OK: encOK, Detail: "another unlocked member's LUKS2 partition to copy the header from: " + clone})
	}
	p.Targets = []DiskRef{ref(d)}
	p.Warnings = append(p.Warnings, "replacing "+describeMember(disks, mem))
	if d.Transport == "usb" {
		p.Warnings = append(p.Warnings, "USB disk: keep it connected; an unplug makes the set degraded")
	}
	st, nm := prepareMember(d, o, m.UUID, clone)
	p.Steps = st
	if o.Encrypt {
		// The old member stays current until the replace has finished: a
		// power cut mid-replace must boot with it unlocked (the kernel
		// resumes the replace at mount and may still read from it).
		p.Steps = append(p.Steps, TokenSteps(m, nm, -1, m.Generation+1, PhasePrepare)...)
	}
	src := strconv.Itoa(mem.DevID)
	p.Steps = append(p.Steps,
		Step{ID: "replace", Phase: PhaseCommit, Cmd: []string{"btrfs", "replace", "start", "-B", "-f", src, nm.Dev, m.Mount},
			Why: "copy every chunk of devid " + src + " onto the new disk (from the mirror copy when the old disk is gone); a power cut resumes it at the next mount"},
		Step{ID: "resize", Phase: PhaseCommit, Cmd: []string{"btrfs", "filesystem", "resize", src + ":max", m.Mount}, Why: "use the whole new disk when it is bigger"},
		Step{ID: "balance", Phase: PhaseCommit, Cmd: []string{"btrfs", "balance", "start", "-dconvert=" + p.DataProfile + ",soft", "-mconvert=" + p.MetaProfile + ",soft", m.Mount},
			Why: "rewrite any chunk written with one copy while the set was degraded; soft skips chunks already mirrored"},
	)
	if o.Encrypt {
		// Now the old member leaves the set for the boot assembly too.
		p.Steps = append(p.Steps, TokenSteps(m, nm, mem.DevID, m.Generation+2, PhaseCommit)...)
	}
	if !mem.Missing && mem.Backing != "" {
		p.Steps = append(p.Steps, Step{ID: "old-close", Phase: PhaseCommit, Cmd: []string{"cryptsetup", "close", mem.Path}, Why: "lock the replaced member"})
	}
	if wipeOld && !mem.Missing {
		p.Steps = append(p.Steps, wipeMemberSteps(disks, mem)...)
	}
	p.Steps = append(p.Steps, verifyStep(m.Mount))
	if m.NeedsScrub {
		p.Warnings = append(p.Warnings, "the set ran degraded before: run a repair (scrub) afterwards so the other members are verified too")
	}
	return finish(p)
}

// wipeMemberSteps erase a removed member's LUKS2 keyslots and signatures so
// the disk is blank (and no longer opens with the set's keys).
func wipeMemberSteps(disks []Disk, mem Member) []Step {
	var steps []Step
	part := mem.Backing
	if part == "" {
		part = mem.Path
	}
	if mem.Backing != "" {
		steps = append(steps, Step{ID: "old-erase", Phase: PhaseCommit, Cmd: []string{"cryptsetup", "erase", "--batch-mode", mem.Backing},
			Why: "destroy the removed member's keyslots: the set's keys no longer open it", Destructive: true})
	}
	steps = append(steps, Step{ID: "old-wipefs", Phase: PhaseCommit, Cmd: []string{"wipefs", "--all", part}, Why: "remove filesystem signatures", Destructive: true})
	if d, _, ok := containing(disks, part); ok && d.Path != part {
		steps = append(steps, Step{ID: "old-zap", Phase: PhaseCommit, Cmd: []string{"sgdisk", "--zap-all", d.Path}, Why: "blank partition table on " + label(d), Destructive: true})
	}
	return steps
}

// PlanRemove plans taking one member out of the set: btrfs moves its chunks
// to the other members first. Going below two members loses protection and
// needs unprotect; the profile is converted to single/dup before the device
// leaves. Three to two converts raid1c3 metadata to raid1 first (btrfs will
// not go below three devices on raid1c3). A missing member is removed with
// "btrfs device remove missing". wipe erases the removed disk.
func PlanRemove(disks []Disk, m *Mirror, old string, unprotect, wipe bool, o PlanOptions) Plan {
	o.Mount = m.Mount
	o.defaults()
	p := Plan{Kind: "remove", Mount: m.Mount}
	p.Checks = append(p.Checks,
		Check{ID: "set-mounted", OK: m.State != StateUnavailable, Detail: m.Mount + " " + string(m.State)},
		Check{ID: "no-parity-raid", OK: m.State != StateUnsupported, Detail: string(m.State)},
	)
	mem, ok := FindMember(disks, m, old)
	p.Checks = append(p.Checks, Check{ID: "member:" + old, OK: ok, Detail: "a member of the set (devid, device, disk or \"missing\")"})
	n := len(m.Members)
	remaining := n - 1
	p.DataProfile, p.MetaProfile = profilesFor(remaining)
	p.Checks = append(p.Checks, Check{ID: "keeps-a-member", OK: remaining >= 1, Detail: fmt.Sprintf("%d members left", remaining)})
	p.Checks = append(p.Checks, Check{ID: "keeps-protection", OK: remaining >= 2 || unprotect,
		Detail: fmt.Sprintf("%d members left; one member keeps one copy of the data (set unprotect to accept)", remaining)})
	if !ok || remaining < 1 {
		return finish(p)
	}
	otherMissing := 0
	var raw, rest, biggest uint64
	for _, x := range m.Members {
		raw += x.UsedBytes
		if x.DevID == mem.DevID {
			continue
		}
		if x.Missing {
			otherMissing++
			continue
		}
		rest += x.SizeBytes
		if x.SizeBytes > biggest {
			biggest = x.SizeBytes
		}
	}
	p.Checks = append(p.Checks, Check{ID: "others-present", OK: otherMissing == 0, Detail: fmt.Sprintf("%d other members missing", otherMissing)})
	// Conservative space check with 10 % headroom (btrfs needs room to
	// balance): with two or more left, every chunk needs two copies on
	// different disks; with one left, raid1 data (raw/2) becomes single.
	need := raw + raw/10
	fits := rest >= need && rest-biggest >= need/2
	if remaining == 1 {
		need = raw/2 + raw/10
		fits = rest >= need
	}
	p.Checks = append(p.Checks, Check{ID: "fits-on-the-rest", OK: fits,
		Detail: fmt.Sprintf("%d bytes allocated; the remaining members have %d", raw, rest)})
	if remaining == 1 {
		p.Warnings = append(p.Warnings, "after this the data has one copy: a disk failure loses it")
	}
	p.Warnings = append(p.Warnings, "removing "+describeMember(disks, mem))
	if mem.Missing {
		p.Warnings = append(p.Warnings, "the member is missing: its chunks are rebuilt from the mirror copies")
	}
	if d, _, ok := containing(disks, mem.Path); ok {
		p.Targets = []DiskRef{ref(d)}
	}
	if remaining == 1 {
		p.Steps = append(p.Steps, Step{ID: "balance", Phase: PhaseCommit, Cmd: []string{"btrfs", "balance", "start", "-f", "-dconvert=single,soft", "-mconvert=dup,soft", "-sconvert=dup,soft", m.Mount},
			Why: "keep one data copy and two metadata copies on the disk that stays (-f: btrfs asks before lowering redundancy)"})
	} else if n == 3 {
		p.Steps = append(p.Steps, Step{ID: "balance", Phase: PhaseCommit, Cmd: []string{"btrfs", "balance", "start", "-f", "-mconvert=raid1,soft", "-sconvert=raid1,soft", m.Mount},
			Why: "metadata from three copies to two, so two disks can hold it"})
	}
	target := strconv.Itoa(mem.DevID)
	if mem.Missing {
		target = "missing"
	}
	p.Steps = append(p.Steps, Step{ID: "device-remove", Phase: PhaseCommit, Cmd: []string{"btrfs", "device", "remove", target, m.Mount},
		Why: "move every chunk off devid " + strconv.Itoa(mem.DevID) + " and drop it from the set; a restart continues where it stopped"})
	if m.Encrypted {
		p.Encrypted = true
		p.Steps = append(p.Steps, TokenSteps(m, newMember{}, mem.DevID, m.Generation+1, PhaseCommit)...)
	}
	if !mem.Missing && mem.Backing != "" {
		p.Steps = append(p.Steps, Step{ID: "old-close", Phase: PhaseCommit, Cmd: []string{"cryptsetup", "close", mem.Path}, Why: "lock the removed member"})
	}
	if wipe && !mem.Missing {
		p.Steps = append(p.Steps, wipeMemberSteps(disks, mem)...)
	}
	p.Steps = append(p.Steps, verifyStep(m.Mount))
	return finish(p)
}
