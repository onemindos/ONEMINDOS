// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
)

// Boot assembly of the data set (UMB-STOR-2, storage.md §4.3-§4.4,
// docs/leap/core/STORAGE-ACT-os.patch.md): `onemindd storage assemble` runs
// in the signed, read-only root before local-fs.target and
//
//  1. formats a blank onemind-data partition on the system disk (first boot,
//     H-11) when asked to;
//  2. finds every LUKS2 partition labelled onemind-data whose OneMind token
//     names that very partition (a header copied onto another disk does not
//     count), picks the system disk's set and its newest generation;
//  3. unlocks each member with TPM2 (the systemd-tpm2 token) or else the
//     recovery key, asked once and cached for the other members;
//  4. waits for late disks, retries with older-generation members of the
//     same set, then mounts degraded (marker needs-scrub) or, when nothing
//     mounts, puts a tmpfs on the mount point and leaves the unavailable
//     marker, so the box boots into storage recovery mode instead of failing.

// Candidate is one onemind-data partition seen at boot.
type Candidate struct {
	Part     string         `json:"part"`
	PartUUID string         `json:"partuuid"`
	Disk     string         `json:"disk"`
	System   bool           `json:"system_disk"`
	Token    *storage.Token `json:"token,omitempty"`
	Skip     string         `json:"skipped,omitempty"`
}

// Choose picks the set to assemble: the one with a member on the system
// disk, else the newest. It returns its members at the newest generation and
// the older ones (which may still hold chunks after an interrupted operation).
func Choose(cands []Candidate) (set string, current, stale []Candidate, skipped []Candidate) {
	var valid []Candidate
	for _, c := range cands {
		switch {
		case c.Token == nil:
			c.Skip = "no OneMind token"
		case c.Token.PartUUID == "" || !strings.EqualFold(c.Token.PartUUID, c.PartUUID):
			c.Skip = "the token names another partition (a copied header)"
		}
		if c.Skip != "" {
			skipped = append(skipped, c)
			continue
		}
		valid = append(valid, c)
	}
	best := -1
	for _, c := range valid {
		if c.System {
			set = c.Token.SetUUID
			break
		}
		if c.Token.Generation > best {
			best, set = c.Token.Generation, c.Token.SetUUID
		}
	}
	gen := 0
	for _, c := range valid {
		if c.Token.SetUUID == set && c.Token.Generation > gen {
			gen = c.Token.Generation
		}
	}
	for _, c := range valid {
		switch {
		case c.Token.SetUUID != set:
			c.Skip = "belongs to another set (foreign)"
			skipped = append(skipped, c)
		case c.Token.Generation == gen:
			current = append(current, c)
		default:
			c.Skip = fmt.Sprintf("generation %d, the set is at %d", c.Token.Generation, gen)
			stale = append(stale, c)
		}
	}
	return set, current, stale, skipped
}

// AssembleOptions configure one boot assembly.
type AssembleOptions struct {
	Mount       string        // default /data
	Wait        time.Duration // for late members (USB, SAS); default 30 s
	KeyFile     string        // a file holding the recovery key (rescue and labs); else ask
	Init        bool          // format a blank onemind-data partition on the system disk
	MountNormal bool          // also mount when complete (else /etc/fstab's data.mount does)
	RunDir      string        // markers (degraded, unavailable); default storage.RunDir
	Log         *slog.Logger
}

// AssembleResult is printed as JSON by `onemindd storage assemble`.
type AssembleResult struct {
	State       string      `json:"state"` // ready, mounted, degraded, unavailable, empty
	Set         string      `json:"set_uuid,omitempty"`
	Members     []string    `json:"members,omitempty"`
	Stale       []string    `json:"stale_opened,omitempty"`
	Skipped     []Candidate `json:"skipped,omitempty"`
	Initialized bool        `json:"initialized,omitempty"`
	Detail      string      `json:"detail,omitempty"`
}

// MapperName is the mapping of a member: onemind-data for the system disk's
// (what /etc/fstab mounts), onemind-data-<partuuid prefix> for the others.
func MapperName(c Candidate) string {
	if c.System {
		return "onemind-data"
	}
	return "onemind-data-" + strings.ToLower(c.PartUUID[:min(8, len(c.PartUUID))])
}

