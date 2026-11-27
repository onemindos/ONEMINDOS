// SPDX-License-Identifier: Apache-2.0

package cot

import (
	"bytes"
	"encoding/xml"
	"errors"
	"fmt"
	"io"
	"math"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Version is the only CoT event version this package reads and writes.
const Version = "2.0"

// Unknown is the value TAK's sample events use for an unknown height or
// error estimate (seven nines). TAK's protobuf schema comment says 999999 (six
// nines), so IsUnknown accepts both; OneMind always writes Unknown.
const Unknown = 9999999.0

// unknownProto is the six-nines value named in TAK's cotevent.proto comment.
const unknownProto = 999999.0

// IsUnknown reports whether v is one of the two "unknown" conventions.
func IsUnknown(v float64) bool { return v == Unknown || v == unknownProto }

// MaxEventBytes caps one received event. A TAK situational-awareness packet
// is usually well under 2 KB; a larger one is refused before it is parsed.
const MaxEventBytes = 16 * 1024

// MaxSendBytes caps one event OneMind encodes, so it fits a single UDP
// datagram without heavy IP fragmentation.
const MaxSendBytes = 8 * 1024

// minTime is the earliest event time accepted; anything earlier is a broken
// clock or a crafted packet.
var minTime = time.Date(2000, 1, 1, 0, 0, 0, 0, time.UTC)

// MaxUIDLen caps the uid attribute.
const MaxUIDLen = 256

// MaxClockSkew is how far into the future an event's time may be before it is
// refused, to allow for clocks on field devices that are slightly ahead.
const MaxClockSkew = 5 * time.Minute

// MaxStaleAhead caps how long an event may stay valid. A marker that claims
// to be valid for more than a year is almost certainly wrong.
const MaxStaleAhead = 366 * 24 * time.Hour

// TimeLayout is the CoT time format: ISO 8601 in UTC, milliseconds, "Z".
const TimeLayout = "2006-01-02T15:04:05.000Z"

// Time is a CoT timestamp. It marshals as TimeLayout and unmarshals any
// RFC 3339 time, which is what TAK clients send.
type Time struct{ time.Time }

// MarshalXMLAttr writes the time in UTC with millisecond precision.
func (t Time) MarshalXMLAttr(name xml.Name) (xml.Attr, error) {
	return xml.Attr{Name: name, Value: t.UTC().Format(TimeLayout)}, nil
}

// UnmarshalXMLAttr reads an RFC 3339 time (with or without fractions).
func (t *Time) UnmarshalXMLAttr(attr xml.Attr) error {
	v, err := time.Parse(time.RFC3339Nano, attr.Value)
	if err != nil {
		return fmt.Errorf("cot: bad %s time %q", attr.Name.Local, attr.Value)
	}
	t.Time = v.UTC()
	return nil
}

// Event is one CoT event.
type Event struct {
	XMLName xml.Name `xml:"event"`
	Version string   `xml:"version,attr"`
	UID     string   `xml:"uid,attr"`
	Type    string   `xml:"type,attr"`
	How     string   `xml:"how,attr"`
	Time    Time     `xml:"time,attr"`
	Start   Time     `xml:"start,attr"`
	Stale   Time     `xml:"stale,attr"`
	Access  string   `xml:"access,attr,omitempty"`
	Point   Point    `xml:"point"`
	Detail  *Detail  `xml:"detail,omitempty"`
}

// Point is the event's location: WGS 84 latitude and longitude in degrees,
// hae is the height above the ellipsoid in metres, ce and le are the circular
// (horizontal) and linear (vertical) error in metres. Unknown means unknown.
type Point struct {
	Lat float64 `xml:"lat,attr"`
	Lon float64 `xml:"lon,attr"`
	HAE float64 `xml:"hae,attr"`
	CE  float64 `xml:"ce,attr"`
	LE  float64 `xml:"le,attr"`
}

// decimal formats v as a plain xs:decimal. The CoT base schema types point
// and track numbers as decimals, which forbid the exponent form (1e-05,
// 9.999999e+06) that strconv's 'g' and encoding/xml's float default write.
func decimal(v float64) string { return strconv.FormatFloat(v, 'f', -1, 64) }

// MarshalXML writes the point with plain-decimal attributes.
func (p Point) MarshalXML(enc *xml.Encoder, start xml.StartElement) error {
	start.Attr = append(start.Attr,
		xml.Attr{Name: xml.Name{Local: "lat"}, Value: decimal(p.Lat)},
		xml.Attr{Name: xml.Name{Local: "lon"}, Value: decimal(p.Lon)},
		xml.Attr{Name: xml.Name{Local: "hae"}, Value: decimal(p.HAE)},
		xml.Attr{Name: xml.Name{Local: "ce"}, Value: decimal(p.CE)},
		xml.Attr{Name: xml.Name{Local: "le"}, Value: decimal(p.LE)},
	)
	return enc.EncodeElement(struct{}{}, start)
}

// MarshalXML writes the track with plain-decimal attributes.
func (t Track) MarshalXML(enc *xml.Encoder, start xml.StartElement) error {
	start.Attr = append(start.Attr,
		xml.Attr{Name: xml.Name{Local: "course"}, Value: decimal(t.Course)},
		xml.Attr{Name: xml.Name{Local: "speed"}, Value: decimal(t.Speed)},
	)
	return enc.EncodeElement(struct{}{}, start)
}

// Detail holds the detail elements OneMind reads and writes. Elements this
// package does not model are kept as raw XML in Extra for display and
// debugging only: Extra is never interpreted and Encode never writes it, so
// untrusted XML is never re-emitted (OneMind never re-sends inbound events).
type Detail struct {
	Contact  *Contact  `xml:"contact,omitempty"`
	Group    *Group    `xml:"__group,omitempty"`
	Takv     *Takv     `xml:"takv,omitempty"`
	Track    *Track    `xml:"track,omitempty"`
	Status   *Status   `xml:"status,omitempty"`
	Remarks  *Remarks  `xml:"remarks,omitempty"`
	Usericon *Usericon `xml:"usericon,omitempty"`
	Links    []Link    `xml:"link,omitempty"`
	Extra    []RawXML  `xml:",any"`
}

// Contact is the callsign shown next to the marker, and optionally where to
// reach the sender.
type Contact struct {
	Callsign string `xml:"callsign,attr,omitempty"`
	Endpoint string `xml:"endpoint,attr,omitempty"`
}

// Group is the TAK team colour and role.
type Group struct {
	Name string `xml:"name,attr,omitempty"`
	Role string `xml:"role,attr,omitempty"`
}

// Takv names the software that produced the event.
type Takv struct {
	Device   string `xml:"device,attr,omitempty"`
	Platform string `xml:"platform,attr,omitempty"`
	OS       string `xml:"os,attr,omitempty"`
	Version  string `xml:"version,attr,omitempty"`
}

// Track is the direction of travel in degrees from true north and the speed
// in metres per second.
type Track struct {
	Course float64 `xml:"course,attr"`
	Speed  float64 `xml:"speed,attr"`
}

// Status carries the battery level (percent) of the device.
type Status struct {
	Battery string `xml:"battery,attr,omitempty"`
}

// Remarks is free text attached to the event.
type Remarks struct {
	Text string `xml:",chardata"`
}

// Usericon is an icon-set path that TAK clients use instead of the default
// symbol for the type.
type Usericon struct {
	IconSetPath string `xml:"iconsetpath,attr,omitempty"`
}

// Link relates this event to another one (for example the parent marker).
type Link struct {
	UID      string `xml:"uid,attr,omitempty"`
	Type     string `xml:"type,attr,omitempty"`
	Relation string `xml:"relation,attr,omitempty"`
}

// RawXML is a detail element this package does not model.
type RawXML struct {
	XMLName xml.Name
	Attrs   []xml.Attr `xml:",any,attr"`
	Inner   string     `xml:",innerxml"`
}

var (
	// typeRe: dash-separated atoms, the first a lower-case letter
	// ("a" atom, "b" bits, "t" tasking, ...), then short alphanumeric atoms,
	// for example a-f-G-U-C or b-m-p-s-m.
	typeRe = regexp.MustCompile(`^[a-z](-[A-Za-z0-9.]{1,16}){0,15}$`)
	// howRe: dash-separated lower-case atoms, for example h-e, m-g, h-g-i-g-o.
	howRe = regexp.MustCompile(`^[a-z](-[a-z]{1,8}){0,7}$`)
)

// Validation errors. Use errors.Is to test for them.
var (
	ErrTooLarge = errors.New("cot: event larger than the size cap")
	ErrDoctype  = errors.New("cot: DOCTYPE and entity declarations are refused")
	ErrInvalid  = errors.New("cot: invalid event")
)

func invalid(format string, args ...any) error {
	return fmt.Errorf("%w: %s", ErrInvalid, fmt.Sprintf(format, args...))
}

// Validate checks the event against the rules this package enforces. now is
// the receiver's clock; pass time.Time{} to skip the clock checks (for
// example when reading a recorded fixture).
func (e *Event) Validate(now time.Time) error {
	if e.Version != Version {
		return invalid("version %q, want %q", e.Version, Version)
	}
	if e.UID == "" || len(e.UID) > MaxUIDLen {
		return invalid("uid must be 1 to %d bytes", MaxUIDLen)
	}
	if strings.ContainsFunc(e.UID, func(r rune) bool { return r < 0x20 || r == 0x7f }) {
		return invalid("uid has control characters")
	}
	if !typeRe.MatchString(e.Type) {
		return invalid("type %q is not a CoT type", e.Type)
	}
	if !howRe.MatchString(e.How) {
		return invalid("how %q is not a CoT how code", e.How)
	}
	if e.Time.IsZero() || e.Start.IsZero() || e.Stale.IsZero() {
		return invalid("time, start and stale are required")
	}
	if e.Time.Before(minTime) || e.Start.Before(minTime) {
		return invalid("time and start must be after %s", minTime.Format("2006"))
	}
	if e.Stale.Before(e.Start.Time) {
		return invalid("stale is before start")
	}
	if e.Stale.Sub(e.Start.Time) > MaxStaleAhead {
		return invalid("stale is more than %s after start", MaxStaleAhead)
	}
	if !now.IsZero() && e.Time.Sub(now) > MaxClockSkew {
		return invalid("time is more than %s in the future", MaxClockSkew)
	}
	if !now.IsZero() && e.Start.Sub(now) > MaxClockSkew {
		return invalid("start is more than %s in the future", MaxClockSkew)
	}
	return e.Point.validate()
}

func (p Point) validate() error {
	for _, v := range []float64{p.Lat, p.Lon, p.HAE, p.CE, p.LE} {
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return invalid("point has a NaN or infinite value")
		}
	}
	if p.Lat < -90 || p.Lat > 90 {
		return invalid("lat %v out of range", p.Lat)
	}
	if p.Lon < -180 || p.Lon > 180 {
		return invalid("lon %v out of range", p.Lon)
	}
	if p.CE < 0 || p.LE < 0 {
		return invalid("ce and le must not be negative")
	}
	if !IsUnknown(p.HAE) && (p.HAE < -12000 || p.HAE > 100000) {
		return invalid("hae %v out of range", p.HAE)
	}
	return nil
}

