// SPDX-License-Identifier: Apache-2.0

package host

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/onemindos/onemindos/internal/storage/ops"
)

// Factory reset, the box's half (#146 UMB-P09, HOST-ACTIONS.md section 4).
//
// FAST WIPE (founder, 2026-11-21): destroy the encryption keys of every disk
// of the data set (cryptsetup erase removes every LUKS2 keyslot, so the data
// can never be decrypted again) and clear the signatures, then set the box up
// again. The disks are not overwritten. That is only true when the data is
// encrypted: on a box whose /data is not LUKS2 yet (F-61/F-62), the reset is
// refused with that reason. It never falls back to a slow overwrite and never
// pretends to have wiped.

// PlanSchema names the plan document.
const PlanSchema = "onemind.host.factory-reset-plan/v1"

// ResetWarning is shown to the owner with the plan, and is part of what the
// passkey approval is bound to (it is inside the plan hash).
const ResetWarning = "This erases everything on this box: apps, settings, the owner and passkeys, " +
	"and the box's identity, on every disk listed below. It is a fast wipe: the encryption keys are destroyed, " +
	"so the data can never be read again, but the disks are not overwritten. " +
	"Backups kept off this box (other disks, other machines, the cloud) are not erased. " +
	"Restoring them afterwards needs the printed recovery key, because this box's own backup key is wiped with it. " +
	"If you do not have that recovery key, do not continue."

// ResetErases and ResetSurvives say what the wipe touches (HOST-ACTIONS.md section 4).
var (
	ResetErases = []string{
		"apps and their data", "the k3s cluster state", "settings, users and passkeys",
		"the box's certificate authority and identity", "tokens and the backup device key",
		"local backup snapshots", "the first-boot settings file on the boot partition",
	}
	ResetSurvives = []string{
		"both system versions (A and B) and the bootloader state",
		"backups stored off this box (other disks, other machines, the cloud): restoring them needs the printed recovery key",
		"disks that do not belong to this box's data set",
	}
)

// PlanMember is one disk partition of the data set. Every one is erased.
type PlanMember struct {
	Part       string `json:"part"`
	Disk       string `json:"disk"`
	PartUUID   string `json:"partuuid"`
	Generation int    `json:"generation"`
	SystemDisk bool   `json:"system_disk"`
	// Stale: an older-generation member of the set (a disk that left the
	// mirror but still holds readable data) is wiped too.
	Stale bool `json:"stale,omitempty"`
}

// ResetPlan is what a factory reset would do on this box right now.
// SHA256 covers everything else in it; the owner's approval is bound to it.
type ResetPlan struct {
	Schema    string       `json:"schema"`
	Available bool         `json:"available"`
	Refusal   string       `json:"refusal,omitempty"` // why not, when !Available
	Method    string       `json:"method"`
	SetUUID   string       `json:"set_uuid,omitempty"`
	Members   []PlanMember `json:"members"`
	Erases    []string     `json:"erases"`
	Survives  []string     `json:"survives"`
	Warning   string       `json:"warning"`
	SHA256    string       `json:"plan_sha256"`
}

// candidates is the disk discovery (tests replace it).
var candidates = ops.Candidates

const resetMethod = "fast wipe: destroy the LUKS2 encryption keys of every member, then clear its signatures"

func (p *ResetPlan) seal() {
	p.SHA256 = ""
	b, _ := json.Marshal(p)
	h := sha256.Sum256(b)
	p.SHA256 = hex.EncodeToString(h[:])
}

func refusedPlan(why string) ResetPlan {
	p := ResetPlan{Schema: PlanSchema, Refusal: why, Method: resetMethod, Members: []PlanMember{},
		Erases: ResetErases, Survives: ResetSurvives, Warning: ResetWarning}
	p.seal()
	return p
}

// BuildPlan turns the disks seen at boot into the plan. A box whose data is
// not LUKS2 gets a refused plan that says so.
func BuildPlan(cands []ops.Candidate) ResetPlan {
	set, current, stale, _ := ops.Choose(cands)
	if set == "" || len(current) == 0 {
		return refusedPlan("the data on this box is not encrypted yet (no LUKS2 data set was found), " +
			"so the fast wipe cannot run and nothing was changed. A slow overwrite is deliberately not offered; " +
			"the encrypted data disk is tracked as F-61/F-62")
	}
	p := ResetPlan{Schema: PlanSchema, Available: true, Method: resetMethod, SetUUID: set,
		Erases: ResetErases, Survives: ResetSurvives, Warning: ResetWarning}
	for _, c := range current {
		p.Members = append(p.Members, member(c, false))
	}
	for _, c := range stale {
		p.Members = append(p.Members, member(c, true))
	}
	sort.Slice(p.Members, func(i, j int) bool { return p.Members[i].PartUUID < p.Members[j].PartUUID })
	p.seal()
	return p
}

