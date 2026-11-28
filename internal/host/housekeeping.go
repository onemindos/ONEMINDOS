// SPDX-License-Identifier: Apache-2.0

package host

// Storage housekeeping (P-10): the weekly TRIM, what smartd has warned about, and the USB drives the owner may
// safely remove. The host service reads all three (it is root; the gateway is not) and ejects one drive when the
// owner approves it. Nothing here decides policy: the gateway files the request, an owner approves it, and this
// file checks again that the device is a removable disk that nothing the box needs lives on.

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// CmdRunner runs a command and returns its stdout and exit code (internal/storage.ExecRunner in production).
type CmdRunner interface {
	Run(ctx context.Context, name string, args ...string) (stdout []byte, exit int, err error)
}

// Media is the storage housekeeping side of the host service. Nil on a Service means the box has none.
type Media interface {
	Unavailable() string
	View(ctx context.Context) MediaView
	// CheckEject refuses (a *Refusal) unless device is a removable disk with nothing the box needs on it.
	// serial, when not empty, must match the drive's own serial number (the stick may have been swapped).
	CheckEject(ctx context.Context, device, serial string) error
	Eject(ctx context.Context, device, serial string) error
}

var deviceRe = regexp.MustCompile(`^/dev/[a-z][a-z0-9]{1,15}$`)

// TrimStatus is the weekly TRIM (fstrim.timer, limited to /data by the image).
type TrimStatus struct {
	Enabled    bool       `json:"enabled"`
	Timer      string     `json:"timer_state"`           // systemd ActiveState of fstrim.timer
	LastRun    *time.Time `json:"last_run_at"`           // when fstrim.service last finished; nil: never ran on this box
	LastResult string     `json:"last_result,omitempty"` // success, exit-code, ...
	LastBytes  *int64     `json:"last_trimmed_bytes"`    // from the service's own log line; nil when it did not say
	NextRun    *time.Time `json:"next_run_at"`
}

// SmartAlert is one warning smartd raised (its -M exec script, os/rootfs/layers/base/usr/lib/onemind/smartd-notify).
type SmartAlert struct {
	ID      string    `json:"id"` // stable for one warning: the gateway tells it once
	At      time.Time `json:"at"`
	Device  string    `json:"device"`
	Kind    string    `json:"kind"` // smartd's FAILTYPE: Health, FailedHealthCheck, Temperature, ...
	Message string    `json:"message"`
}

// SmartStatus is the smartd side.
type SmartStatus struct {
	Daemon string       `json:"daemon_state"` // systemd ActiveState of smartmontools.service ("inactive" in a VM: no disk to watch)
	Alerts []SmartAlert `json:"alerts"`       // newest first, at most maxAlerts
}

// Removable is a USB (or other removable) disk.
type Removable struct {
	Device     string   `json:"device"` // /dev/sdb
	Model      string   `json:"model,omitempty"`
	Serial     string   `json:"serial,omitempty"` // only when it is plain text; the eject request carries it
	SizeBytes  int64    `json:"size_bytes"`
	Label      string   `json:"label,omitempty"` // the first filesystem label
	Mounts     []string `json:"mountpoints"`
	Ejectable  bool     `json:"ejectable"`
	Why        string   `json:"why_not,omitempty"` // when not ejectable
	Partitions int      `json:"partitions"`
}

// MediaView is GET /v1/storage/housekeeping.
type MediaView struct {
	Trim      TrimStatus  `json:"trim"`
	Smart     SmartStatus `json:"smart"`
	Removable []Removable `json:"removable"`
	At        time.Time   `json:"at"`
}

const maxAlerts = 50

// Housekeeping is Media on the real box.
type Housekeeping struct {
	Run       CmdRunner
	AlertFeed string // the JSON-lines file smartd's script appends to
	Now       func() time.Time
	// CmdTimeout bounds each udisksctl call so a hung udisks cannot leave an eject "running" for ever (default 30 s).
	CmdTimeout time.Duration
}