// IsStale reports whether the event is no longer valid at now.
func (e *Event) IsStale(now time.Time) bool { return !now.Before(e.Stale.Time) }

// Decode parses one CoT XML event and validates it against now (see
// Validate). It refuses input larger than MaxEventBytes and any DOCTYPE, so
// entity tricks never reach the parser.
func Decode(data []byte, now time.Time) (*Event, error) {
	if len(data) > MaxEventBytes {
		return nil, ErrTooLarge
	}
	if bytes.Contains(data, []byte("<!")) && containsDecl(data) {
		return nil, ErrDoctype
	}
	dec := xml.NewDecoder(bytes.NewReader(data))
	dec.Strict = true
	dec.Entity = nil // only the five predefined XML entities
	var e Event
	if err := dec.Decode(&e); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalid, err)
	}
	// Anything after the root element other than whitespace is refused, so a
	// packet cannot smuggle a second event.
	for {
		tok, err := dec.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("%w: %v", ErrInvalid, err)
		}
		switch t := tok.(type) {
		case xml.CharData:
			if len(bytes.TrimSpace(t)) != 0 {
				return nil, invalid("text after the event")
			}
		case xml.Comment, xml.ProcInst:
		default:
			return nil, invalid("data after the event")
		}
	}
	if e.XMLName.Space != "" {
		return nil, invalid("namespaced event element")
	}
	if err := e.Validate(now); err != nil {
		return nil, err
	}
	return &e, nil
}