func member(c ops.Candidate, stale bool) PlanMember {
	return PlanMember{Part: c.Part, Disk: c.Disk, PartUUID: strings.ToLower(c.PartUUID),
		Generation: c.Token.Generation, SystemDisk: c.System, Stale: stale}
}

// Marker is the file on the ESP that tells the next boot to wipe. The ESP is
// not part of the data set, so it survives the wipe.
type Marker struct {
	ActionID    string
	RequestedAt time.Time
	DataSet     string // the set's UUID: a marker never wipes another disk set
	PlanSHA256  string
	ExpiresAt   time.Time
	State       string // "" armed, "wiping"
	Attempts    int
	// Members are the approved plan's disks (PARTUUID and generation). The
	// wipe erases exactly these and refuses unless every one is found.
	Members []MarkerMember
	// Erased are the members already done, so a retry after a power cut
	// knows which are left (an erased member has no token to find).
	Erased []string
}

// MarkerMember is one approved plan member as the marker stores it.
type MarkerMember struct {
	PartUUID   string
	Generation int
}

const (
	MarkerName     = "onemind/factory-reset"
	MarkerDoneName = "onemind/factory-reset.done"
	// PendingName is the ESP note an update trial writes (rauc-pre-install).
	PendingName = "onemind/pending"
	// AppliedName is the first-boot settings file, which can hold a join code.
	AppliedName = "onemind.conf.applied"
	// MarkerWindow is how long an armed reset stays valid.
	MarkerWindow = time.Hour
)

var markerValueRe = regexp.MustCompile(`^[A-Za-z0-9_.:+-]{0,128}$`)

func (m Marker) encode() []byte {
	var b strings.Builder
	w := func(k, v string) { fmt.Fprintf(&b, "%s=%s\n", k, v) }
	w("ACTION_ID", m.ActionID)
	w("REQUESTED_AT", m.RequestedAt.UTC().Format(time.RFC3339))
	w("DATA_SET", m.DataSet)
	w("PLAN_SHA256", m.PlanSHA256)
	w("EXPIRES_AT", m.ExpiresAt.UTC().Format(time.RFC3339))
	w("STATE", m.State)
	w("ATTEMPTS", strconv.Itoa(m.Attempts))
	for _, mm := range m.Members {
		w("MEMBER", mm.PartUUID+":"+strconv.Itoa(mm.Generation))
	}
	for _, e := range m.Erased {
		w("ERASED", e)
	}
	return []byte(b.String())
}

// ParseMarker reads a marker; anything malformed is an error (the wipe then
// goes to recovery mode instead of guessing).
func ParseMarker(b []byte) (Marker, error) {
	var m Marker
	kv := map[string]string{}
	var memberLines, erasedLines []string
	sc := bufio.NewScanner(strings.NewReader(string(b)))
	for sc.Scan() {
		k, v, ok := strings.Cut(strings.TrimSpace(sc.Text()), "=")
		if !ok || !markerValueRe.MatchString(v) {
			return m, fmt.Errorf("bad marker line %q", sc.Text())
		}
		switch k {
		case "MEMBER":
			memberLines = append(memberLines, v)
		case "ERASED":
			erasedLines = append(erasedLines, strings.ToLower(v))
		default:
			kv[k] = v
		}
	}
	var err error
	if m.RequestedAt, err = time.Parse(time.RFC3339, kv["REQUESTED_AT"]); err != nil {
		return m, errors.New("marker has no valid REQUESTED_AT")
	}
	if m.ExpiresAt, err = time.Parse(time.RFC3339, kv["EXPIRES_AT"]); err != nil {
		return m, errors.New("marker has no valid EXPIRES_AT")
	}
	m.Attempts, _ = strconv.Atoi(kv["ATTEMPTS"])
	m.ActionID, m.DataSet, m.PlanSHA256, m.State = kv["ACTION_ID"], kv["DATA_SET"], kv["PLAN_SHA256"], kv["STATE"]
	if m.ActionID == "" || m.DataSet == "" {
		return m, errors.New("marker has no ACTION_ID or DATA_SET")
	}
	for _, l := range memberLines {
		id, g, ok := strings.Cut(l, ":")
		gen, gerr := strconv.Atoi(g)
		if !ok || id == "" || gerr != nil {
			return m, fmt.Errorf("bad MEMBER %q", l)
		}
		m.Members = append(m.Members, MarkerMember{PartUUID: strings.ToLower(id), Generation: gen})
	}
	m.Erased = erasedLines
	return m, nil
}

