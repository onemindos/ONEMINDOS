// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// zoneBox is a zone directory with two real-looking zone files (TZif magic), one junk file and the symlink
// the image points /etc/localtime at.
func zoneBox(t *testing.T) *Timezone {
	t.Helper()
	root := t.TempDir()
	dir := filepath.Join(root, "zoneinfo")
	for name, body := range map[string]string{"UTC": "TZif2", "Europe/Berlin": "TZif2", "Pacific/Auckland": "TZif2", "zone.tab": "# not a zone"} {
		p := filepath.Join(dir, name)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Symlink("../Europe/Berlin", filepath.Join(dir, "Posix_Link")); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(root, "localtime")
	if err := os.Symlink(filepath.Join(dir, "UTC"), link); err != nil {
		t.Fatal(err)
	}
	return &Timezone{ZoneDir: dir, Link: link, SyncStamp: filepath.Join(root, "synchronized")}
}

func TestZoneNameIsAShapeCheck(t *testing.T) {
	for _, ok := range []string{"UTC", "Europe/Berlin", "America/Argentina/Buenos_Aires", "Etc/GMT+5"} {
		if !ZoneName(ok) {
			t.Errorf("%q refused", ok)
		}
	}
	for _, bad := range []string{"", "../etc/passwd", "/etc/passwd", "Europe/../../x", "posix/Europe/Berlin", "right/UTC", "a b", "Europe//Berlin", "A/B/C/D", "-UTC", "localtime", "posixrules", "Factory"} {
		if ZoneName(bad) {
			t.Errorf("%q accepted", bad)
		}
	}
}

func TestSetSwapsTheSymlinkAndCheckRefusesUnknownZones(t *testing.T) {
	z := zoneBox(t)
	if got := z.Current(); got != "UTC" {
		t.Fatalf("seed zone %q", got)
	}
	for _, bad := range []string{"Mars/Olympus", "zone.tab", "UTC/../zone.tab", "../zoneinfo/UTC"} {
		if err := z.Check(bad); err == nil {
			t.Errorf("%q passed Check", bad)
		}
		if err := z.Set(context.Background(), bad); err == nil {
			t.Errorf("%q was set", bad)
		}
	}
	if got := z.Current(); got != "UTC" {
		t.Fatalf("a refused zone changed the box: %q", got)
	}
	if err := z.Set(context.Background(), "Pacific/Auckland"); err != nil {
		t.Fatal(err)
	}
	if got := z.Current(); got != "Pacific/Auckland" {
		t.Fatalf("zone %q", got)
	}
	// What a process sees through the link is the zone file itself.
	if b, err := os.ReadFile(z.Link); err != nil || string(b) != "TZif2" {
		t.Fatalf("link does not resolve: %q %v", b, err)
	}
	if _, err := os.Lstat(z.Link + ".new"); !os.IsNotExist(err) {
		t.Fatal("temporary link left behind")
	}
}

func TestSetTimezoneIsAnApprovedJournaledAction(t *testing.T) {
	s, p := newService(t, t.TempDir(), "boot-1")
	if why := s.Unavailable(KindSetTimezone); why == "" {
		t.Fatal("no Zones: set-timezone must be unavailable")
	}
	z := zoneBox(t)
	s.Zones = z
	for _, bad := range []Request{
		{ActionID: "a", Kind: KindSetTimezone},                                               // no zone
		{ActionID: "a", Kind: KindRestart, Zone: "UTC"},                                      // zone on another kind
		{ActionID: "a", Kind: KindSetTimezone, Zone: "../../etc/passwd"},                     // not a zone name
		{ActionID: "a", Kind: KindSetTimezone, Zone: "UTC", Unit: "onemind-gateway.service"}, // extra field
	} {
		if err := bad.Validate(); err == nil {
			t.Errorf("%+v was valid", bad)
		}
	}
	var ref *Refusal
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-bad", Kind: KindSetTimezone, Zone: "Mars/Olympus"}); !errors.As(err, &ref) || ref.Reason != "unknown_zone" {
		t.Fatalf("unknown zone: %v", err)
	}
	op, created, err := s.Submit(context.Background(), Request{ActionID: "act-tz", Kind: KindSetTimezone, Zone: "Europe/Berlin"})
	if err != nil || !created || op.Zone != "Europe/Berlin" {
		t.Fatalf("%+v %v %v", op, created, err)
	}
	s.Wait()
	got, _ := s.Store.Get("act-tz")
	if got.State != StateSucceeded || z.Current() != "Europe/Berlin" || p.reboots != 0 {
		t.Fatalf("journal %+v zone %q reboots %d", got, z.Current(), p.reboots)
	}
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-tz", Kind: KindSetTimezone, Zone: "UTC"}); !errors.As(err, &ref) || ref.Reason != "action_id_reused" {
		t.Fatalf("reused id: %v", err)
	}
	// A box that cannot write the link reports the action failed, not succeeded.
	z.Link = filepath.Join(t.TempDir(), "missing-dir", "localtime")
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-fail", Kind: KindSetTimezone, Zone: "UTC"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if got, _ := s.Store.Get("act-fail"); got.State != StateFailed || got.Reason != "host_error" {
		t.Fatalf("a failed set is reported failed: %+v", got)
	}
}