// Assemble runs the boot assembly.
func Assemble(ctx context.Context, r Runner, o AssembleOptions) (AssembleResult, error) {
	if o.Mount == "" {
		o.Mount = "/data"
	}
	if o.Wait == 0 {
		o.Wait = 30 * time.Second
	}
	if o.RunDir == "" {
		o.RunDir = storage.RunDir
	}
	lg := o.Log
	if lg == nil {
		lg = slog.New(slog.NewTextHandler(os.Stderr, nil))
	}
	sr, ok := r.(storage.Runner)
	if !ok {
		sr = stdoutOf{r}
	}
	col := &storage.Collector{Run: sr}
	var res AssembleResult
	deadline := time.Now().Add(o.Wait)
	asked := ""
	var (
		stale          []Candidate
		missing, total int
		dev            string
		normalFailed   bool
	)
	opened := map[string]string{} // part → mapper
	failed := map[string]bool{}   // not retried in this boot: no repeated prompts
	for {
		cands, blank, err := candidates(ctx, col, r)
		if err != nil {
			return res, err
		}
		if blank != "" && o.Init && !res.Initialized {
			lg.Warn("first boot: formatting the data partition (LUKS2 + btrfs)", "part", blank)
			if _, err := InitData(ctx, r, storage.InitOptions{Part: blank, TPM2: storage.TPM2Present(), PCRKey: pcrKey()}, false); err != nil {
				return res, fmt.Errorf("first-boot format: %w", err)
			}
			res.Initialized = true
			continue
		}
		var set string
		var current, skipped []Candidate
		set, current, stale, skipped = Choose(cands)
		res.Set, res.Skipped = set, skipped
		if set == "" {
			if time.Now().Before(deadline) && len(cands) == 0 {
				time.Sleep(time.Second)
				continue
			}
			return unavailable(ctx, r, o, res, "no OneMind data set found")
		}
		for _, c := range current {
			if _, ok := opened[c.Part]; ok || failed[c.Part] {
				continue
			}
			name := MapperName(c)
			if err := openMember(ctx, r, c, name, o.KeyFile, &asked); err != nil {
				lg.Error("cannot unlock a member", "part", c.Part, "err", err)
				failed[c.Part] = true
				continue
			}
			opened[c.Part] = name
			lg.Info("member unlocked", "part", c.Part, "as", name, "generation", c.Token.Generation)
		}
		res.Members = mappers(opened)
		missing, total, dev = checkSet(ctx, r, opened)
		if dev != "" && missing == 0 && !normalFailed {
			if !o.MountNormal {
				res.State = "ready"
				return res, nil
			}
			err := mount(ctx, r, dev, o.Mount, "")
			if err == nil {
				res.State = "mounted"
				return res, nil
			}
			lg.Warn("normal mount failed; trying older-generation members, then degraded", "err", err)
			normalFailed = true
		}
		if missing > 0 && time.Now().Before(deadline) {
			time.Sleep(time.Second)
			continue
		}
		break
	}
	// Older-generation members of this set may still hold chunks (an
	// interrupted operation left a token behind): btrfs ignores a disk that
	// really left the set, so opening them is safe.
	for _, c := range stale {
		if _, ok := opened[c.Part]; ok {
			continue
		}
		name := MapperName(c)
		if openMember(ctx, r, c, name, o.KeyFile, &asked) == nil {
			opened[c.Part] = name
			res.Stale = append(res.Stale, c.Part)
		}
	}
	missing, total, dev = checkSet(ctx, r, opened)
	if dev == "" {
		return unavailable(ctx, r, o, res, "no member could be unlocked")
	}
	res.Members = mappers(opened)
	if missing == 0 && len(res.Stale) > 0 {
		res.Detail = "complete only with older-generation members: run a repair"
		if !o.MountNormal {
			res.State = "ready"
			return res, nil
		}
		if err := mount(ctx, r, dev, o.Mount, ""); err == nil {
			res.State = "mounted"
			return res, nil
		}
	}
	// btrfs itself refuses a degraded mount when the missing members held
	// the only copy of something (more missing than the profile tolerates).
	if err := mount(ctx, r, dev, o.Mount, "degraded"); err != nil {
		return unavailable(ctx, r, o, res, fmt.Sprintf("%d of %d members missing and the rest cannot hold the data: %v", missing, total, err))
	}
	_ = os.MkdirAll(filepath.Join(o.Mount, filepath.Dir(storage.NeedsScrubMarker)), 0o755)
	_ = os.WriteFile(filepath.Join(o.Mount, storage.NeedsScrubMarker), nil, 0o644)
	_ = storage.MakeRunDir(o.RunDir)
	_ = os.WriteFile(o.RunDir+"/degraded", nil, 0o644)
	res.State, res.Detail = "degraded", fmt.Sprintf("%d of %d members missing; mounted degraded, needs-scrub marker written", missing, total)
	return res, nil
}

func pcrKey() string {
	if _, err := os.Stat(storage.PCRPublicKey); err == nil {
		return storage.PCRPublicKey
	}
	return ""
}

func mappers(opened map[string]string) []string {
	var out []string
	for _, n := range opened {
		out = append(out, "/dev/mapper/"+n)
	}
	sort.Strings(out)
	return out
}

