// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"unicode"
)

// Plan is a dry run: the exact commands an approved action would run, and
// the safety checks behind them. This package never executes a plan.
type Plan struct {
	Kind        string    `json:"kind"` // create, protect, repair
	Mount       string    `json:"mount"`
	Targets     []DiskRef `json:"targets,omitempty"` // disks the plan writes to (wipes, for create/protect)
	Encrypted   bool      `json:"encrypted"`
	DataProfile string    `json:"data_profile,omitempty"`
	MetaProfile string    `json:"metadata_profile,omitempty"`
	Checks      []Check   `json:"checks"`
	Blocked     bool      `json:"blocked"` // a check failed: Steps is empty
	Warnings    []string  `json:"warnings,omitempty"`
	Steps       []Step    `json:"steps,omitempty"`
	SHA256      string    `json:"plan_sha256"` // binds the plan to these disks (id, size, serial) and commands
}

// DiskRef names a disk the way the approval screen shows it.
type DiskRef struct {
	Path       string `json:"path"`
	ID         string `json:"id"`
	Model      string `json:"model,omitempty"`
	SizeBytes  uint64 `json:"size_bytes"`
	SerialTail string `json:"serial_tail,omitempty"`
	Transport  string `json:"transport,omitempty"`
}

// Check is one data-safety check and its outcome.
type Check struct {
	ID     string `json:"id"`
	OK     bool   `json:"ok"`
	Detail string `json:"detail"`
}

// Step is one command. Destructive steps erase what is on a target disk.
type Step struct {
	Cmd         []string `json:"cmd"`
	Why         string   `json:"why"`
	Destructive bool     `json:"destructive,omitempty"`
}

// String renders the command for a shell, quoting where needed.
func (s Step) String() string {
	q := make([]string, len(s.Cmd))
	for i, a := range s.Cmd {
		if a == "" || strings.ContainsAny(a, " \t'\"$`\\;&|<>*?()") {
			a = "'" + strings.ReplaceAll(a, "'", `'\''`) + "'"
		}
		q[i] = a
	}
	return strings.Join(q, " ")
}

// PlanOptions are shared by the plan generators.
type PlanOptions struct {
	Mount   string // where the data set is (or will be) mounted, e.g. /data
	Label   string // filesystem label; default onemind-data
	Encrypt bool   // LUKS2 under each new member (create); protect follows the existing set
	// KeyFile unlocks new LUKS2 members in this slice. TPM2 enrolment and the
	// one-time recovery key replace it in STOR-1/STOR-2.
	KeyFile string
	Health  map[string]Health // by disk path; a failing disk blocks the plan
}

// MountOptions follow docs/umbrel2/storage.md §4.2.
const MountOptions = "noatime,compress=zstd:1,space_cache=v2,discard=async"

func (o *PlanOptions) defaults() {
	if o.Label == "" {
		o.Label = "onemind-data"
	}
	if o.Mount == "" {
		o.Mount = "/data"
	}
	if o.KeyFile == "" {
		o.KeyFile = "/run/onemind/storage/new-member.key"
	}
}

// metaProfile: raid1 at two disks, raid1c3 (three copies) at three or more.
func profilesFor(n int) (data, meta string) {
	switch {
	case n >= 3:
		return "raid1", "raid1c3"
	case n == 2:
		return "raid1", "raid1"
	default:
		return "single", "dup"
	}
}

// targetChecks are the checks every disk to be wiped must pass.
func targetChecks(d Disk, o PlanOptions) []Check {
	name := d.Path
	cs := []Check{
		{ID: "not-system:" + name, OK: d.Role != RoleSystem, Detail: string(d.Role)},
		{ID: "unused:" + name, OK: d.Role == RoleUnused, Detail: describeHolds(d)},
		{ID: "writable:" + name, OK: !d.ReadOnly, Detail: fmt.Sprintf("read_only=%t", d.ReadOnly)},
	}
	if h, ok := o.Health[d.Path]; ok {
		cs = append(cs, Check{ID: "healthy:" + name, OK: h.Verdict != VerdictCritical, Detail: string(h.Verdict) + reasons(h.Reasons)})
	}
	return cs
}

