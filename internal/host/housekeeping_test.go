// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// fakeCmds answers by the command line; every call is recorded.
type fakeCmds struct {
	mu    sync.Mutex
	out   map[string]string
	exit  map[string]int
	calls []string
}

func (f *fakeCmds) Run(_ context.Context, name string, args ...string) ([]byte, int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	line := name + " " + strings.Join(args, " ")
	f.calls = append(f.calls, line)
	for prefix, out := range f.out {
		if strings.HasPrefix(line, prefix) {
			return []byte(out), f.exit[prefix], nil
		}
	}
	return nil, 0, nil
}

const lsblkTwoDisks = `{"blockdevices":[
 {"path":"/dev/vda","type":"disk","rm":false,"tran":null,"size":34359738368,"model":null,"label":null,"mountpoints":[null],"children":[
   {"path":"/dev/vda2","type":"part","rm":false,"tran":null,"size":1,"model":null,"label":"data","mountpoints":["/data"]}]},
 {"path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Cruzer","serial":"4C530001230","label":null,"mountpoints":[null],"children":[
   {"path":"/dev/sdb1","type":"part","rm":true,"tran":null,"size":15000000000,"model":null,"label":"HOLIDAY","mountpoints":["/run/media/holiday"]}]},
 {"path":"/dev/sdc","type":"disk","rm":"1","tran":"usb","size":500000000000,"model":"Boot stick","label":null,"mountpoints":[null],"children":[
   {"path":"/dev/sdc1","type":"part","rm":true,"tran":null,"size":1,"model":null,"label":null,"mountpoints":["/data/odd"]}]}
]}`

func newHK(t *testing.T) (*Housekeeping, *fakeCmds) {
	t.Helper()
	f := &fakeCmds{out: map[string]string{"lsblk": lsblkTwoDisks}, exit: map[string]int{}}
	return &Housekeeping{Run: f, AlertFeed: filepath.Join(t.TempDir(), "alerts.jsonl"),
		Now: func() time.Time { return time.Date(2026, 11, 25, 12, 0, 0, 0, time.UTC) }}, f
}

func TestViewListsRemovableDrivesAndRefusesTheOneInUse(t *testing.T) {
	h, _ := newHK(t)
	v := h.View(context.Background())
	if len(v.Removable) != 2 {
		t.Fatalf("the internal disk must not be listed: %+v", v.Removable)
	}
	a, b := v.Removable[0], v.Removable[1]
	if a.Device != "/dev/sdb" || !a.Ejectable || a.Label != "HOLIDAY" || len(a.Mounts) != 1 || a.Partitions != 1 {
		t.Fatalf("sdb: %+v", a)
	}
	if b.Device != "/dev/sdc" || b.Ejectable || !strings.Contains(b.Why, "/data/odd") {
		t.Fatalf("a stick with a mount under /data is in use: %+v", b)
	}
}

func TestTrimStatusReadsTheTimerAndTheLastRun(t *testing.T) {
	h, f := newHK(t)
	f.out["systemctl show --timestamp=utc fstrim.timer"] = "UnitFileState=enabled\nActiveState=active\nNextElapseUSecRealtime=Mon 2026-11-30 00:00:00 UTC\n"
	f.out["systemctl show --timestamp=utc fstrim.service"] = "Result=success\nExecMainStartTimestamp=Mon 2026-11-23 00:07:12 UTC\nInactiveEnterTimestamp=Mon 2026-11-23 00:07:14 UTC\n"
	f.out["journalctl"] = "/data: 12.4 GiB (13314398208 bytes) trimmed on /dev/vda2\n"
	tr := h.Trim(context.Background())
	if !tr.Enabled || tr.Timer != "active" || tr.LastResult != "success" || tr.LastRun == nil || tr.NextRun == nil {
		t.Fatalf("%+v", tr)
	}
	if tr.LastRun.Format(time.RFC3339) != "2026-11-23T00:07:14Z" || tr.NextRun.Day() != 30 || tr.LastBytes == nil || *tr.LastBytes != 13314398208 {
		t.Fatalf("%+v %v", tr, tr.LastBytes)
	}
	// A box whose TRIM never ran says so: no last run, no byte count, and no journal read.
	f.out["systemctl show --timestamp=utc fstrim.service"] = "Result=success\nExecMainStartTimestamp=\nInactiveEnterTimestamp=\n"
	f.calls = nil
	if tr := h.Trim(context.Background()); tr.LastRun != nil || tr.LastBytes != nil {
		t.Fatalf("never ran: %+v", tr)
	}
	for _, c := range f.calls {
		if strings.HasPrefix(c, "journalctl") {
			t.Fatal("journal read for a unit that never ran")
		}
	}
}