// candidates lists onemind-data partitions with their tokens, and a blank
// onemind-data partition on the system disk (first boot), if any.
func candidates(ctx context.Context, col *storage.Collector, r Runner) ([]Candidate, string, error) {
	disks, err := col.Inventory(ctx, nil)
	if err != nil {
		return nil, "", err
	}
	var out []Candidate
	blank := ""
	for _, d := range disks {
		for _, s := range d.Holds {
			if s.Type != "part" || s.PartLabel != "onemind-data" {
				continue
			}
			sys := d.Role == storage.RoleSystem
			if s.FSType == "" && sys {
				blank = s.Path
				continue
			}
			if s.FSType != "crypto_LUKS" {
				continue
			}
			c := Candidate{Part: s.Path, PartUUID: s.PartUUID, Disk: d.Path, System: sys}
			if b, code, err := r.Exec(ctx, "", "cryptsetup", "token", "export", "--token-id", fmt.Sprint(storage.TokenID), s.Path); err == nil && code == 0 {
				var t storage.Token
				if json.Unmarshal(b, &t) == nil && t.Type == storage.TokenType {
					c.Token = &t
				}
			}
			out = append(out, c)
		}
	}
	return out, blank, nil
}

// openMember unlocks with a token (TPM2) first, then the recovery key: from
// KeyFile, or asked once through systemd-ask-password and cached in the
// kernel keyring for the other members. The key goes to cryptsetup on stdin
// and is never logged.
func openMember(ctx context.Context, r Runner, c Candidate, name, keyFile string, asked *string) error {
	if _, code, err := r.Exec(ctx, "", "cryptsetup", "status", name); err == nil && code == 0 {
		return nil
	}
	if _, code, err := r.Exec(ctx, "", "cryptsetup", "open", "--token-only", c.Part, name); err == nil && code == 0 {
		return nil
	}
	if keyFile != "" {
		out, code, err := r.Exec(ctx, "", "cryptsetup", "open", "--key-file", keyFile, c.Part, name)
		if err != nil || code != 0 {
			return fmt.Errorf("cryptsetup open: %s", tail(out, 200))
		}
		return nil
	}
	for attempt := 0; attempt < 3; attempt++ {
		if *asked == "" || attempt > 0 {
			args := []string{"--id=onemind-data", "--keyname=onemind-data", "--timeout=0", "OneMind recovery key for the data disks:"}
			if attempt == 0 {
				args = append([]string{"--accept-cached"}, args...)
			}
			out, code, err := r.Exec(ctx, "", "systemd-ask-password", args...)
			if err != nil || code != 0 {
				return fmt.Errorf("no recovery key entered")
			}
			*asked = strings.TrimRight(string(out), "\n")
		}
		if _, code, err := r.Exec(ctx, *asked, "cryptsetup", "open", "--key-file=-", c.Part, name); err == nil && code == 0 {
			return nil
		}
	}
	return fmt.Errorf("the recovery key did not open %s", c.Part)
}

// checkSet scans for btrfs devices and reports, for the filesystem on the
// first opened member, how many devices are missing.
func checkSet(ctx context.Context, r Runner, opened map[string]string) (missing, total int, dev string) {
	if len(opened) == 0 {
		return 0, 0, ""
	}
	_, _, _ = r.Exec(ctx, "", "btrfs", "device", "scan")
	var names []string
	for _, n := range mappers(opened) { // the system disk's member first: that is what fstab mounts
		if n == "/dev/mapper/onemind-data" {
			names = append([]string{n}, names...)
		} else {
			names = append(names, n)
		}
	}
	for _, dev := range names {
		out, code, err := r.Exec(ctx, "", "btrfs", "filesystem", "show", "--raw", dev)
		if err != nil || code != 0 {
			continue
		}
		total, present, err := storage.ShowCounts(out)
		if err != nil {
			continue
		}
		return total - present, total, dev
	}
	return 0, 0, ""
}

func mount(ctx context.Context, r Runner, dev, at, extra string) error {
	opts := "subvol=@," + storage.MountOptions
	if extra != "" {
		opts += "," + extra
	}
	if err := os.MkdirAll(at, 0o755); err != nil {
		return err
	}
	out, code, err := r.Exec(ctx, "", "mount", "-o", opts, dev, at)
	if err != nil || code != 0 {
		return fmt.Errorf("mount: %s", tail(out, 200))
	}
	return nil
}

func unavailable(ctx context.Context, r Runner, o AssembleOptions, res AssembleResult, why string) (AssembleResult, error) {
	res.State, res.Detail = "unavailable", why
	_ = storage.MakeRunDir(o.RunDir)
	_ = os.WriteFile(o.RunDir+"/unavailable", []byte(why+"\n"), 0o644)
	_ = os.MkdirAll(o.Mount, 0o755)
	_, _, _ = r.Exec(ctx, "", "mount", "-t", "tmpfs", "-o", "mode=0755,size=256m", "onemind-recovery", o.Mount)
	return res, nil
}

// stdoutOf lets any Runner serve storage.Collector.
type stdoutOf struct{ r Runner }

func (s stdoutOf) Run(ctx context.Context, name string, args ...string) ([]byte, int, error) {
	return s.r.Exec(ctx, "", name, args...)
}