func describeHolds(d Disk) string {
	if len(d.Holds) == 0 {
		return "no partitions or filesystem signatures"
	}
	var parts []string
	for _, s := range d.Holds {
		p := s.Path + " " + s.Type
		if s.FSType != "" {
			p += " " + s.FSType
		}
		if s.Label != "" {
			p += " label=" + s.Label
		}
		if len(s.Mountpoints) > 0 {
			p += " mounted at " + strings.Join(s.Mountpoints, ",")
		}
		parts = append(parts, p)
	}
	return "holds: " + strings.Join(parts, "; ")
}

func reasons(r []string) string {
	if len(r) == 0 {
		return ""
	}
	return ": " + strings.Join(r, "; ")
}

// partPath is the first partition of a disk (nvme0n1 → nvme0n1p1, sdb → sdb1).
func partPath(disk string) string {
	if r := []rune(disk); unicode.IsDigit(r[len(r)-1]) {
		return disk + "p1"
	}
	return disk + "1"
}

// mapperName is stable per disk: onemind-data-<serial tail or kernel name>.
func mapperName(d Disk) string {
	t := d.SerialTail
	if t == "" {
		t = d.Path[strings.LastIndex(d.Path, "/")+1:]
	}
	return "onemind-data-" + strings.ToLower(t)
}

// prepareMember partitions a disk and, when encrypting, opens LUKS2 on it.
// It returns the steps and the block device btrfs should use.
func prepareMember(d Disk, o PlanOptions) ([]Step, string) {
	part := partPath(d.Path)
	steps := []Step{
		{Cmd: []string{"sgdisk", "--zap-all", d.Path}, Why: "erase the partition tables on " + label(d), Destructive: true},
		{Cmd: []string{"sgdisk", "--new=1:0:0", "--typecode=1:" + typecode(o.Encrypt), "--change-name=1:" + o.Label, d.Path}, Why: "one partition over the whole disk, labelled " + o.Label + " so it is found by label, not by sdX order", Destructive: true},
		{Cmd: []string{"udevadm", "settle"}, Why: "wait for the kernel to create " + part},
	}
	if !o.Encrypt {
		return steps, part
	}
	mapper := mapperName(d)
	steps = append(steps,
		Step{Cmd: []string{"cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--key-file", o.KeyFile, part}, Why: "LUKS2 encryption on the new member", Destructive: true},
		Step{Cmd: []string{"cryptsetup", "open", "--key-file", o.KeyFile, part, mapper}, Why: "unlock it as /dev/mapper/" + mapper},
	)
	return steps, "/dev/mapper/" + mapper
}

func typecode(enc bool) string {
	if enc {
		return "8309" // Linux LUKS
	}
	return "8300" // Linux filesystem
}

func label(d Disk) string {
	s := d.Path
	if d.Model != "" {
		s += " (" + d.Model
		if d.SerialTail != "" {
			s += ", serial …" + d.SerialTail
		}
		s += ")"
	}
	return s
}

func ref(d Disk) DiskRef {
	return DiskRef{Path: d.Path, ID: d.ID, Model: d.Model, SizeBytes: d.SizeBytes, SerialTail: d.SerialTail, Transport: d.Transport}
}