func TestAlertsNewestFirstAndDamagedLinesSkipped(t *testing.T) {
	h, _ := newHK(t)
	feed := `{"id":"a1","at":"2026-11-24T01:00:00Z","device":"/dev/sda","kind":"Health","message":"SMART health failed"}
not json
{"id":"a2","at":"2026-11-25T01:00:00Z","device":"/dev/nvme0n1","kind":"Temperature","message":"too hot\u001b[31m"}
{"id":"a3","at":"2026-11-25T02:00:00Z","device":"../../etc/passwd","kind":"x","message":"bad device"}
`
	if err := os.WriteFile(h.AlertFeed, []byte(feed), 0o600); err != nil {
		t.Fatal(err)
	}
	al := h.Alerts()
	if len(al) != 2 || al[0].ID != "a2" || al[1].ID != "a1" {
		t.Fatalf("%+v", al)
	}
	if strings.ContainsRune(al[0].Message, 0x1b) {
		t.Fatalf("control characters must not reach a screen: %q", al[0].Message)
	}
	if got := (&Housekeeping{Run: &fakeCmds{}, AlertFeed: filepath.Join(t.TempDir(), "none")}).Alerts(); got == nil || len(got) != 0 {
		t.Fatalf("no feed is an empty list, not null: %#v", got)
	}
}

func TestEjectUnmountsThenPowersOffAndRefusesWhatIsNotRemovable(t *testing.T) {
	h, f := newHK(t)
	s, _ := newService(t, t.TempDir(), "b1")
	if why := s.Unavailable(KindEject); why == "" {
		t.Fatal("no Media: eject must be unavailable")
	}
	s.Media = h
	for _, bad := range []Request{
		{ActionID: "a", Kind: KindEject},                                     // no device
		{ActionID: "a", Kind: KindRestart, Device: "/dev/sdb"},               // device on another kind
		{ActionID: "a", Kind: KindEject, Device: "/dev/sdb; rm -rf /"},       // not a path
		{ActionID: "a", Kind: KindEject, Device: "/dev/sdb", Version: "1.0"}, // extra field
	} {
		if bad.Validate() == nil {
			t.Errorf("%+v was valid", bad)
		}
	}
	var ref *Refusal
	for dev, reason := range map[string]string{"/dev/vda": "not_removable", "/dev/sdc": "in_use", "/dev/sdz": "not_removable"} {
		if _, _, err := s.Submit(context.Background(), Request{ActionID: "no-" + filepath.Base(dev), Kind: KindEject, Device: dev}); !errors.As(err, &ref) || ref.Reason != reason {
			t.Fatalf("%s: %v", dev, err)
		}
	}
	op, created, err := s.Submit(context.Background(), Request{ActionID: "act-eject", Kind: KindEject, Device: "/dev/sdb"})
	if err != nil || !created || op.Device != "/dev/sdb" {
		t.Fatalf("%+v %v %v", op, created, err)
	}
	s.Wait()
	got, _ := s.Store.Get("act-eject")
	if got.State != StateSucceeded || !strings.Contains(got.Message, "safe to remove") {
		t.Fatalf("%+v", got)
	}
	var um, off int
	for i, c := range f.calls {
		switch c {
		case "udisksctl unmount -b /dev/sdb1":
			um = i + 1
		case "udisksctl power-off -b /dev/sdb":
			off = i + 1
		}
	}
	if um == 0 || off == 0 || um > off {
		t.Fatalf("unmount must come before power-off: %v", f.calls)
	}
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-eject", Kind: KindEject, Device: "/dev/sdd"}); !errors.As(err, &ref) || ref.Reason != "action_id_reused" {
		t.Fatalf("reused id: %v", err)
	}
	// A power-off that fails is reported failed, not succeeded.
	f.out["udisksctl power-off"], f.exit["udisksctl power-off"] = "", 1
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-fail", Kind: KindEject, Device: "/dev/sdb"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if got, _ := s.Store.Get("act-fail"); got.State != StateFailed || got.Reason != "host_error" {
		t.Fatalf("%+v", got)
	}
}

