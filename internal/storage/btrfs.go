// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// State of the data set (the contract proposal's storage.state).
type State string

const (
	StateProtected   State = "protected"   // every chunk has two or more copies on different disks
	StateUnprotected State = "unprotected" // one copy only (single or dup): a disk failure loses data
	StateDegraded    State = "degraded"    // a member is missing, or chunks written while degraded need repair
	StateUnavailable State = "unavailable" // nothing mounted at the path, or not btrfs
	StateUnsupported State = "unsupported" // raid5/raid6: never offered, needs the owner's attention
)

// Member is one device of the btrfs filesystem.
type Member struct {
	DevID     int              `json:"devid"`
	Path      string           `json:"path,omitempty"` // empty when missing
	Missing   bool             `json:"missing"`
	SizeBytes uint64           `json:"size_bytes"`
	UsedBytes uint64           `json:"allocated_bytes"`
	Errors    map[string]int64 `json:"errors"`              // write_io_errs, read_io_errs, flush_io_errs, corruption_errs, generation_errs
	Backing   string           `json:"backing,omitempty"`   // LUKS2 partition under a dm-crypt member (Collector.LUKS)
	LUKSUUID  string           `json:"luks_uuid,omitempty"` // that partition's LUKS UUID
	PartUUID  string           `json:"partuuid,omitempty"`  // that partition's GPT id
}

// Profile is one allocation class (Data, Metadata, System) and its profile.
type Profile struct {
	Kind       string `json:"kind"`    // Data, Metadata, System
	Profile    string `json:"profile"` // single, dup, raid1, raid1c3, ...
	TotalBytes uint64 `json:"total_bytes"`
	UsedBytes  uint64 `json:"used_bytes"`
}

// Mirror is the state of the btrfs data set mounted at Mount.
type Mirror struct {
	Mount        string    `json:"mount"`
	UUID         string    `json:"uuid,omitempty"`
	Label        string    `json:"label,omitempty"`
	Source       string    `json:"source,omitempty"`
	MountOptions []string  `json:"mount_options,omitempty"`
	Degraded     bool      `json:"mounted_degraded"`
	NeedsScrub   bool      `json:"needs_scrub"` // NeedsScrubMarker exists: the set ran degraded since its last repair
	UsedBytes    uint64    `json:"used_bytes"`
	Members      []Member  `json:"members"`
	Profiles     []Profile `json:"profiles"`
	State        State     `json:"state"`
	Reasons      []string  `json:"reasons,omitempty"`
	Repair       []string  `json:"repair,omitempty"` // what PlanRepair would do: "reconnect", "scrub", "soft-convert"
	Encrypted    bool      `json:"encrypted"`        // members are dm-crypt (Collector.LUKS)
	Generation   int       `json:"generation"`       // newest OneMind LUKS2 token generation; 0 = none
}

// NeedsScrubMarker (relative to the mount) records that the set was mounted
// degraded. btrfs gives no lasting sign of it once the member is back:
// writes made while degraded also land in existing raid1 chunks, leaving
// stale copies on the returned disk that only a scrub finds (lab: 260 334
// checksum errors corrected, research-output/evidence/lab/storage-mirror).
// The initrd assembly unit writes it on a degraded mount (STOR-2); the
// repair plan removes it after the scrub. This package only reads it.
const NeedsScrubMarker = "onemind/storage/needs-scrub"

var statFile = os.Stat

// MirrorStatus reads the btrfs set mounted at mount. The returned error is
// for a tool that could not run; an unmounted path is StateUnavailable.
func (c *Collector) MirrorStatus(ctx context.Context, mount string) (*Mirror, error) {
	m := &Mirror{Mount: mount}
	out, code, err := c.Run.Run(ctx, "findmnt", "--json", "--mountpoint", mount, "-o", "SOURCE,FSTYPE,OPTIONS,UUID")
	if err != nil {
		return nil, fmt.Errorf("findmnt: %w", err)
	}
	if code != 0 {
		m.State, m.Reasons = StateUnavailable, []string{"nothing is mounted at " + mount}
		return m, nil
	}
	if err := parseFindmnt(out, m); err != nil {
		return nil, err
	}
	if m.State == StateUnavailable {
		return m, nil
	}
	for _, step := range []struct {
		args  []string
		parse func([]byte, *Mirror) error
	}{
		{[]string{"filesystem", "show", "--raw", mount}, parseShow},
		{[]string{"filesystem", "df", "-b", mount}, parseDF},
		{[]string{"device", "stats", mount}, parseStats},
	} {
		out, code, err := c.Run.Run(ctx, "btrfs", step.args...)
		if err != nil {
			return nil, fmt.Errorf("btrfs %s: %w", strings.Join(step.args[:2], " "), err)
		}
		// device stats exits 64 when an error counter is non-zero (-c only);
		// any other non-zero exit is a real failure.
		if code != 0 {
			return nil, fmt.Errorf("btrfs %s exited %d", strings.Join(step.args[:2], " "), code)
		}
		if err := step.parse(out, m); err != nil {
			return nil, err
		}
	}
	if _, err := statFile(filepath.Join(mount, NeedsScrubMarker)); err == nil {
		m.NeedsScrub = true
	}
	Evaluate(m)
	return m, nil
}