// PlanCreate plans a new data set on blank disks: raid1 with two, raid1
// data plus raid1c3 metadata with three or more. One disk gives an
// unprotected set (single data, dup metadata) with a warning.
func PlanCreate(disks []Disk, devices []string, o PlanOptions) Plan {
	o.defaults()
	p := Plan{Kind: "create", Mount: o.Mount, Encrypted: o.Encrypt}
	var targets []Disk
	seen := map[string]bool{}
	for _, ref := range devices {
		d, ok := Find(disks, ref)
		p.Checks = append(p.Checks, Check{ID: "exists:" + ref, OK: ok, Detail: "whole disk from lsblk"})
		if !ok || seen[d.Path] {
			if ok {
				p.Checks = append(p.Checks, Check{ID: "distinct:" + ref, OK: false, Detail: "listed twice"})
			}
			continue
		}
		seen[d.Path] = true
		targets = append(targets, d)
		p.Checks = append(p.Checks, targetChecks(d, o)...)
	}
	p.DataProfile, p.MetaProfile = profilesFor(len(targets))
	p.Checks = append(p.Checks, Check{ID: "no-parity-raid", OK: true, Detail: "profiles " + p.DataProfile + "/" + p.MetaProfile + "; raid5/6 are never generated"})
	if len(targets) == 1 {
		p.Warnings = append(p.Warnings, "one disk: the data has one copy; add a second disk to protect it")
	}
	warnSizes(&p, targets)
	var members []string
	for _, d := range targets {
		p.Targets = append(p.Targets, ref(d))
		st, dev := prepareMember(d, o)
		p.Steps = append(p.Steps, st...)
		members = append(members, dev)
	}
	mkfs := append([]string{"mkfs.btrfs", "--label", o.Label, "--data", p.DataProfile, "--metadata", p.MetaProfile}, members...)
	p.Steps = append(p.Steps,
		Step{Cmd: mkfs, Why: "one btrfs filesystem across the members", Destructive: true},
		Step{Cmd: []string{"mkdir", "-p", o.Mount}, Why: "mount point"},
	)
	if len(members) > 0 {
		p.Steps = append(p.Steps, Step{Cmd: []string{"mount", "-o", MountOptions, members[0], o.Mount}, Why: "mount the set (any member mounts all of them)"})
	}
	for _, sv := range []string{"@", "@storage", "@snapshots"} {
		p.Steps = append(p.Steps, Step{Cmd: []string{"btrfs", "subvolume", "create", o.Mount + "/" + sv}, Why: "subvolume layout (storage.md §4.2)"})
	}
	p.Steps = append(p.Steps, Step{Cmd: []string{"btrfs", "filesystem", "df", o.Mount}, Why: "verify: every line shows the planned profile"})
	return finish(p)
}

// PlanProtect plans adding one blank disk to the mounted set and converting
// it to raid1 (raid1c3 metadata at three disks). On a set that is already
// raid1 it is the "add" operation.
func PlanProtect(disks []Disk, m *Mirror, device string, o PlanOptions) Plan {
	o.defaults()
	o.Mount = m.Mount
	p := Plan{Kind: "protect", Mount: m.Mount}
	mounted := m.State != StateUnavailable
	p.Checks = append(p.Checks, Check{ID: "set-mounted", OK: mounted, Detail: m.Mount + " " + string(m.State) + reasons(m.Reasons)})
	missing := 0
	var allocated uint64
	for _, mem := range m.Members {
		if mem.Missing {
			missing++
		}
		allocated += mem.UsedBytes
	}
	p.Checks = append(p.Checks,
		Check{ID: "no-missing-members", OK: missing == 0, Detail: fmt.Sprintf("%d missing; reconnect or replace first", missing)},
		Check{ID: "no-parity-raid", OK: m.State != StateUnsupported, Detail: string(m.State)},
	)
	d, ok := Find(disks, device)
	p.Checks = append(p.Checks, Check{ID: "exists:" + device, OK: ok, Detail: "whole disk from lsblk"})
	if ok {
		p.Checks = append(p.Checks, targetChecks(d, o)...)
		// Each raid1 chunk needs a copy on a different disk. With one member
		// today, the new disk must hold everything already allocated.
		need := allocated
		if len(m.Members) >= 2 {
			need = 0
		}
		p.Checks = append(p.Checks, Check{ID: "big-enough:" + d.Path, OK: d.SizeBytes >= need,
			Detail: fmt.Sprintf("disk %d bytes, needs at least %d (allocated on the current member)", d.SizeBytes, need)})
		// Follow the set: encrypt the new member when the existing ones are.
		for _, mem := range m.Members {
			if _, s, ok := containing(disks, mem.Path); ok && s.Type == "crypt" || strings.HasPrefix(mem.Path, "/dev/mapper/") {
				o.Encrypt = true
			}
		}
		p.Encrypted = o.Encrypt
		if !o.Encrypt {
			p.Warnings = append(p.Warnings, "the existing set is not encrypted, so the new member is not either (LUKS2 for every member lands with STOR-1)")
		}
		if d.Transport == "usb" {
			p.Warnings = append(p.Warnings, "USB disk: keep it connected; an unplug makes the set degraded")
		}
		p.Targets = []DiskRef{ref(d)}
	}
	p.DataProfile, p.MetaProfile = profilesFor(len(m.Members) + 1)
	if ok {
		warnSizes(&p, append(diskOfMembers(disks, m), d))
		st, dev := prepareMember(d, o)
		p.Steps = append(st,
			Step{Cmd: []string{"btrfs", "device", "add", dev, m.Mount}, Why: "join the new member to the set"},
			Step{Cmd: []string{"btrfs", "balance", "start", "-dconvert=" + p.DataProfile + ",soft", "-mconvert=" + p.MetaProfile + ",soft", m.Mount},
				Why: "write a second copy of every chunk on the other disk (soft: skips chunks already converted, so a restart after a power cut resumes)"},
			Step{Cmd: []string{"btrfs", "filesystem", "df", m.Mount}, Why: "verify: Data, Metadata and System show the new profile"},
		)
	}
	return finish(p)
}

