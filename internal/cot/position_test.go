// SPDX-License-Identifier: Apache-2.0

package cot

import (
	"errors"
	"testing"
	"time"
)

func ptr(v float64) *float64 { return &v }

func machinePos() Position {
	return Position{
		Kind: KindMachine, ID: "m-42", Label: "Garage hub",
		Lat: 40.7, Lon: -74.0, HAE: ptr(15), Accuracy: ptr(4),
		Course: ptr(90), Speed: ptr(0.5),
		Time: time.Date(2026, 11, 26, 15, 0, 0, 0, time.UTC),
		Note: "rack 1",
	}
}

func TestToEventMachine(t *testing.T) {
	e, err := ToEvent(machinePos())
	if err != nil {
		t.Fatal(err)
	}
	if e.UID != "onemind-machine-m-42" || e.Type != "a-f-G-E" || e.How != "m-g" {
		t.Fatalf("header %+v", e)
	}
	if got := e.Stale.Sub(e.Start.Time); got != DefaultStale {
		t.Fatalf("stale window %v", got)
	}
	if e.Point.HAE != 15 || e.Point.CE != 4 || e.Point.LE != Unknown {
		t.Fatalf("point %+v", e.Point)
	}
	d := e.Detail
	if d.Contact.Callsign != "Garage hub" || d.Track.Course != 90 || d.Remarks.Text != "rack 1" || d.Takv.Device != "OneMind" {
		t.Fatalf("detail %+v", d)
	}
	if _, err := Encode(e); err != nil {
		t.Fatal(err)
	}
}

func TestToEventTypes(t *testing.T) {
	for kind, want := range map[Kind]string{
		KindHub: "a-f-G-I", KindSensor: "a-f-G-E-S", KindCamera: "a-f-G-E-S", KindAlert: "b-m-p-s-m",
	} {
		p := machinePos()
		p.Kind = kind
		e, err := ToEvent(p)
		if err != nil || e.Type != want {
			t.Fatalf("%s: type %v err %v, want %s", kind, e, err, want)
		}
	}
}

func TestToEventPrivacy(t *testing.T) {
	person := machinePos()
	person.Kind = KindPerson
	if _, err := ToEvent(person); !errors.Is(err, ErrNotShareable) {
		t.Fatalf("person without opt-in: %v", err)
	}
	person.OwnerOptIn = true
	if e, err := ToEvent(person); err != nil || e.Type != "a-f-G-U-C" {
		t.Fatalf("person with opt-in: %v %v", e, err)
	}
	person.Minor = true // opt-in never overrides the child rule
	if _, err := ToEvent(person); !errors.Is(err, ErrNotShareable) {
		t.Fatalf("child: %v", err)
	}
	m := machinePos()
	m.Minor = true // e.g. a child's tablet registered as a machine
	if _, err := ToEvent(m); !errors.Is(err, ErrNotShareable) {
		t.Fatalf("child's machine: %v", err)
	}
}

func TestToEventRefusesEchoAndBadInput(t *testing.T) {
	marker := machinePos()
	marker.Kind = KindMarker
	if _, err := ToEvent(marker); !errors.Is(err, ErrNotShareable) {
		t.Fatalf("marker re-send: %v", err)
	}
	fromTAK := machinePos()
	fromTAK.SourceUID = "ANDROID-1"
	if _, err := ToEvent(fromTAK); !errors.Is(err, ErrNotShareable) {
		t.Fatalf("inbound re-send: %v", err)
	}
	for name, mutate := range map[string]func(*Position){
		"no id":     func(p *Position) { p.ID = "" },
		"space id":  func(p *Position) { p.ID = "a b" },
		"no time":   func(p *Position) { p.Time = time.Time{} },
		"bad kind":  func(p *Position) { p.Kind = "robot" },
		"bad lat":   func(p *Position) { p.Lat = 91 },
		"neg error": func(p *Position) { p.Accuracy = ptr(-1) },
		"null fix":  func(p *Position) { p.Lat, p.Lon = 0, 0 },
	} {
		p := machinePos()
		mutate(&p)
		if _, err := ToEvent(p); !errors.Is(err, ErrInvalid) {
			t.Fatalf("%s: want ErrInvalid, got %v", name, err)
		}
	}
}

func TestFromEvent(t *testing.T) {
	e, err := Decode(fixture(t, "sa-team-member.xml"), fixtureNow)
	if err != nil {
		t.Fatal(err)
	}
	p, err := FromEvent(e, fixtureNow)
	if err != nil {
		t.Fatal(err)
	}
	if p.Kind != KindMarker || p.Label != "RIVER-1" || p.SourceUID != e.UID || p.SourceType != "a-f-G-U-C" {
		t.Fatalf("marker %+v", p)
	}
	if p.HAE == nil || *p.HAE != 12.5 || p.VerticalAccuracy != nil || *p.Speed != 1.2 {
		t.Fatalf("values %+v", p)
	}
	if p.Stale != 6*time.Minute {
		t.Fatalf("stale %v", p.Stale)
	}
	// A marker from TAK must never be re-sent as if it were OneMind's own.
	if _, err := ToEvent(p); !errors.Is(err, ErrNotShareable) {
		t.Fatalf("inbound marker re-sent: %v", err)
	}
}

func TestFromEventRefusesEchoAndStale(t *testing.T) {
	own, err := ToEvent(machinePos())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := FromEvent(own, own.Time.Time); !errors.Is(err, ErrInvalid) {
		t.Fatalf("echo accepted: %v", err)
	}
	e, _ := Decode(fixture(t, "sa-team-member.xml"), fixtureNow)
	if _, err := FromEvent(e, e.Stale.Add(time.Second)); !errors.Is(err, ErrInvalid) {
		t.Fatalf("stale accepted: %v", err)
	}
	e.Point.Lat, e.Point.Lon = 0, 0
	if _, err := FromEvent(e, fixtureNow); !errors.Is(err, ErrInvalid) {
		t.Fatalf("0,0 accepted: %v", err)
	}
}

func TestMachineRoundTripThroughXML(t *testing.T) {
	e, err := ToEvent(machinePos())
	if err != nil {
		t.Fatal(err)
	}
	b, err := Encode(e)
	if err != nil {
		t.Fatal(err)
	}
	back, err := Decode(b, e.Time.Time)
	if err != nil {
		t.Fatal(err)
	}
	// Strip the OneMind prefix to read it the way another hub would see a
	// third-party event with the same content.
	back.UID = "peer-" + back.UID
	p, err := FromEvent(back, e.Time.Time)
	if err != nil {
		t.Fatal(err)
	}
	if p.Lat != 40.7 || p.Lon != -74.0 || *p.HAE != 15 || *p.Accuracy != 4 || p.Label != "Garage hub" || p.Note != "rack 1" {
		t.Fatalf("round trip %+v", p)
	}
}
