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
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/keymap"
)

const catalog = `! layout
  us              English (US)
  de              German
  fr              French

! variant
  nodeadkeys      de: German (no dead keys)
  bepo            fr: French (BEPO)
`

// keyUnits stands in for systemd: it records restarts and can fail one unit.
type keyUnits struct {
	fakeUnits
	failOn string
	file   string // the keyboard file, as each restart saw it
	seen   []string
}

func (k *keyUnits) Restart(ctx context.Context, unit string) error {
	b, _ := os.ReadFile(k.file)
	k.seen = append(k.seen, unit+":"+string(b))
	_ = k.fakeUnits.Restart(ctx, unit)
	if unit == k.failOn {
		return errors.New("exit status 1")
	}
	return nil
}

func keyService(t *testing.T) (*Service, *KeymapStore, *keyUnits) {
	t.Helper()
	dir := t.TempDir()
	cat := filepath.Join(dir, "base.lst")
	if err := os.WriteFile(cat, []byte(catalog), 0o644); err != nil {
		t.Fatal(err)
	}
	st := keymap.Store{Path: filepath.Join(dir, "console", "keyboard"), Catalog: cat}
	u := &keyUnits{file: st.Path}
	flag := filepath.Join(dir, "kiosk-enabled")
	if err := os.WriteFile(flag, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	k := &KeymapStore{Store: st, Units: u, KioskFlag: flag}
	s, _ := newService(t, t.TempDir(), "boot-1")
	s.Keymap = k
	return s, k, u
}

func TestSetKeymapRequestShape(t *testing.T) {
	for _, bad := range []Request{
		{ActionID: "a", Kind: KindSetKeymap},                                       // no layout
		{ActionID: "a", Kind: KindSetKeymap, Layout: "de; reboot"},                 // not a name
		{ActionID: "a", Kind: KindSetKeymap, Layout: "de", Variant: "no/dead"},     // not a name
		{ActionID: "a", Kind: KindSetKeymap, Layout: "de", Unit: "x.service"},      // extra field
		{ActionID: "a", Kind: KindSetKeymap, Layout: "de", Version: "1"},           // extra field
		{ActionID: "a", Kind: KindRestart, Layout: "de"},                           // layout on another kind
		{ActionID: "a", Kind: KindServiceRestart, Unit: "x.service", Variant: "v"}, // variant on another kind
	} {
		if err := bad.Validate(); err == nil {
			t.Errorf("%+v was valid", bad)
		}
	}
	if err := (Request{ActionID: "a", Kind: KindSetKeymap, Layout: "de", Variant: "nodeadkeys"}).Validate(); err != nil {
		t.Error(err)
	}
}

func TestSetKeymapWritesThenLoadsConsoleThenKiosk(t *testing.T) {
	s, k, u := keyService(t)
	if _, _, err := k.Store.Write("us", ""); err != nil {
		t.Fatal(err)
	}
	op, created, err := s.Submit(context.Background(), Request{ActionID: "k-1", Kind: KindSetKeymap, Layout: "de", Variant: "nodeadkeys"})
	if err != nil || !created || op.Layout != "de" || op.Variant != "nodeadkeys" {
		t.Fatalf("%+v %v %v", op, created, err)
	}
	s.Wait()
	got, _ := s.Store.Get("k-1")
	if got.State != StateSucceeded || !strings.Contains(got.Message, "de (nodeadkeys)") || got.Layout != "de" {
		t.Fatalf("%+v", got)
	}
	if len(u.seen) != 2 || !strings.HasPrefix(u.seen[0], ConsoleUnit+":") || !strings.HasPrefix(u.seen[1], KioskUnit+":") {
		t.Fatalf("restarts: %v", u.seen)
	}
	for _, seen := range u.seen { // each unit started after the file already said de, so it loads the new layout
		if !strings.Contains(seen, `XKBLAYOUT="de"`) || !strings.Contains(seen, `XKBVARIANT="nodeadkeys"`) {
			t.Fatalf("a unit restarted before the file was written: %q", seen)
		}
	}
	// The same action id again: nothing runs twice, and a different layout under that id is refused.
	if _, created, err := s.Submit(context.Background(), Request{ActionID: "k-1", Kind: KindSetKeymap, Layout: "de", Variant: "nodeadkeys"}); err != nil || created {
		t.Fatalf("replay: %v %v", created, err)
	}
	var ref *Refusal
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "k-1", Kind: KindSetKeymap, Layout: "fr"}); !errors.As(err, &ref) || ref.Reason != "action_id_reused" {
		t.Fatalf("a different layout under a used id: %v", err)
	}
	if len(u.seen) != 2 {
		t.Fatalf("a replay restarted units: %v", u.seen)
	}
}