func parseFindmnt(data []byte, m *Mirror) error {
	var doc struct {
		Filesystems []struct {
			Source, FSType, Options, UUID string
		} `json:"filesystems"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return fmt.Errorf("findmnt JSON: %w", err)
	}
	if len(doc.Filesystems) == 0 || doc.Filesystems[0].FSType != "btrfs" {
		m.State, m.Reasons = StateUnavailable, []string{m.Mount + " is not a btrfs filesystem"}
		return nil
	}
	f := doc.Filesystems[0]
	m.Source, m.UUID = f.Source, f.UUID
	m.MountOptions = strings.Split(f.Options, ",")
	for _, o := range m.MountOptions {
		if o == "degraded" {
			m.Degraded = true
		}
	}
	return nil
}

var (
	reLabel = regexp.MustCompile(`^Label:\s+(?:'(.*)'|none)\s+uuid:\s+(\S+)`)
	reUsed  = regexp.MustCompile(`FS bytes used (\d+)`)
	reDev   = regexp.MustCompile(`^\s*devid\s+(\d+)\s+size\s+(\d+)\s+used\s+(\d+)\s+path\s*(.*)$`)
	reDF    = regexp.MustCompile(`^(\w+), (\w+): total=(\d+), used=(\d+)`)
	reStat  = regexp.MustCompile(`^\[(.+)\]\.(\w+)\s+(-?\d+)`)
)

// parseShow reads `btrfs filesystem show --raw` (btrfs-progs 6.x).
func parseShow(data []byte, m *Mirror) error {
	sc := bufio.NewScanner(bytes.NewReader(data))
	for sc.Scan() {
		line := sc.Text()
		if g := reLabel.FindStringSubmatch(line); g != nil {
			m.Label = g[1]
			if m.UUID == "" {
				m.UUID = g[2]
			}
		}
		if g := reUsed.FindStringSubmatch(line); g != nil {
			m.UsedBytes, _ = strconv.ParseUint(g[1], 10, 64)
		}
		if g := reDev.FindStringSubmatch(line); g != nil {
			id, _ := strconv.Atoi(g[1])
			size, _ := strconv.ParseUint(g[2], 10, 64)
			used, _ := strconv.ParseUint(g[3], 10, 64)
			path := strings.TrimSpace(g[4])
			missing := strings.HasSuffix(path, "MISSING") || strings.Contains(path, "<missing")
			if missing {
				path = ""
			}
			m.Members = append(m.Members, Member{DevID: id, Path: path, Missing: missing, SizeBytes: size, UsedBytes: used, Errors: map[string]int64{}})
		}
	}
	if len(m.Members) == 0 {
		return fmt.Errorf("btrfs filesystem show: no devices in output")
	}
	sort.Slice(m.Members, func(i, j int) bool { return m.Members[i].DevID < m.Members[j].DevID })
	return nil
}

// parseDF reads `btrfs filesystem df -b`. GlobalReserve is an in-memory
// reservation, not stored chunks, so it is left out.
func parseDF(data []byte, m *Mirror) error {
	sc := bufio.NewScanner(bytes.NewReader(data))
	for sc.Scan() {
		g := reDF.FindStringSubmatch(sc.Text())
		if g == nil || g[1] == "GlobalReserve" {
			continue
		}
		total, _ := strconv.ParseUint(g[3], 10, 64)
		used, _ := strconv.ParseUint(g[4], 10, 64)
		m.Profiles = append(m.Profiles, Profile{Kind: g[1], Profile: strings.ToLower(g[2]), TotalBytes: total, UsedBytes: used})
	}
	return nil
}

// parseStats reads `btrfs device stats`: lines "[/dev/x].write_io_errs 0",
// or "[devid:2]..." for a missing member.
func parseStats(data []byte, m *Mirror) error {
	sc := bufio.NewScanner(bytes.NewReader(data))
	for sc.Scan() {
		g := reStat.FindStringSubmatch(sc.Text())
		if g == nil {
			continue
		}
		v, _ := strconv.ParseInt(g[3], 10, 64)
		for i := range m.Members {
			mem := &m.Members[i]
			if (mem.Path != "" && mem.Path == g[1]) || g[1] == "devid:"+strconv.Itoa(mem.DevID) {
				mem.Errors[g[2]] = v
			}
		}
	}
	return nil
}

// redundant profiles keep a copy on another disk.
var redundant = map[string]bool{"raid1": true, "raid1c3": true, "raid1c4": true, "raid10": true}

// Evaluate sets State, Reasons and Repair from the parsed facts.
func Evaluate(m *Mirror) {
	m.Reasons, m.Repair = nil, nil
	missing := 0
	for _, mem := range m.Members {
		if mem.Missing {
			missing++
		}
		for k, v := range mem.Errors {
			if v > 0 {
				m.Reasons = append(m.Reasons, fmt.Sprintf("devid %d: %s=%d", mem.DevID, k, v))
			}
		}
	}
	sort.Strings(m.Reasons)
	kinds := map[string]map[string]bool{}
	for _, p := range m.Profiles {
		if p.Profile == "raid5" || p.Profile == "raid6" {
			m.State = StateUnsupported
			m.Reasons = append(m.Reasons, p.Kind+" uses "+p.Profile+", which OneMind never offers (write-hole risk)")
			return
		}
		if kinds[p.Kind] == nil {
			kinds[p.Kind] = map[string]bool{}
		}
		kinds[p.Kind][p.Profile] = true
	}
	anyRedundant, single := false, []string{}
	for _, k := range []string{"Data", "Metadata", "System"} {
		for prof := range kinds[k] {
			if redundant[prof] {
				anyRedundant = true
			} else {
				single = append(single, k+" "+prof)
			}
		}
	}
	sort.Strings(single)
	switch {
	case missing > 0:
		m.State = StateDegraded
		m.Reasons = append(m.Reasons, fmt.Sprintf("%d of %d disks missing", missing, len(m.Members)))
		m.Repair = append(m.Repair, "reconnect")
		if len(single) > 0 {
			m.Reasons = append(m.Reasons, "single-copy chunks written while degraded: "+strings.Join(single, ", "))
		}
		m.Repair = append(m.Repair, "scrub", "soft-convert")
	case m.NeedsScrub && len(m.Members) >= 2:
		m.State = StateDegraded
		m.Reasons = append(m.Reasons, "the set ran degraded since its last repair: the returned disk may hold stale copies until a scrub")
		if len(single) > 0 {
			m.Reasons = append(m.Reasons, "single-copy chunks need converting: "+strings.Join(single, ", "))
		}
		m.Repair = append(m.Repair, "scrub", "soft-convert")
	case len(m.Members) >= 2 && anyRedundant && len(single) > 0:
		// A returned member: data written during the degraded period has
		// one copy until a soft-convert balance rewrites it.
		m.State = StateDegraded
		m.Reasons = append(m.Reasons, "single-copy chunks need converting: "+strings.Join(single, ", "))
		m.Repair = append(m.Repair, "scrub", "soft-convert")
	case len(m.Members) >= 2 && len(single) == 0 && anyRedundant:
		m.State = StateProtected
		if m.Degraded {
			// Mounted with -o degraded but every member present: harmless,
			// yet the option lets a later failure go silent. Remount.
			m.Reasons = append(m.Reasons, "mounted with the degraded option although all disks are present; remount without it")
		}
	default:
		m.State = StateUnprotected
		m.Reasons = append(m.Reasons, "one copy of the data only: a disk failure loses it")
	}
}

// MembersFromShow parses `btrfs filesystem show --raw` for one filesystem.
func MembersFromShow(data []byte) ([]Member, error) {
	m := &Mirror{}
	if err := parseShow(data, m); err != nil {
		return nil, err
	}
	return m.Members, nil
}

var reTotal = regexp.MustCompile(`Total devices (\d+)`)

// ShowCounts reads `btrfs filesystem show --raw` for one filesystem: how many
// devices it has and how many are present. For a filesystem that is not
// mounted, btrfs-progs does not list a missing device at all; it prints only
// the total and "*** Some devices missing" (Debian 13 VM lab, log 27).
func ShowCounts(data []byte) (total, present int, err error) {
	g := reTotal.FindSubmatch(data)
	if g == nil {
		return 0, 0, fmt.Errorf("btrfs filesystem show: no device total")
	}
	total, _ = strconv.Atoi(string(g[1]))
	mem, err := MembersFromShow(data)
	if err != nil {
		return total, 0, err
	}
	for _, m := range mem {
		if !m.Missing {
			present++
		}
	}
	return total, present, nil
}