const showOut = "NTP=yes\nNTPSynchronized=yes\n"
const timesyncOut = "SystemNTPServers=\nServerName=0.debian.pool.ntp.org\nServerAddress=192.0.2.7\n" +
	"NTPMessage={ Leap=0, Version=4, Mode=4, Stratum=2, Precision=-24, RootDelay=1ms, Reference=C0000201 }\n"

func TestStatusReadsTheClock(t *testing.T) {
	z := zoneBox(t)
	stamp := time.Date(2026, 11, 25, 12, 0, 0, 0, time.UTC)
	if err := os.WriteFile(z.SyncStamp, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Chtimes(z.SyncStamp, stamp, stamp); err != nil {
		t.Fatal(err)
	}
	z.Run = func(_ context.Context, name string, args ...string) ([]byte, error) {
		if name != "timedatectl" {
			t.Fatalf("ran %s", name)
		}
		if args[0] == "show-timesync" {
			return []byte(timesyncOut), nil
		}
		return []byte(showOut), nil
	}
	st := z.Status(context.Background())
	if st.Zone == nil || *st.Zone != "UTC" || st.NTPSynchronized == nil || !*st.NTPSynchronized || st.NTPEnabled == nil || !*st.NTPEnabled {
		t.Fatalf("%+v", st)
	}
	if st.Server == nil || *st.Server != "0.debian.pool.ntp.org" || st.Stratum == nil || *st.Stratum != 2 || st.LastSyncAt == nil || !st.LastSyncAt.Equal(stamp) || st.Problem != nil {
		t.Fatalf("%+v", st)
	}
}

func TestStatusNeverInventsWhatTheClockDidNotSay(t *testing.T) {
	z := zoneBox(t)
	z.Run = func(context.Context, string, ...string) ([]byte, error) { return nil, errors.New("exit status 1") }
	st := z.Status(context.Background())
	if st.NTPSynchronized != nil || st.NTPEnabled != nil || st.Server != nil || st.LastSyncAt != nil || st.Problem == nil || st.Zone == nil {
		t.Fatalf("%+v", st)
	}
	// Before timesyncd reaches a server: synchronised no, and no server named.
	z.Run = func(_ context.Context, _ string, args ...string) ([]byte, error) {
		if args[0] == "show-timesync" {
			return []byte("ServerName=\nNTPMessage=\n"), nil
		}
		return []byte("NTP=yes\nNTPSynchronized=no\n"), nil
	}
	st = z.Status(context.Background())
	if st.NTPSynchronized == nil || *st.NTPSynchronized || st.Server != nil || st.Stratum != nil {
		t.Fatalf("%+v", st)
	}
}

func TestTimeRoute(t *testing.T) {
	get := func(srv *Server) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/time", nil))
		return rec
	}
	if rec := get(&Server{}); rec.Code != http.StatusNotFound {
		t.Fatalf("no Time: the route is off, got %d", rec.Code)
	}
	z := zoneBox(t)
	z.Run = func(context.Context, string, ...string) ([]byte, error) { return []byte(showOut), nil }
	rec := get(&Server{Time: func(ctx context.Context) (any, error) { return z.Status(ctx), nil }})
	var body map[string]any
	if rec.Code != 200 || json.Unmarshal(rec.Body.Bytes(), &body) != nil || body["schema"] != TimeSchema || body["zone"] != "UTC" || body["ntp_synchronized"] != true {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
}

// Debian's tzdata ships zoneinfo/localtime -> /etc/localtime. Whatever that ends at, a zone that steps out of
// the zone directory must be refused: setting it would point the box's link back at itself.
func TestCheckRefusesZonesWhoseLinksLeaveTheZoneDirectory(t *testing.T) {
	z := zoneBox(t)
	dir := z.ZoneDir
	outside := filepath.Join(filepath.Dir(dir), "etc-localtime")
	if err := os.Symlink(filepath.Join(dir, "UTC"), outside); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(dir, "Loopy")); err != nil {
		t.Fatal(err)
	}
	if err := z.Check("Loopy"); err == nil {
		t.Fatal("a zone whose link goes through a path outside the zone directory was accepted")
	}
	if err := z.Check("UTC"); err != nil {
		t.Fatal(err)
	}
}