func (h *Housekeeping) udisks(ctx context.Context, args ...string) ([]byte, int, error) {
	d := h.CmdTimeout
	if d <= 0 {
		d = 30 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, d)
	defer cancel()
	return h.Run.Run(ctx, "udisksctl", args...)
}

// DefaultAlertFeed lives on /data (a bind mount of /var/lib/smartmontools), so it survives reboots and A/B updates.
const DefaultAlertFeed = "/var/lib/smartmontools/onemind-alerts.jsonl"

func (h *Housekeeping) now() time.Time {
	if h.Now != nil {
		return h.Now().UTC()
	}
	return time.Now().UTC()
}

// Unavailable implements Media.
func (h *Housekeeping) Unavailable() string {
	if h.Run == nil {
		return "this host service cannot run disk tools"
	}
	return ""
}

func (h *Housekeeping) show(ctx context.Context, unit string, props ...string) map[string]string {
	args := []string{"show", "--timestamp=utc", unit} // utc: a box set to another time zone must not shift the dates
	for _, p := range props {
		args = append(args, "-p", p)
	}
	out, _, err := h.Run.Run(ctx, "systemctl", args...)
	m := map[string]string{}
	if err != nil {
		return m
	}
	for _, l := range strings.Split(string(out), "\n") {
		if k, v, ok := strings.Cut(l, "="); ok {
			m[k] = strings.TrimSpace(v)
		}
	}
	return m
}

// usec parses systemd's "Wed 2026-11-25 03:10:00 UTC" timestamp (`systemctl show --timestamp=utc`), or the
// microseconds-since-epoch form. Zero or unparsable: nil.
func usec(v string) *time.Time {
	if v == "" || v == "n/a" || v == "0" {
		return nil
	}
	if n, err := strconv.ParseInt(v, 10, 64); err == nil {
		if n <= 0 {
			return nil
		}
		t := time.UnixMicro(n).UTC()
		return &t
	}
	for _, layout := range []string{"Mon 2006-01-02 15:04:05 MST", "Mon 2006-01-02 15:04:05.999999 MST"} {
		if t, err := time.Parse(layout, v); err == nil {
			t = t.UTC()
			return &t
		}
	}
	return nil
}

var trimLineRe = regexp.MustCompile(`\((\d+) bytes\) trimmed`)

// Trim reads fstrim.timer and fstrim.service.
func (h *Housekeeping) Trim(ctx context.Context) TrimStatus {
	t := h.show(ctx, "fstrim.timer", "UnitFileState", "ActiveState", "NextElapseUSecRealtime")
	s := h.show(ctx, "fstrim.service", "Result", "ExecMainExitTimestampMonotonic", "ExecMainStartTimestamp", "ActiveEnterTimestamp", "InactiveEnterTimestamp")
	st := TrimStatus{Enabled: t["UnitFileState"] == "enabled", Timer: t["ActiveState"], NextRun: usec(t["NextElapseUSecRealtime"])}
	if st.Timer == "" {
		st.Timer = "unknown"
	}
	// A service that never ran has no start time. InactiveEnterTimestamp is the finish of the last run.
	if last := usec(s["InactiveEnterTimestamp"]); last != nil && usec(s["ExecMainStartTimestamp"]) != nil {
		st.LastRun, st.LastResult = last, s["Result"]
	}
	if st.LastRun != nil {
		out, _, err := h.Run.Run(ctx, "journalctl", "-u", "fstrim.service", "-n", "20", "-o", "cat", "--no-pager")
		if err == nil {
			for _, l := range strings.Split(string(out), "\n") {
				if m := trimLineRe.FindStringSubmatch(l); m != nil {
					n, _ := strconv.ParseInt(m[1], 10, 64)
					st.LastBytes = &n
				}
			}
		}
	}
	return st
}