// writeAtomic: temp file, fsync, rename, fsync of the folder (the same
// discipline as the action journal).
func writeAtomic(path string, data []byte) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	f, err := os.CreateTemp(dir, ".tmp-*")
	if err != nil {
		return err
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, err := f.Write(data); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		return err
	}
	d, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}

// FactoryReset is the Resetter of `onemindd host serve`: it plans from the
// real disks and arms the marker on the ESP. The wipe itself is Wipe, run by
// onemind-factory-reset.service early in the next boot.
type FactoryReset struct {
	ESP         string     // ESP mount, default /boot/efi
	Run         ops.Runner // default ops.ExecRunner
	Now         func() time.Time
	StorageBusy func() string // why a storage operation is running, or ""

	mu     sync.Mutex
	cached ResetPlan
	at     time.Time
}

func (f *FactoryReset) esp() string {
	if f.ESP != "" {
		return f.ESP
	}
	return "/boot/efi"
}

func (f *FactoryReset) now() time.Time {
	if f.Now != nil {
		return f.Now().UTC()
	}
	return time.Now().UTC()
}

func (f *FactoryReset) runner() ops.Runner {
	if f.Run != nil {
		return f.Run
	}
	return ops.ExecRunner{}
}

// Plan implements Resetter.
func (f *FactoryReset) Plan(ctx context.Context) ResetPlan {
	cands, err := candidates(ctx, f.runner())
	if err != nil {
		return refusedPlan("the disks cannot be inspected, so nothing can be listed or wiped: " + err.Error())
	}
	p := BuildPlan(cands)
	f.mu.Lock()
	f.cached, f.at = p, f.now()
	f.mu.Unlock()
	return p
}

// Unavailable implements Resetter. Status is polled, so a plan up to 20 s old is reused.
func (f *FactoryReset) Unavailable() string {
	f.mu.Lock()
	p, fresh := f.cached, !f.at.IsZero() && f.now().Sub(f.at) < 20*time.Second
	f.mu.Unlock()
	if !fresh {
		p = f.Plan(context.Background())
	}
	if !p.Available {
		return p.Refusal
	}
	return ""
}

// Arm implements Resetter.
func (f *FactoryReset) Arm(ctx context.Context, op Op) error {
	p := f.Plan(ctx)
	switch {
	case !p.Available:
		return errors.New(p.Refusal)
	case p.SHA256 != op.PlanSHA256:
		return errors.New("the disks changed since the approved plan")
	}
	if f.StorageBusy != nil {
		if why := f.StorageBusy(); why != "" {
			return errors.New(why)
		}
	}
	if _, err := os.Stat(filepath.Join(f.esp(), PendingName)); err == nil {
		return errors.New("an OS update trial is waiting for its verdict; a rollback could move the box onto a system without the wipe")
	}
	now := f.now()
	m := Marker{ActionID: op.ID, RequestedAt: now, DataSet: p.SetUUID, PlanSHA256: p.SHA256, ExpiresAt: now.Add(MarkerWindow)}
	for _, pm := range p.Members {
		m.Members = append(m.Members, MarkerMember{PartUUID: pm.PartUUID, Generation: pm.Generation})
	}
	return writeAtomic(filepath.Join(f.esp(), MarkerName), m.encode())
}

// Wipe outcomes the early-boot unit maps onto the boot.
var (
	ErrNoMarker    = errors.New("no factory reset is armed")
	ErrStaleMarker = errors.New("the armed factory reset does not match this boot (expired, or another disk set): nothing was wiped")
	// ErrMembersMissing: a disk of the approved plan did not show up in time.
	// Nothing is wiped, so the box never reports a reset that left a member
	// readable; the marker stays and the box goes to recovery mode.
	ErrMembersMissing = errors.New("a disk of the approved factory reset plan was not found")
)

var (
	// wipeWait is how long the wipe waits for late disks (USB, SAS), the same
	// 30 s the data assembly waits.
	wipeWait = 30 * time.Second
	wipePoll = time.Second
)

