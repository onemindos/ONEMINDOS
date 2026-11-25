// SPDX-License-Identifier: Apache-2.0

package keymap

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// A cut of xkb-data's rules/base.lst (same layout of the file: sections, two-space indent, "layout: name" in variants).
const lst = `! model
  pc105           Generic 105-key PC (intl.)

! layout
  us              English (US)
  de              German
  fr              French
  latam           Spanish (Latin American)

! variant
  intl            us: English (US, intl., with dead keys)
  dvorak          us: English (Dvorak)
  nodeadkeys      de: German (no dead keys)
  bepo            fr: French (BEPO)
  nodeadkeys      fr: French (no dead keys)
  ghost           xx: A variant of a layout that is not listed

! option
  grp             Switching to another layout
`

func store(t *testing.T) Store {
	t.Helper()
	dir := t.TempDir()
	cat := filepath.Join(dir, "base.lst")
	if err := os.WriteFile(cat, []byte(lst), 0o644); err != nil {
		t.Fatal(err)
	}
	return Store{Path: filepath.Join(dir, "console", "keyboard"), Catalog: cat}
}

func TestCatalogListsLayoutsWithTheirOwnVariants(t *testing.T) {
	got, err := ParseCatalog(strings.NewReader(lst))
	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, l := range got {
		names = append(names, l.ID)
	}
	if strings.Join(names, ",") != "us,fr,de,latam" { // sorted by name: English (US), French, German, Spanish (Latin American)
		t.Fatalf("order %v", names)
	}
	byID := map[string]Layout{}
	for _, l := range got {
		byID[l.ID] = l
	}
	if len(byID["de"].Variants) != 1 || byID["de"].Variants[0].ID != "nodeadkeys" {
		t.Errorf("de variants %+v", byID["de"].Variants)
	}
	if len(byID["fr"].Variants) != 2 || len(byID["us"].Variants) != 2 || len(byID["latam"].Variants) != 0 {
		t.Errorf("variants: fr %d us %d latam %d", len(byID["fr"].Variants), len(byID["us"].Variants), len(byID["latam"].Variants))
	}
	if byID["de"].Name != "German" || byID["us"].Variants[0].Name == "" {
		t.Errorf("names %+v", byID["us"])
	}
	if _, err := ParseCatalog(strings.NewReader("! model\n  pc105 x\n")); err == nil {
		t.Error("a list with no layouts must be an error")
	}
}

func TestTheRealXKBFileParsesWhenTheHostHasOne(t *testing.T) {
	f, err := os.Open(DefaultCatalog)
	if err != nil {
		t.Skip("no xkb-data on this machine")
	}
	defer f.Close()
	got, err := ParseCatalog(f)
	if err != nil || len(got) < 50 {
		t.Fatalf("%d layouts, %v", len(got), err)
	}
}

func TestCheckOffersOnlyWhatTheImageHas(t *testing.T) {
	s := store(t)
	for _, c := range []struct {
		layout, variant string
		ok              bool
	}{{"de", "", true}, {"de", "nodeadkeys", true}, {"fr", "bepo", true}, {"de", "bepo", false}, {"zz", "", false},
		{"de; rm", "", false}, {"de", "no/dead", false}, {"", "", false}} {
		err := s.Check(c.layout, c.variant)
		if (err == nil) != c.ok {
			t.Errorf("Check(%q,%q) = %v", c.layout, c.variant, err)
		}
	}
	if err := s.Check("zz", ""); !errors.Is(err, ErrUnknown) {
		t.Errorf("an unlisted layout must wrap ErrUnknown, got %v", err)
	}
	if err := (Store{Catalog: filepath.Join(t.TempDir(), "none")}).Check("de", ""); err == nil || errors.Is(err, ErrUnknown) {
		t.Errorf("a missing list is a host error, not 'unknown': %v", err)
	}
}

func TestCurrentIsTheSeedUntilTheOwnerChooses(t *testing.T) {
	s := store(t)
	cur, seeded, err := s.Current()
	if err != nil || !seeded || cur.Layout != "us" || cur.Model != "pc105" {
		t.Fatalf("%+v seeded=%v %v", cur, seeded, err)
	}
	if _, _, err := s.Write("de", "nodeadkeys"); err != nil {
		t.Fatal(err)
	}
	cur, seeded, _ = s.Current()
	if seeded || cur.Layout != "de" || cur.Variant != "nodeadkeys" {
		t.Fatalf("%+v seeded=%v", cur, seeded)
	}
}

func TestWriteKeepsModelAndOptionsAndTheFileModeAndCanBeUndone(t *testing.T) {
	s := store(t)
	if err := os.MkdirAll(filepath.Dir(s.Path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(s.Path, []byte("XKBMODEL=\"pc104\"\nXKBLAYOUT=\"us\"\nXKBVARIANT=\"\"\nXKBOPTIONS=\"ctrl:nocaps\"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	prev, had, err := s.Write("fr", "bepo")
	if err != nil || !had || prev.Layout != "us" {
		t.Fatalf("%+v %v %v", prev, had, err)
	}
	cur, _, _ := s.Current()
	if cur != (Setting{Model: "pc104", Layout: "fr", Variant: "bepo", Options: "ctrl:nocaps"}) {
		t.Fatalf("%+v", cur)
	}
	if fi, _ := os.Stat(s.Path); fi.Mode().Perm() != 0o644 {
		t.Errorf("mode %v", fi.Mode().Perm())
	}
	if err := s.Restore(prev, had); err != nil {
		t.Fatal(err)
	}
	cur, _, _ = s.Current()
	if cur.Layout != "us" || cur.Options != "ctrl:nocaps" {
		t.Fatalf("restored %+v", cur)
	}
	// No file before: Restore removes it again.
	s2 := store(t)
	prev, had, err = s2.Write("de", "")
	if err != nil || had {
		t.Fatalf("%v %v", had, err)
	}
	if err := s2.Restore(prev, had); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(s2.Path); !errors.Is(err, os.ErrNotExist) {
		t.Errorf("the file should be gone: %v", err)
	}
	if left, _ := filepath.Glob(filepath.Join(filepath.Dir(s.Path), ".keyboard-*")); len(left) != 0 {
		t.Errorf("temp files left: %v", left)
	}
}

func TestAnUnusableFileReadsAsTheSeedLikeTheConsoleScript(t *testing.T) {
	s := store(t)
	_ = os.MkdirAll(filepath.Dir(s.Path), 0o755)
	_ = os.WriteFile(s.Path, []byte("XKBLAYOUT=\"de$(reboot)\"\n"), 0o644)
	cur, seeded, err := s.Current()
	if err != nil || !seeded || cur.Layout != "us" {
		t.Fatalf("%+v %v %v", cur, seeded, err)
	}
	// And the last line of a key wins, quotes are optional, a missing layout is US.
	got, ok := Parse(strings.NewReader("XKBLAYOUT=de\nXKBLAYOUT=\"fr\"\n# XKBLAYOUT=zz\n"))
	if !ok || got.Layout != "fr" || got.Model != "pc105" {
		t.Errorf("%+v %v", got, ok)
	}
}