// PlanRepair plans bringing a degraded set back to protected after its
// missing member is connected again: scrub (rewrites stale copies on the
// returned disk from the good one) then a soft-convert balance (rewrites
// single-copy chunks created while degraded).
func PlanRepair(m *Mirror) Plan {
	p := Plan{Kind: "repair", Mount: m.Mount}
	missing := 0
	for _, mem := range m.Members {
		if mem.Missing {
			missing++
		}
	}
	p.DataProfile, p.MetaProfile = profilesFor(len(m.Members))
	p.Checks = append(p.Checks,
		Check{ID: "set-mounted", OK: m.State != StateUnavailable, Detail: string(m.State)},
		Check{ID: "all-members-present", OK: missing == 0, Detail: fmt.Sprintf("%d missing: reconnect it and remount (replace comes with STOR-4)", missing)},
		Check{ID: "no-parity-raid", OK: m.State != StateUnsupported, Detail: string(m.State)},
	)
	if m.State == StateProtected {
		p.Warnings = append(p.Warnings, "already protected; the scrub still verifies every checksum")
	}
	if m.Degraded {
		p.Warnings = append(p.Warnings, "mounted with -o degraded: remount without it once the member is back, so a new failure is not silent")
	}
	p.Steps = []Step{
		{Cmd: []string{"btrfs", "scrub", "start", "-B", m.Mount}, Why: "read every copy, verify checksums and rewrite bad or stale copies from the good one"},
		{Cmd: []string{"btrfs", "balance", "start", "-dconvert=" + p.DataProfile + ",soft", "-mconvert=" + p.MetaProfile + ",soft", m.Mount},
			Why: "rewrite chunks written with one copy while degraded; soft skips chunks already mirrored"},
		{Cmd: []string{"btrfs", "filesystem", "df", m.Mount}, Why: "verify: no single or dup lines remain"},
		{Cmd: []string{"btrfs", "device", "stats", "--reset", m.Mount}, Why: "record and zero the error counters after the repair so new errors stand out"},
	}
	if m.NeedsScrub {
		p.Steps = append(p.Steps, Step{Cmd: []string{"rm", "-f", m.Mount + "/" + NeedsScrubMarker}, Why: "clear the degraded marker: the scrub verified every copy"})
	}
	return finish(p)
}

func diskOfMembers(disks []Disk, m *Mirror) []Disk {
	var out []Disk
	for _, mem := range m.Members {
		if d, _, ok := containing(disks, mem.Path); ok {
			out = append(out, d)
		}
	}
	return out
}

// warnSizes: raid1 usable space is limited by the smallest pair; mixed
// sizes still work (unlike a classic mirror), the plan says how much.
func warnSizes(p *Plan, ds []Disk) {
	if len(ds) < 2 {
		return
	}
	var total, max uint64
	for _, d := range ds {
		total += d.SizeBytes
		if d.SizeBytes > max {
			max = d.SizeBytes
		}
	}
	usable := total / 2
	if rest := total - max; rest < usable {
		usable = rest
	}
	if usable < total/2 {
		p.Warnings = append(p.Warnings, fmt.Sprintf("mixed sizes: about %d bytes usable with two copies; the rest of the largest disk stays unused", usable))
	}
}

// finish blocks the plan when a check failed and seals it with plan_sha256.
func finish(p Plan) Plan {
	for _, c := range p.Checks {
		if !c.OK {
			p.Blocked = true
		}
	}
	if p.Blocked {
		p.Steps = nil
	}
	p.SHA256 = ""
	b, _ := json.Marshal(struct {
		Kind, Mount, Data, Meta string
		Encrypted               bool
		Targets                 []DiskRef
		Steps                   []Step
	}{p.Kind, p.Mount, p.DataProfile, p.MetaProfile, p.Encrypted, p.Targets, p.Steps})
	sum := sha256.Sum256(b)
	p.SHA256 = hex.EncodeToString(sum[:])
	return p
}