// Wipe runs the armed reset: fast-wipes every member of the approved plan,
// removes the first-boot settings file, and renames the marker to .done. Every
// step can be repeated, so a power cut just means the next boot starts again;
// the marker goes only after the last step. It wipes nothing when an armed
// marker is expired or names another disk set (ErrStaleMarker), or when a
// planned member (PARTUUID and generation) is still missing after the wait
// (ErrMembersMissing). A marker already in the wiping state is a retry of an
// approved reset, so the expiry does not apply to it. It never wipes a disk
// outside the plan.
func Wipe(ctx context.Context, r ops.Runner, esp string, now time.Time) error {
	path := filepath.Join(esp, MarkerName)
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return ErrNoMarker
	} else if err != nil {
		return err
	}
	m, err := ParseMarker(b)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrStaleMarker, err)
	}
	if m.State != "wiping" && now.After(m.ExpiresAt) {
		return ErrStaleMarker
	}
	if len(m.Members) == 0 {
		return fmt.Errorf("%w: the marker lists no disks", ErrStaleMarker)
	}
	erased := map[string]bool{}
	for _, e := range m.Erased {
		erased[e] = true
	}
	deadline := time.Now().Add(wipeWait)
	var cands, targets []ops.Candidate
	for {
		if cands, err = candidates(ctx, r); err != nil {
			return err
		}
		var missing []string
		targets = targets[:0]
		for _, mm := range m.Members {
			if erased[mm.PartUUID] {
				continue
			}
			found := false
			for _, c := range cands {
				if c.Token != nil && strings.EqualFold(c.PartUUID, mm.PartUUID) && strings.EqualFold(c.Token.PartUUID, mm.PartUUID) &&
					c.Token.SetUUID == m.DataSet && c.Token.Generation == mm.Generation {
					targets, found = append(targets, c), true
					break
				}
			}
			if !found {
				missing = append(missing, mm.PartUUID)
			}
		}
		if len(missing) == 0 {
			break
		}
		if !time.Now().Before(deadline) || ctx.Err() != nil {
			return fmt.Errorf("%w: %s (nothing was wiped; the marker stays)", ErrMembersMissing, strings.Join(missing, ", "))
		}
		select {
		case <-ctx.Done():
		case <-time.After(wipePoll):
		}
	}
	// The first run needs this box's own set to be the marker's. A retry has
	// already erased some members, so the system disk may be blank by now.
	if set, _, _, _ := ops.Choose(cands); m.State != "wiping" && set != m.DataSet {
		return ErrStaleMarker
	}
	// A disk of the set that is not in the approved plan appeared since the
	// approval: wiping it was never approved, and leaving it readable would
	// break the reset, so stop and let the owner decide.
	planned := map[string]bool{}
	for _, mm := range m.Members {
		planned[mm.PartUUID] = true
	}
	for _, c := range cands {
		if c.Token != nil && c.Token.SetUUID == m.DataSet && !planned[strings.ToLower(c.PartUUID)] {
			return fmt.Errorf("%w: %s is a member of the data set that the approved plan does not list", ErrStaleMarker, c.Part)
		}
	}
	m.State, m.Attempts = "wiping", m.Attempts+1
	if err := writeAtomic(path, m.encode()); err != nil {
		return err
	}
	for _, c := range targets {
		if out, code, err := r.Exec(ctx, "", "cryptsetup", "erase", "--batch-mode", c.Part); err != nil || code != 0 {
			return fmt.Errorf("cryptsetup erase %s failed: %s", c.Part, strings.TrimSpace(string(out)))
		}
		if out, code, err := r.Exec(ctx, "", "wipefs", "-a", c.Part); err != nil || code != 0 {
			return fmt.Errorf("wipefs %s failed: %s", c.Part, strings.TrimSpace(string(out)))
		}
		m.Erased = append(m.Erased, strings.ToLower(c.PartUUID))
		if err := writeAtomic(path, m.encode()); err != nil {
			return err
		}
	}
	if err := os.Remove(filepath.Join(esp, AppliedName)); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	done := fmt.Sprintf("ACTION_ID=%s\nCOMPLETED_AT=%s\n", m.ActionID, now.UTC().Format(time.RFC3339))
	if err := writeAtomic(filepath.Join(esp, MarkerDoneName), []byte(done)); err != nil {
		return err
	}
	return os.Remove(path)
}