// Alerts reads smartd's feed, newest first.
func (h *Housekeeping) Alerts() []SmartAlert {
	f, err := os.Open(h.feed())
	if err != nil {
		return []SmartAlert{}
	}
	defer f.Close()
	var all []SmartAlert
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 64<<10), 64<<10)
	for sc.Scan() {
		var a SmartAlert
		if json.Unmarshal(sc.Bytes(), &a) != nil || a.ID == "" || !deviceRe.MatchString(a.Device) {
			continue // a damaged line never hides the others
		}
		a.Kind, a.Message = clean(a.Kind, 64), clean(a.Message, 400)
		all = append(all, a)
	}
	for i, j := 0, len(all)-1; i < j; i, j = i+1, j-1 {
		all[i], all[j] = all[j], all[i]
	}
	if len(all) > maxAlerts {
		all = all[:maxAlerts]
	}
	if all == nil {
		all = []SmartAlert{}
	}
	return all
}

func (h *Housekeeping) feed() string {
	if h.AlertFeed != "" {
		return h.AlertFeed
	}
	return DefaultAlertFeed
}

// clean drops control characters and caps the length: smartd's message carries a drive's own text.
func clean(s string, max int) string {
	s = strings.Map(func(r rune) rune {
		if r < 0x20 || r == 0x7f {
			return ' '
		}
		return r
	}, s)
	if len(s) > max {
		s = s[:max]
	}
	return s
}

// lsblkBool reads lsblk's flags: a JSON bool on util-linux 2.38 and later, "0" or "1" before that.
type lsblkBool bool

func (b *lsblkBool) UnmarshalJSON(v []byte) error {
	*b = lsblkBool(string(v) == "true" || string(v) == `"1"` || string(v) == "1")
	return nil
}

type lsblkDev struct {
	Path       string     `json:"path"`
	Type       string     `json:"type"`
	RM         lsblkBool  `json:"rm"`
	Tran       string     `json:"tran"`
	Size       int64      `json:"size"`
	Model      string     `json:"model"`
	Serial     string     `json:"serial"`
	Label      string     `json:"label"`
	Mountpoint []string   `json:"mountpoints"`
	Children   []lsblkDev `json:"children"`
}

// protectedMounts: a drive carrying any of these is never ejected, whatever it says about itself.
var protectedMounts = []string{"/", "/data", "/boot", "/usr", "/var", "/home", "/etc", "/opt", "/srv"}

func protected(mp string) bool {
	if mp == "[SWAP]" { // lsblk's name for swap: a swap partition on a USB disk is in use, not removable
		return true
	}
	for _, p := range protectedMounts {
		if mp == p || (p != "/" && strings.HasPrefix(mp, p+"/")) {
			return true
		}
	}
	return false
}

func (d lsblkDev) allMounts() []string {
	var out []string
	for _, m := range d.Mountpoint {
		if m != "" {
			out = append(out, m)
		}
	}
	for _, c := range d.Children {
		out = append(out, c.allMounts()...)
	}
	return out
}

func (d lsblkDev) partitions() []string {
	var out []string
	for _, c := range d.Children {
		out = append(out, c.Path)
		out = append(out, c.partitions()...)
	}
	return out
}

// disks lists the removable disks. A removable disk is a whole disk on the USB bus or flagged removable by the kernel.
func (h *Housekeeping) disks(ctx context.Context) ([]lsblkDev, error) {
	out, code, err := h.Run.Run(ctx, "lsblk", "--json", "--bytes", "--tree", "-o", "PATH,TYPE,RM,TRAN,SIZE,MODEL,SERIAL,LABEL,MOUNTPOINTS")
	if err != nil || code != 0 {
		return nil, fmt.Errorf("lsblk failed")
	}
	var doc struct {
		Blockdevices []lsblkDev `json:"blockdevices"`
	}
	if err := json.Unmarshal(out, &doc); err != nil {
		return nil, fmt.Errorf("lsblk output unreadable")
	}
	var r []lsblkDev
	for _, d := range doc.Blockdevices {
		if d.Type == "disk" && (d.Tran == "usb" || bool(d.RM)) {
			r = append(r, d)
		}
	}
	return r, nil
}

func ejectProblem(d lsblkDev) string {
	for _, m := range d.allMounts() {
		if protected(m) {
			return "the box is using this drive (" + m + ")"
		}
	}
	return ""
}

