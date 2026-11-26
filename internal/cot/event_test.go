// SPDX-License-Identifier: Apache-2.0

package cot

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func fixture(t *testing.T, name string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("testdata", name))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

var fixtureNow = time.Date(2026, 11, 26, 15, 3, 0, 0, time.UTC)

func TestDecodeTeamMember(t *testing.T) {
	e, err := Decode(fixture(t, "sa-team-member.xml"), fixtureNow)
	if err != nil {
		t.Fatal(err)
	}
	if e.UID != "ANDROID-0000000000000001" || e.Type != "a-f-G-U-C" || e.How != "h-e" {
		t.Fatalf("header: %+v", e)
	}
	if e.Point.Lat != 40.689247 || e.Point.Lon != -74.044502 || e.Point.HAE != 12.5 || e.Point.LE != Unknown {
		t.Fatalf("point: %+v", e.Point)
	}
	d := e.Detail
	if d == nil || d.Contact.Callsign != "RIVER-1" || d.Group.Name != "Cyan" || d.Group.Role != "Team Member" {
		t.Fatalf("detail: %+v", d)
	}
	if d.Takv.Platform != "ATAK-CIV" || d.Track.Course != 270 || d.Track.Speed != 1.2 || d.Status.Battery != "88" {
		t.Fatalf("detail: takv %+v track %+v status %+v", d.Takv, d.Track, d.Status)
	}
	if want := time.Date(2026, 11, 26, 15, 6, 0, 0, time.UTC); !e.Stale.Equal(want) {
		t.Fatalf("stale %v want %v", e.Stale, want)
	}
}

func TestDecodeSpotMarkerEntitiesAndLinks(t *testing.T) {
	e, err := Decode(fixture(t, "spot-marker.xml"), fixtureNow)
	if err != nil {
		t.Fatal(err)
	}
	if e.Detail.Remarks.Text != "Meet here & wait" {
		t.Fatalf("remarks %q", e.Detail.Remarks.Text)
	}
	if len(e.Detail.Links) != 1 || e.Detail.Links[0].Relation != "p-p" {
		t.Fatalf("links %+v", e.Detail.Links)
	}
}

func TestRoundTripKeepsUnknownDetail(t *testing.T) {
	for _, name := range []string{"sa-team-member.xml", "spot-marker.xml", "unknown-detail.xml"} {
		t.Run(name, func(t *testing.T) {
			e, err := Decode(fixture(t, name), fixtureNow)
			if err != nil {
				t.Fatal(err)
			}
			out, err := Encode(e)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.HasPrefix(out, []byte(`<?xml version="1.0"`)) {
				t.Fatalf("no XML header: %s", out)
			}
			again, err := Decode(out, fixtureNow)
			if err != nil {
				t.Fatalf("re-decode: %v\n%s", err, out)
			}
			if again.UID != e.UID || again.Point != e.Point || !again.Stale.Equal(e.Stale.Time) {
				t.Fatalf("round trip changed the event:\n%+v\n%+v", e, again)
			}
			if name == "unknown-detail.xml" {
				if len(again.Detail.Extra) != 2 || !bytes.Contains(out, []byte(`geopointsrc="USER"`)) {
					t.Fatalf("unknown detail lost: %s", out)
				}
			}
		})
	}
}

func TestEncodeTimeFormat(t *testing.T) {
	e, err := Decode(fixture(t, "spot-marker.xml"), fixtureNow)
	if err != nil {
		t.Fatal(err)
	}
	out, _ := Encode(e)
	if !bytes.Contains(out, []byte(`time="2026-11-26T15:01:00.000Z"`)) {
		t.Fatalf("time not in CoT format: %s", out)
	}
}

func validEvent() *Event {
	t0 := time.Date(2026, 11, 26, 15, 0, 0, 0, time.UTC)
	return &Event{
		Version: Version, UID: "u1", Type: "a-f-G", How: "m-g",
		Time: Time{t0}, Start: Time{t0}, Stale: Time{t0.Add(time.Minute)},
		Point: Point{Lat: 1, Lon: 2, HAE: Unknown, CE: Unknown, LE: Unknown},
	}
}

