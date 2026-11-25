// SPDX-License-Identifier: Apache-2.0

// Package keymap is the box's keyboard layout (P-11): which layouts the image offers, what the owner chose, and
// the file that records it.
//
// The choice lives on /data, not in /etc, because the root is read-only and /data survives reboots and A/B
// updates. The file has the format of Debian's /etc/default/keyboard and is read by two things: the text console
// (onemind-console-keyboard, which loads it with ckbcomp and loadkeys, tty1-tty6 and so the tty2 login) and the
// kiosk screen (onemind_kiosk.py, which hands it to the compositor as XKB_DEFAULT_*). The list of layouts is the
// one the image's xkb-data package ships (rules/base.lst), the same list localectl and console-setup offer.
package keymap

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// Default paths on the image.
const (
	DefaultPath    = "/data/onemind/console/keyboard"
	DefaultCatalog = "/usr/share/X11/xkb/rules/base.lst"
)

// Seed is what the box uses before the owner chooses (the same as console-keyboard.default).
var Seed = Setting{Model: "pc105", Layout: "us"}

// Setting is a keyboard choice in the terms of /etc/default/keyboard.
type Setting struct {
	Model   string `json:"model"`
	Layout  string `json:"layout"`
	Variant string `json:"variant"`
	Options string `json:"options"`
}

// Variant is one variant of a layout ("nodeadkeys" of "de").
type Variant struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

// Layout is one layout the image offers with its variants.
type Layout struct {
	ID       string    `json:"id"`
	Name     string    `json:"name"`
	Variants []Variant `json:"variants"`
}

var (
	layoutRe  = regexp.MustCompile(`^[A-Za-z0-9_]{1,24}$`)
	variantRe = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)
	// valueRe is what the console script accepts in every field of the file (onemind-console-keyboard `ok`).
	valueRe = regexp.MustCompile(`^[A-Za-z0-9_,:+-]*$`)
	lineRe  = regexp.MustCompile(`^\s*(XKB[A-Z]+)="?([^"]*)"?\s*$`)
)

// ValidID reports whether layout (and variant, when not empty) have the shape of xkb names. It does not say the
// image offers them: Store.Check does.
func ValidID(layout, variant string) error {
	if !layoutRe.MatchString(layout) {
		return errors.New("layout must be 1-24 characters of A-Z a-z 0-9 _")
	}
	if variant != "" && !variantRe.MatchString(variant) {
		return errors.New("variant must be 1-32 characters of A-Z a-z 0-9 _ -")
	}
	return nil
}

// ErrUnknown: the image does not offer that layout or variant.
var ErrUnknown = errors.New("this image does not offer that keyboard layout")

// ParseCatalog reads xkb's rules/base.lst: the "! layout" section lists layouts, the "! variant" section lists
// "variant  layout: description". Layouts come back sorted by name; an unreadable file is an error, a variant of a
// layout that is not listed is dropped.
func ParseCatalog(r io.Reader) ([]Layout, error) {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64<<10), 1<<20)
	byID := map[string]*Layout{}
	var order []string
	type pending struct{ layout, id, name string }
	var variants []pending
	section := ""
	for sc.Scan() {
		line := strings.TrimRight(sc.Text(), " \t\r")
		if strings.HasPrefix(line, "!") {
			section = strings.TrimSpace(strings.TrimPrefix(line, "!"))
			continue
		}
		f := strings.Fields(line)
		if len(f) < 2 {
			continue
		}
		rest := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(line), f[0]))
		switch section {
		case "layout":
			if layoutRe.MatchString(f[0]) && byID[f[0]] == nil {
				byID[f[0]] = &Layout{ID: f[0], Name: rest, Variants: []Variant{}}
				order = append(order, f[0])
			}
		case "variant":
			if !strings.HasSuffix(f[1], ":") || !variantRe.MatchString(f[0]) {
				continue
			}
			name := strings.TrimSpace(strings.TrimPrefix(rest, f[1]))
			variants = append(variants, pending{strings.TrimSuffix(f[1], ":"), f[0], name})
		}
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if len(order) == 0 {
		return nil, errors.New("no layouts in the keyboard list")
	}
	for _, v := range variants {
		if l := byID[v.layout]; l != nil {
			l.Variants = append(l.Variants, Variant{ID: v.id, Name: v.name})
		}
	}
	out := make([]Layout, 0, len(order))
	for _, id := range order {
		l := byID[id]
		sort.SliceStable(l.Variants, func(i, j int) bool { return strings.ToLower(l.Variants[i].Name) < strings.ToLower(l.Variants[j].Name) })
		out = append(out, *l)
	}
	sort.SliceStable(out, func(i, j int) bool { return strings.ToLower(out[i].Name) < strings.ToLower(out[j].Name) })
	return out, nil
}