func TestHousekeepingRoute(t *testing.T) {
	get := func(srv *Server) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/storage/housekeeping", nil))
		return rec
	}
	if rec := get(&Server{S: &Service{}}); rec.Code != http.StatusNotFound {
		t.Fatalf("no Media: the route is off, got %d", rec.Code)
	}
	h, _ := newHK(t)
	rec := get(&Server{S: &Service{Media: h}})
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), `"removable"`) || !strings.Contains(rec.Body.String(), `"smart"`) {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
}

func TestEjectBoundToTheSerialAndSwapIsInUse(t *testing.T) {
	h, f := newHK(t)
	ctx := context.Background()
	if v := h.View(ctx); v.Removable[0].Serial != "4C530001230" {
		t.Fatalf("the view carries the serial: %+v", v.Removable[0])
	}
	var ref *Refusal
	// Another stick that came up as sdb after the owner was asked: refused, nothing unmounted.
	if err := h.CheckEject(ctx, "/dev/sdb", "OTHERSTICK"); !errors.As(err, &ref) || ref.Reason != "drive_changed" {
		t.Fatalf("a swapped stick: %v", err)
	}
	if err := h.Eject(ctx, "/dev/sdb", "OTHERSTICK"); !errors.As(err, &ref) || ref.Reason != "drive_changed" {
		t.Fatalf("a swapped stick at run time: %v", err)
	}
	for _, c := range f.calls {
		if strings.HasPrefix(c, "udisksctl") {
			t.Fatalf("nothing may be touched for a swapped stick: %v", f.calls)
		}
	}
	if err := h.CheckEject(ctx, "/dev/sdb", "4C530001230"); err != nil {
		t.Fatal(err)
	}
	// A swap area on a USB disk is the box's memory.
	f.out["lsblk"] = `{"blockdevices":[{"path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":1,"model":"x","serial":"S1","label":null,"mountpoints":[null],"children":[
	  {"path":"/dev/sdb1","type":"part","rm":true,"tran":null,"size":1,"model":null,"label":null,"mountpoints":["[SWAP]"]}]}]}`
	if err := h.CheckEject(ctx, "/dev/sdb", ""); !errors.As(err, &ref) || ref.Reason != "in_use" {
		t.Fatalf("swap on a USB disk: %v", err)
	}
	if (Request{ActionID: "a", Kind: KindEject, Device: "/dev/sdb", Serial: "bad serial;"}).Validate() == nil ||
		(Request{ActionID: "a", Kind: KindRestart, Serial: "S1"}).Validate() == nil {
		t.Fatal("a bad serial, or a serial on another kind, must be refused")
	}
}

type hangCmds struct{}

func (hangCmds) Run(ctx context.Context, name string, args ...string) ([]byte, int, error) {
	if name == "lsblk" {
		return []byte(lsblkTwoDisks), 0, nil
	}
	<-ctx.Done() // a hung udisks: only the context ends it
	return nil, -1, ctx.Err()
}

func TestEjectGivesUpWhenUdisksHangs(t *testing.T) {
	h := &Housekeeping{Run: hangCmds{}, CmdTimeout: 50 * time.Millisecond}
	done := make(chan error, 1)
	go func() { done <- h.Eject(context.Background(), "/dev/sdb", "") }()
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("a hung unmount must fail the eject")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("eject hung: udisksctl has no timeout")
	}
}