func TestValidate(t *testing.T) {
	cases := map[string]func(*Event){
		"version":       func(e *Event) { e.Version = "1.0" },
		"empty uid":     func(e *Event) { e.UID = "" },
		"long uid":      func(e *Event) { e.UID = strings.Repeat("x", MaxUIDLen+1) },
		"control uid":   func(e *Event) { e.UID = "a\nb" },
		"type":          func(e *Event) { e.Type = "A-f-G" },
		"type spaces":   func(e *Event) { e.Type = "a-f G" },
		"how":           func(e *Event) { e.How = "M-G" },
		"no stale":      func(e *Event) { e.Stale = Time{} },
		"stale<start":   func(e *Event) { e.Stale = Time{e.Start.Add(-time.Second)} },
		"stale too far": func(e *Event) { e.Stale = Time{e.Start.Add(MaxStaleAhead + time.Hour)} },
		"future time":   func(e *Event) { e.Time = Time{fixtureNow.Add(time.Hour)} },
		"lat":           func(e *Event) { e.Point.Lat = 90.1 },
		"lon":           func(e *Event) { e.Point.Lon = -180.5 },
		"negative ce":   func(e *Event) { e.Point.CE = -1 },
		"hae":           func(e *Event) { e.Point.HAE = 1e6 },
	}
	if err := validEvent().Validate(fixtureNow); err != nil {
		t.Fatalf("valid event refused: %v", err)
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			e := validEvent()
			mutate(e)
			if err := e.Validate(fixtureNow); !errors.Is(err, ErrInvalid) {
				t.Fatalf("want ErrInvalid, got %v", err)
			}
		})
	}
}

func TestDecodeRefusesHostileInput(t *testing.T) {
	ok := string(fixture(t, "spot-marker.xml"))
	cases := map[string]struct {
		in   string
		want error
	}{
		"doctype":    {`<?xml version="1.0"?><!DOCTYPE event [<!ENTITY x "y">]>` + ok[strings.Index(ok, "<event"):], ErrDoctype},
		"entity":     {strings.Replace(ok, "&amp;", "&bogus;", 1), ErrInvalid},
		"two events": {ok + ok[strings.Index(ok, "<event"):], ErrInvalid},
		"not xml":    {"hello", ErrInvalid},
		"wrong root": {`<foo version="2.0"/>`, ErrInvalid},
		"too large":  {ok + strings.Repeat(" ", MaxEventBytes), ErrTooLarge},
	}
	for name, c := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := Decode([]byte(c.in), fixtureNow); !errors.Is(err, c.want) {
				t.Fatalf("want %v, got %v", c.want, err)
			}
		})
	}
}

func TestDecodeAllowsCDATA(t *testing.T) {
	in := strings.Replace(string(fixture(t, "spot-marker.xml")), "Meet here &amp; wait", "<![CDATA[a < b]]>", 1)
	e, err := Decode([]byte(in), fixtureNow)
	if err != nil {
		t.Fatal(err)
	}
	if e.Detail.Remarks.Text != "a < b" {
		t.Fatalf("remarks %q", e.Detail.Remarks.Text)
	}
}

func TestUnknownConventions(t *testing.T) {
	e := validEvent()
	e.Point.HAE = 999999 // six nines, as TAK's protobuf comment says
	if err := e.Validate(fixtureNow); err != nil {
		t.Fatalf("six-nines hae refused: %v", err)
	}
	if known(999999) != nil || known(Unknown) != nil || known(0) == nil {
		t.Fatal("unknown detection wrong")
	}
}

func TestIsStale(t *testing.T) {
	e := validEvent()
	if e.IsStale(e.Start.Time) || !e.IsStale(e.Stale.Time) {
		t.Fatal("stale boundary wrong")
	}
}

func FuzzDecode(f *testing.F) {
	for _, n := range []string{"sa-team-member.xml", "spot-marker.xml", "unknown-detail.xml"} {
		b, err := os.ReadFile(filepath.Join("testdata", n))
		if err != nil {
			f.Fatal(err)
		}
		f.Add(b)
	}
	f.Fuzz(func(t *testing.T, data []byte) {
		e, err := Decode(data, time.Time{})
		if err != nil {
			return
		}
		// Anything Decode accepts must encode and decode again.
		out, err := Encode(e)
		if err != nil {
			t.Fatalf("accepted event does not encode: %v", err)
		}
		if _, err := Decode(out, time.Time{}); err != nil {
			t.Fatalf("encoded event does not decode: %v\n%s", err, out)
		}
	})
}
