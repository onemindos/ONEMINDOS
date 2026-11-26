// SPDX-License-Identifier: Apache-2.0

package cot

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

// Kind is what a OneMind position belongs to.
type Kind string

// Kinds the bridge maps. Marker is used for positions that came in from a TAK
// device and have no OneMind owner.
const (
	KindHub     Kind = "hub"     // the OneMind box itself
	KindMachine Kind = "machine" // a joined OneMind machine
	KindSensor  Kind = "sensor"  // a sensor with a fixed or reported location
	KindCamera  Kind = "camera"  // a camera
	KindAlert   Kind = "alert"   // an alert with a location
	KindPerson  Kind = "person"  // a household member who opted in
	KindMarker  Kind = "marker"  // anything received from TAK
)

// UIDPrefix starts the uid of every event OneMind sends, so inbound events
// that echo OneMind's own markers can be recognised and dropped.
const UIDPrefix = "onemind-"

// DefaultStale is how long an outgoing position stays valid on TAK maps when
// the caller does not say. Positions are resent well before this.
const DefaultStale = 2 * time.Minute

// typeFor maps a OneMind kind to its CoT type. The a-f-... types are
// "friendly" atoms in the MIL-STD-2525 tree (G = ground; E = equipment,
// E-S = sensor, I = installation, U-C = combat unit, the type ATAK uses for
// a team member); b-m-p-s-m is the point "spot" marker. See the design doc.
var typeFor = map[Kind]string{
	KindHub:     "a-f-G-I",
	KindMachine: "a-f-G-E",
	KindSensor:  "a-f-G-E-S",
	KindCamera:  "a-f-G-E-S",
	KindAlert:   "b-m-p-s-m",
	KindPerson:  "a-f-G-U-C",
}

// Position is a OneMind location as the bridge sees it. Lat and Lon are WGS 84
// degrees; HAE, Accuracy and VerticalAccuracy are metres, nil when unknown.
type Position struct {
	Kind  Kind
	ID    string // stable id inside OneMind (machine id, sensor id, ...)
	Label string // callsign shown on TAK maps

	Lat, Lon         float64
	HAE              *float64
	Accuracy         *float64 // horizontal error (CoT ce)
	VerticalAccuracy *float64 // vertical error (CoT le)
	Course, Speed    *float64 // degrees from true north, metres per second

	Time  time.Time     // when the position was measured
	Stale time.Duration // how long it stays valid; DefaultStale when 0
	Note  string        // optional remarks

	// Privacy flags. A person is only ever sent with OwnerOptIn set, and a
	// position marked Minor is never sent at all, whatever the other flags say.
	OwnerOptIn bool
	Minor      bool

	// Set on positions that came in from TAK.
	SourceUID  string
	SourceType string
}

// ErrNotShareable means the privacy rules forbid sending this position.
var ErrNotShareable = errors.New("cot: position may not be shared")

// ToEvent turns a OneMind position into a CoT event. It refuses children's
// locations and people without the owner's opt-in (ErrNotShareable), and it
// never sends a position that came in from TAK back out (no echo loops).
func ToEvent(p Position) (*Event, error) {
	if p.Minor {
		return nil, fmt.Errorf("%w: a child's location never leaves the box", ErrNotShareable)
	}
	if p.Kind == KindPerson && !p.OwnerOptIn {
		return nil, fmt.Errorf("%w: a person is shared only with the owner's opt-in", ErrNotShareable)
	}
	if p.Kind == KindMarker || p.SourceUID != "" {
		return nil, fmt.Errorf("%w: positions received from TAK are not re-sent", ErrNotShareable)
	}
	typ, ok := typeFor[p.Kind]
	if !ok {
		return nil, invalid("unknown kind %q", p.Kind)
	}
	if p.ID == "" || strings.ContainsAny(p.ID, " \t\r\n") {
		return nil, invalid("position id must be set and have no spaces")
	}
	if p.Time.IsZero() {
		return nil, invalid("position time is required")
	}
	if p.Lat == 0 && p.Lon == 0 {
		return nil, invalid("0,0 is almost always a missing fix")
	}
	stale := p.Stale
	if stale <= 0 {
		stale = DefaultStale
	}
	t := p.Time.UTC()
	e := &Event{
		Version: Version,
		UID:     UIDPrefix + string(p.Kind) + "-" + p.ID,
		Type:    typ,
		How:     "m-g", // machine-generated, from GPS or a surveyed fix
		Time:    Time{t},
		Start:   Time{t},
		Stale:   Time{t.Add(stale)},
		Point: Point{
			Lat: p.Lat, Lon: p.Lon,
			HAE: orUnknown(p.HAE), CE: orUnknown(p.Accuracy), LE: orUnknown(p.VerticalAccuracy),
		},
		Detail: &Detail{
			Takv: &Takv{Device: "OneMind", Platform: "OneMind OS", OS: "Debian"},
		},
	}
	label := p.Label
	if label == "" {
		label = string(p.Kind) + " " + p.ID
	}
	e.Detail.Contact = &Contact{Callsign: label}
	if p.Course != nil || p.Speed != nil {
		e.Detail.Track = &Track{Course: deref(p.Course), Speed: deref(p.Speed)}
	}
	if p.Note != "" {
		e.Detail.Remarks = &Remarks{Text: p.Note}
	}
	if err := e.Validate(time.Time{}); err != nil {
		return nil, err
	}
	return e, nil
}

// FromEvent turns a received CoT event into a OneMind map marker. Events that
// carry OneMind's own uid prefix are refused (they are echoes of what this box
// sent), and so are stale ones. The result is display data only: nothing in
// it is ever an instruction to act.
func FromEvent(e *Event, now time.Time) (Position, error) {
	if err := e.Validate(now); err != nil {
		return Position{}, err
	}
	if strings.HasPrefix(e.UID, UIDPrefix) {
		return Position{}, invalid("event %q is an echo of a OneMind marker", e.UID)
	}
	if !now.IsZero() && e.IsStale(now) {
		return Position{}, invalid("event %q is stale", e.UID)
	}
	// OneMind's position schema refuses exactly 0,0 (onemind.datapoint
	// schema): TAK devices without a fix often report it.
	if e.Point.Lat == 0 && e.Point.Lon == 0 {
		return Position{}, invalid("event %q has no fix (0,0)", e.UID)
	}
	p := Position{
		Kind:       KindMarker,
		ID:         e.UID,
		Label:      e.UID,
		Lat:        e.Point.Lat,
		Lon:        e.Point.Lon,
		HAE:        known(e.Point.HAE),
		Accuracy:   known(e.Point.CE),
		Time:       e.Time.Time,
		Stale:      e.Stale.Sub(e.Start.Time),
		SourceUID:  e.UID,
		SourceType: e.Type,
	}
	p.VerticalAccuracy = known(e.Point.LE)
	if d := e.Detail; d != nil {
		if d.Contact != nil && d.Contact.Callsign != "" {
			p.Label = d.Contact.Callsign
		}
		if d.Track != nil {
			c, s := d.Track.Course, d.Track.Speed
			p.Course, p.Speed = &c, &s
		}
		if d.Remarks != nil {
			p.Note = strings.TrimSpace(d.Remarks.Text)
		}
	}
	return p, nil
}

func orUnknown(v *float64) float64 {
	if v == nil {
		return Unknown
	}
	return *v
}

func known(v float64) *float64 {
	if IsUnknown(v) {
		return nil
	}
	return &v
}

func deref(v *float64) float64 {
	if v == nil {
		return 0
	}
	return *v
}
