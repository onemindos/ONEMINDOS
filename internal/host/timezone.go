// SPDX-License-Identifier: Apache-2.0

package host

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Time zone and clock (P-04). The root is read-only, so systemd-timedated cannot rewrite /etc/localtime.
// The image ships /etc/localtime as a symlink to /data/state/localtime (onemind-data-layout seeds it as
// UTC), and setting the zone swaps that one symlink to the zone file in /usr/share/zoneinfo. The zone
// therefore lives on /data: it is live at once for every process, survives a reboot, and survives an A/B
// update. Reading the clock's sync state is `timedatectl show` and `timedatectl show-timesync`, which only
// ask systemd-timedated and systemd-timesyncd.
//
// UNVERIFIED (needs a trixie box): systemd-timedated reads /etc/localtime one step and only recognises a
// target under /usr/share/zoneinfo/, so with /etc/localtime -> /data/state/localtime `timedatectl` probably
// prints "Time zone: n/a" and D-Bus readers of the Timezone property get "". This code never asks timedated
// for the zone: Current() reads the /data link itself, and the dashboard, API and CLI use that. Anything
// else on the box that needs the zone name must read /etc/localtime (libc does) or GET /v1/system/time.

// TimeSchema names GET /v1/time's shape.
const TimeSchema = "onemind.host.time/v1"

const (
	// DefaultZoneDir is where tzdata puts the zone files.
	DefaultZoneDir = "/usr/share/zoneinfo"
	// DefaultZoneLink is the symlink /etc/localtime points at; it lives on the data partition.
	DefaultZoneLink = "/data/state/localtime"
	// DefaultSyncStamp is touched by systemd-timesyncd each time it adjusts the clock.
	DefaultSyncStamp = "/run/systemd/timesync/synchronized"
)