// Parse reads a keyboard file as data (never as shell), the way the console script does: the last line of a key
// wins, and a value with a character outside [A-Za-z0-9_,:+-] makes the whole file unusable (the boot then uses
// US). ok is false for such a file; the Seed is returned with it.
func Parse(r io.Reader) (s Setting, ok bool) {
	vals := map[string]string{}
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64<<10), 64<<10)
	for sc.Scan() {
		if m := lineRe.FindStringSubmatch(sc.Text()); m != nil {
			vals[m[1]] = m[2]
		}
	}
	for _, v := range vals {
		if !valueRe.MatchString(v) {
			return Seed, false
		}
	}
	s = Setting{Model: vals["XKBMODEL"], Layout: vals["XKBLAYOUT"], Variant: vals["XKBVARIANT"], Options: vals["XKBOPTIONS"]}
	if s.Model == "" {
		s.Model = Seed.Model
	}
	if s.Layout == "" {
		s.Layout = Seed.Layout
	}
	return s, true
}

// Render is the file for s, in /etc/default/keyboard format.
func Render(s Setting) string {
	return fmt.Sprintf("# SPDX-License-Identifier: Apache-2.0\n# The console and kiosk keyboard layout. Written by onemind-host (set-keymap); same format as /etc/default/keyboard.\n"+
		"XKBMODEL=%q\nXKBLAYOUT=%q\nXKBVARIANT=%q\nXKBOPTIONS=%q\n", s.Model, s.Layout, s.Variant, s.Options)
}

// Store is the keyboard file and the image's list of layouts. Zero values use the image's paths.
type Store struct {
	Path    string
	Catalog string
}

func (s Store) path() string {
	if s.Path == "" {
		return DefaultPath
	}
	return s.Path
}

func (s Store) catalog() string {
	if s.Catalog == "" {
		return DefaultCatalog
	}
	return s.Catalog
}

// Layouts is the list the image offers.
func (s Store) Layouts() ([]Layout, error) {
	f, err := os.Open(s.catalog())
	if err != nil {
		return nil, fmt.Errorf("the image has no keyboard layout list: %w", err)
	}
	defer f.Close()
	return ParseCatalog(f)
}

// Current is the owner's choice. seeded is true when nothing is chosen yet or the file is unusable (the box then
// runs the US layout, as the console script does).
func (s Store) Current() (cur Setting, seeded bool, err error) {
	f, err := os.Open(s.path())
	if errors.Is(err, os.ErrNotExist) {
		return Seed, true, nil
	}
	if err != nil {
		return Setting{}, false, err
	}
	defer f.Close()
	cur, ok := Parse(f)
	return cur, !ok, nil
}

// Check says whether the image offers layout and variant. It returns ErrUnknown (wrapped) when it does not.
func (s Store) Check(layout, variant string) error {
	if err := ValidID(layout, variant); err != nil {
		return err
	}
	all, err := s.Layouts()
	if err != nil {
		return err
	}
	for _, l := range all {
		if l.ID != layout {
			continue
		}
		if variant == "" {
			return nil
		}
		for _, v := range l.Variants {
			if v.ID == variant {
				return nil
			}
		}
		return fmt.Errorf("%w: %s has no variant %s", ErrUnknown, layout, variant)
	}
	return fmt.Errorf("%w: %s", ErrUnknown, layout)
}

// Write records layout and variant, keeping the model and options already there. The file is written whole (temp
// file, fsync, rename, fsync of the folder) so a power cut leaves the old file or the new one. It returns the
// previous setting and whether there was a file, for Restore.
func (s Store) Write(layout, variant string) (prev Setting, had bool, err error) {
	cur, _, err := s.Current()
	if err != nil {
		return Setting{}, false, err
	}
	_, statErr := os.Stat(s.path())
	had = statErr == nil
	next := cur
	next.Layout, next.Variant = layout, variant
	if !valueRe.MatchString(next.Model) || !valueRe.MatchString(next.Options) {
		next.Model, next.Options = Seed.Model, ""
	}
	return cur, had, writeAtomic(s.path(), []byte(Render(next)))
}

// Restore puts back what Write returned: the previous file, or no file when there was none.
func (s Store) Restore(prev Setting, had bool) error {
	if !had {
		if err := os.Remove(s.path()); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
		return nil
	}
	return writeAtomic(s.path(), []byte(Render(prev)))
}

func writeAtomic(path string, data []byte) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, ".keyboard-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Chmod(0o644); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp.Name(), path); err != nil {
		return err
	}
	d, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}

// Label names a choice in one short line: "de" or "de (nodeadkeys)".
func Label(layout, variant string) string {
	if variant == "" {
		return layout
	}
	return layout + " (" + variant + ")"
}