// containsDecl reports a <!DOCTYPE or <!ENTITY declaration (CDATA sections,
// which also start with "<!", are allowed).
func containsDecl(data []byte) bool {
	up := bytes.ToUpper(data)
	return bytes.Contains(up, []byte("<!DOCTYPE")) || bytes.Contains(up, []byte("<!ENTITY"))
}

// xmlHeader is the declaration TAK clients put in front of every event.
const xmlHeader = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`

// Encode validates the event (clock checks skipped) and returns its XML. It
// writes only the modelled fields: Detail.Extra and any namespace a decoded
// event carried are dropped, so the output is always well-formed and never
// echoes untrusted raw XML.
func Encode(e *Event) ([]byte, error) {
	if err := e.Validate(time.Time{}); err != nil {
		return nil, err
	}
	c := *e
	c.XMLName = xml.Name{Local: "event"}
	if e.Detail != nil {
		d := *e.Detail
		d.Extra = nil
		c.Detail = &d
	}
	body, err := xml.Marshal(&c)
	if err != nil {
		return nil, fmt.Errorf("cot: encode: %w", err)
	}
	out := make([]byte, 0, len(xmlHeader)+len(body))
	out = append(out, xmlHeader...)
	out = append(out, body...)
	if len(out) > MaxSendBytes {
		return nil, ErrTooLarge
	}
	return out, nil
}