func TestSetKeymapRefusesALayoutTheImageDoesNotOffer(t *testing.T) {
	s, k, u := keyService(t)
	var ref *Refusal
	for _, r := range []Request{{ActionID: "z", Kind: KindSetKeymap, Layout: "zz"}, {ActionID: "z", Kind: KindSetKeymap, Layout: "de", Variant: "bepo"}} {
		if _, _, err := s.Submit(context.Background(), r); !errors.As(err, &ref) || ref.Reason != "unknown_layout" {
			t.Fatalf("%+v: %v", r, err)
		}
	}
	if _, err := os.Stat(k.Store.Path); !errors.Is(err, os.ErrNotExist) || len(u.seen) != 0 {
		t.Fatal("a refused layout touched the box")
	}
	if _, err := s.Store.Get("z"); err == nil {
		t.Fatal("a refused request was journaled as accepted")
	}
}

func TestSetKeymapKeepsThePreviousLayoutWhenTheConsoleCannotLoadTheNewOne(t *testing.T) {
	s, k, u := keyService(t)
	if _, _, err := k.Store.Write("us", ""); err != nil {
		t.Fatal(err)
	}
	u.failOn = ConsoleUnit
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "k-2", Kind: KindSetKeymap, Layout: "fr", Variant: "bepo"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	got, _ := s.Store.Get("k-2")
	if got.State != StateFailed || got.Reason != "host_error" || !strings.Contains(got.Message, "previous layout was kept") {
		t.Fatalf("%+v", got)
	}
	cur, _, _ := k.Store.Current()
	if cur.Layout != "us" || cur.Variant != "" {
		t.Fatalf("the file was not put back: %+v", cur)
	}
	if len(u.seen) < 2 || !strings.Contains(u.seen[len(u.seen)-1], `XKBLAYOUT="us"`) {
		t.Fatalf("the old layout was not loaded again: %v", u.seen)
	}
	for _, seen := range u.seen {
		if strings.HasPrefix(seen, KioskUnit) {
			t.Fatalf("the kiosk must not restart after a failed console: %v", u.seen)
		}
	}
}

func TestSetKeymapLeavesTheKioskAloneWhenItIsOff(t *testing.T) {
	s, k, u := keyService(t)
	if err := os.Remove(k.KioskFlag); err != nil {
		t.Fatal(err)
	}
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "k-off", Kind: KindSetKeymap, Layout: "de"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if got, _ := s.Store.Get("k-off"); got.State != StateSucceeded {
		t.Fatalf("%+v", got)
	}
	if len(u.seen) != 1 || !strings.HasPrefix(u.seen[0], ConsoleUnit+":") {
		t.Fatalf("with kiosk mode off only the console unit restarts (a kiosk restart would stop getty@tty1): %v", u.seen)
	}
}

func TestSetKeymapKioskFailureStillSavesTheLayout(t *testing.T) {
	s, k, u := keyService(t)
	u.failOn = KioskUnit
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "k-3", Kind: KindSetKeymap, Layout: "de"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if got, _ := s.Store.Get("k-3"); got.State != StateSucceeded {
		t.Fatalf("%+v", got)
	}
	if cur, _, _ := k.Store.Current(); cur.Layout != "de" {
		t.Fatalf("%+v", cur)
	}
}

func TestSetKeymapIsUnavailableWithoutAKeymapOrAList(t *testing.T) {
	s, _ := newService(t, t.TempDir(), "boot-1")
	if why := s.Unavailable(KindSetKeymap); why == "" {
		t.Fatal("no Keymap: set-keymap must be unavailable")
	}
	s.Keymap = &KeymapStore{Store: keymap.Store{Catalog: filepath.Join(t.TempDir(), "missing")}, Units: &keyUnits{}}
	if why := s.Unavailable(KindSetKeymap); !strings.Contains(why, "keyboard layout list") {
		t.Fatalf("a missing list: %q", why)
	}
	var ref *Refusal
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "n", Kind: KindSetKeymap, Layout: "de"}); !errors.As(err, &ref) || ref.Reason != "unavailable" {
		t.Fatalf("%v", err)
	}
}

func TestKeyboardRouteShowsTheChoiceAndTheLayouts(t *testing.T) {
	get := func(srv *Server) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/keyboard", nil))
		return rec
	}
	if rec := get(&Server{S: &Service{}}); rec.Code != http.StatusNotFound {
		t.Fatalf("no Keymap: the route is off, got %d", rec.Code)
	}
	s, k, _ := keyService(t)
	rec := get(&Server{S: s})
	var v KeymapView
	if err := json.Unmarshal(rec.Body.Bytes(), &v); err != nil || rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
	if v.Schema != KeymapSchema || !v.Seeded || v.Current.Layout != "us" || len(v.Layouts) != 3 {
		t.Fatalf("%+v", v)
	}
	if _, _, err := k.Store.Write("fr", "bepo"); err != nil {
		t.Fatal(err)
	}
	_ = json.Unmarshal(get(&Server{S: s}).Body.Bytes(), &v)
	if v.Seeded || v.Current.Layout != "fr" || v.Current.Variant != "bepo" {
		t.Fatalf("%+v", v)
	}
	k.Store.Catalog = filepath.Join(t.TempDir(), "gone")
	if rec := get(&Server{S: s}); rec.Code != http.StatusInternalServerError || strings.Contains(rec.Body.String(), "gone") {
		t.Fatalf("a missing list is a plain 500 that names no path: %d %s", rec.Code, rec.Body)
	}
}