// View implements Media.
func (h *Housekeeping) View(ctx context.Context) MediaView {
	v := MediaView{Trim: h.Trim(ctx), At: h.now(), Removable: []Removable{}}
	v.Smart = SmartStatus{Daemon: h.show(ctx, "smartmontools.service", "ActiveState")["ActiveState"], Alerts: h.Alerts()}
	if v.Smart.Daemon == "" {
		v.Smart.Daemon = "unknown"
	}
	ds, err := h.disks(ctx)
	if err != nil {
		return v
	}
	for _, d := range ds {
		r := Removable{Device: d.Path, Model: clean(d.Model, 80), SizeBytes: d.Size, Mounts: []string{}, Partitions: len(d.partitions())}
		if serialRe.MatchString(strings.TrimSpace(d.Serial)) {
			r.Serial = strings.TrimSpace(d.Serial)
		}
		for _, c := range append([]lsblkDev{d}, d.Children...) {
			if c.Label != "" && r.Label == "" {
				r.Label = clean(c.Label, 64)
			}
		}
		if ms := d.allMounts(); ms != nil {
			r.Mounts = ms
		}
		r.Why = ejectProblem(d)
		r.Ejectable = r.Why == ""
		v.Removable = append(v.Removable, r)
	}
	return v
}

func (h *Housekeeping) find(ctx context.Context, device string) (lsblkDev, error) {
	if !deviceRe.MatchString(device) {
		return lsblkDev{}, &Refusal{"bad_device", "device must be a path like /dev/sdb"}
	}
	ds, err := h.disks(ctx)
	if err != nil {
		return lsblkDev{}, &Refusal{"unavailable", "the box could not list its disks"}
	}
	for _, d := range ds {
		if d.Path == device {
			return d, nil
		}
	}
	return lsblkDev{}, &Refusal{"not_removable", device + " is not a removable USB drive (it may already be unplugged)"}
}

// CheckEject implements Media.
func (h *Housekeeping) CheckEject(ctx context.Context, device, serial string) error {
	d, err := h.find(ctx, device)
	if err != nil {
		return err
	}
	if serial != "" && strings.TrimSpace(d.Serial) != serial {
		return &Refusal{"drive_changed", device + " is not the drive the owner was asked about (it was swapped or replugged)"}
	}
	if why := ejectProblem(d); why != "" {
		return &Refusal{"in_use", why}
	}
	return nil
}

// Eject unmounts every mounted partition (udisksctl, the owner-action path F14 proves) and powers the drive off, so
// the stick is safe to pull. It re-checks first: the drive may have changed since the owner approved.
func (h *Housekeeping) Eject(ctx context.Context, device, serial string) error {
	d, err := h.find(ctx, device)
	if err != nil {
		return err
	}
	if serial != "" && strings.TrimSpace(d.Serial) != serial {
		return &Refusal{"drive_changed", device + " is not the drive the owner was asked about (it was swapped or replugged)"}
	}
	if why := ejectProblem(d); why != "" {
		return &Refusal{"in_use", why}
	}
	for _, p := range d.partitions() {
		if !deviceRe.MatchString(p) {
			continue
		}
		if _, code, err := h.udisks(ctx, "unmount", "-b", p); err != nil || (code != 0 && h.mounted(ctx, p)) {
			return fmt.Errorf("could not unmount %s", filepath.Base(p))
		}
	}
	if _, code, err := h.udisks(ctx, "power-off", "-b", device); err != nil || code != 0 {
		return fmt.Errorf("could not power off %s", filepath.Base(device))
	}
	return nil
}

// mounted reports whether p still has a mount point (an unmount of an unmounted partition exits non-zero).
func (h *Housekeeping) mounted(ctx context.Context, p string) bool {
	out, _, err := h.Run.Run(ctx, "findmnt", "-n", "-o", "TARGET", "-S", p)
	return err != nil || strings.TrimSpace(string(out)) != ""
}