var zoneRe = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}$`)

// ZoneName reports whether s looks like an IANA zone name (Europe/Berlin, UTC, Etc/GMT+5). It is a shape
// check only; Timezone.Check looks for the zone file.
func ZoneName(s string) bool {
	if len(s) > 64 || !zoneRe.MatchString(s) {
		return false
	}
	// posix/ and right/ are alternative copies of the database, never what an owner picks.
	if strings.HasPrefix(s, "posix/") || strings.HasPrefix(s, "right/") {
		return false
	}
	// tzdata's own helper entries: localtime links back to /etc/localtime (which is our symlink: a loop),
	// posixrules and Factory are not zones.
	switch s {
	case "localtime", "posixrules", "Factory":
		return false
	}
	return true
}

// Timezone sets and reads the zone and reads the clock. The zero value is the production box.
type Timezone struct {
	ZoneDir   string // default DefaultZoneDir
	Link      string // default DefaultZoneLink
	SyncStamp string // default DefaultSyncStamp
	// Run runs a command and returns its stdout (default: exec with a 5 s limit).
	Run func(ctx context.Context, name string, args ...string) ([]byte, error)
	Now func() time.Time
}

func (t *Timezone) zoneDir() string {
	if t.ZoneDir != "" {
		return t.ZoneDir
	}
	return DefaultZoneDir
}

func (t *Timezone) link() string {
	if t.Link != "" {
		return t.Link
	}
	return DefaultZoneLink
}

func (t *Timezone) stamp() string {
	if t.SyncStamp != "" {
		return t.SyncStamp
	}
	return DefaultSyncStamp
}

// Check refuses a name this box has no zone file for (a TZif file inside the zone directory).
func (t *Timezone) Check(zone string) error {
	if !ZoneName(zone) {
		return errors.New("that is not a time zone name")
	}
	dir, err := filepath.EvalSymlinks(t.zoneDir())
	if err != nil {
		return errors.New("this box has no time zone database")
	}
	path, err := filepath.EvalSymlinks(filepath.Join(dir, zone))
	if err != nil || !strings.HasPrefix(path, dir+string(filepath.Separator)) {
		return fmt.Errorf("this box does not know the time zone %q", zone)
	}
	// Every link on the way must stay inside the zone directory, even when the end lands back inside it
	// (zoneinfo/localtime -> /etc/localtime -> /data/state/localtime -> ... would loop once we swap the link).
	if leavesDir(dir, zone) {
		return fmt.Errorf("this box does not know the time zone %q", zone)
	}
	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("this box does not know the time zone %q", zone)
	}
	defer f.Close()
	magic := make([]byte, 4)
	if _, err := io.ReadFull(f, magic); err != nil || string(magic) != "TZif" {
		return fmt.Errorf("%q is not a time zone", zone)
	}
	return nil
}

// leavesDir reports whether resolving zone under dir, one symlink step at a time, ever points outside dir.
func leavesDir(dir, zone string) bool {
	cur := filepath.Join(dir, zone)
	for range 16 {
		fi, err := os.Lstat(cur)
		if err != nil {
			return true
		}
		if fi.Mode()&os.ModeSymlink == 0 {
			return false
		}
		target, err := os.Readlink(cur)
		if err != nil {
			return true
		}
		if !filepath.IsAbs(target) {
			target = filepath.Join(filepath.Dir(cur), target)
		}
		target = filepath.Clean(target)
		if !strings.HasPrefix(target, dir+string(filepath.Separator)) {
			return true
		}
		cur = target
	}
	return true
}

// Set makes zone the box's zone: one atomic swap of the symlink on /data.
func (t *Timezone) Set(_ context.Context, zone string) error {
	if err := t.Check(zone); err != nil {
		return err
	}
	link := t.link()
	tmp := link + ".new"
	_ = os.Remove(tmp)
	if err := os.Symlink(filepath.Join(t.zoneDir(), zone), tmp); err != nil {
		return err
	}
	if err := os.Rename(tmp, link); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}

// Current is the zone the symlink names, or "" when it names nothing in the zone directory.
func (t *Timezone) Current() string {
	target, err := os.Readlink(t.link())
	if err != nil {
		return ""
	}
	zone, ok := strings.CutPrefix(target, t.zoneDir()+"/")
	if !ok || !ZoneName(zone) {
		return ""
	}
	return zone
}

// TimeStatus is GET /v1/time. Fields the clock did not report are null, never guessed.
type TimeStatus struct {
	Schema string `json:"schema"`
	// Zone is the box's zone name; null when /etc/localtime names none (the image's default is UTC).
	Zone *string `json:"zone"`
	// NTPEnabled is timedatectl's NTP: whether the box is asked to keep its clock from the network.
	NTPEnabled *bool `json:"ntp_enabled"`
	// NTPSynchronized is timedatectl's NTPSynchronized: the clock is currently set from a time server.
	NTPSynchronized *bool `json:"ntp_synchronized"`
	// Server is the time server systemd-timesyncd talked to last (null before it has reached one).
	Server  *string `json:"server"`
	Stratum *int    `json:"stratum"`
	// LastSyncAt is when systemd-timesyncd last set the clock.
	LastSyncAt *time.Time `json:"last_sync_at"`
	At         time.Time  `json:"at"`
	// Problem says why the clock state could not be read (timedatectl failed); the zone is still given.
	Problem *string `json:"problem"`
}

var stratumRe = regexp.MustCompile(`Stratum=(\d{1,2})\b`)

// parseProps reads `systemctl show` style Key=Value lines.
func parseProps(out []byte) map[string]string {
	m := map[string]string{}
	for _, line := range strings.Split(string(out), "\n") {
		if k, v, ok := strings.Cut(line, "="); ok && k != "" {
			m[k] = strings.TrimSpace(v)
		}
	}
	return m
}

func yesNo(v string) *bool {
	switch v {
	case "yes":
		t := true
		return &t
	case "no":
		f := false
		return &f
	}
	return nil
}

// Status reads the zone and the clock. It never fails: what cannot be read is null, and Problem says why.
func (t *Timezone) Status(ctx context.Context) TimeStatus {
	now := time.Now
	if t.Now != nil {
		now = t.Now
	}
	st := TimeStatus{Schema: TimeSchema, At: now().UTC()}
	if z := t.Current(); z != "" {
		st.Zone = &z
	}
	run := t.Run
	if run == nil {
		run = execOutput
	}
	out, err := run(ctx, "timedatectl", "show", "-p", "NTP", "-p", "NTPSynchronized")
	if err != nil {
		p := "the clock could not be read from systemd-timedated"
		st.Problem = &p
		return st
	}
	props := parseProps(out)
	st.NTPEnabled, st.NTPSynchronized = yesNo(props["NTP"]), yesNo(props["NTPSynchronized"])
	// show-timesync is systemd-timesyncd's own answer; a box without it (or before it ran) just has no server.
	if out, err := run(ctx, "timedatectl", "show-timesync"); err == nil {
		ts := parseProps(out)
		if name := ts["ServerName"]; name != "" && len(name) <= 253 && !strings.ContainsAny(name, " \t\x00") {
			st.Server = &name
		}
		if m := stratumRe.FindStringSubmatch(ts["NTPMessage"]); m != nil {
			n, _ := strconv.Atoi(m[1])
			st.Stratum = &n
		}
	}
	if fi, err := os.Stat(t.stamp()); err == nil {
		at := fi.ModTime().UTC()
		st.LastSyncAt = &at
	}
	return st
}

func execOutput(ctx context.Context, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	var out bytes.Buffer
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout = &limitWriter{w: &out, n: 1 << 16}
	return out.Bytes(), cmd.Run()
}

// limitWriter drops what is written past n bytes.
type limitWriter struct {
	w io.Writer
	n int
}

func (l *limitWriter) Write(p []byte) (int, error) {
	if l.n > 0 {
		k := min(len(p), l.n)
		_, _ = l.w.Write(p[:k])
		l.n -= k
	}
	return len(p), nil
}
