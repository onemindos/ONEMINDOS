// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"encoding/json"
	"fmt"
	"os"
	"path"
	"regexp"
	"strings"

	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/sdk/schema"
)

// Known USB radio dongles (issue #732). sdk/schema/onemind.radios.json is the one table: the image's
// udev rules are rendered from it (RadioUdevRules, checked by a golden test), and a named radio is
// reported in the heartbeat only when its USB ids still match the row its name claims. A USB serial
// line that matches no row keeps the kernel's name: it is listed in tty_ports, never named, never
// granted (a grant passes only a /dev/onemind name).

// RadioTableSchema is the value of onemind.radios.json's "schema".
const RadioTableSchema = "onemind.radios/v1"

// RadioDir is where udev puts the stable names; RadioGroup owns them (mode 0660).
const (
	RadioDir   = "/dev/onemind"
	RadioGroup = "onemind-radio"
)

// Radio kinds of a known dongle (heartbeat Radio.Kind beside wifi, bluetooth and cellular).
const (
	RadioZigbee       = "zigbee"
	RadioZigbeeThread = "zigbee-thread"
	RadioLoRa         = "lora"
)

// How a row identifies its dongle: by a product string only that product uses, or only by the chip
// maker's default string (any board with that chip looks the same; the card says so).
const (
	RadioMatchProduct = "product"
	RadioMatchChip    = "chip"
)

// KnownRadio is one row of the table. Product is a lowercase glob over the lowercased USB product
// string.
type KnownRadio struct {
	Kind    string `json:"kind"`
	Model   string `json:"model"`
	ID      string `json:"id"`
	Product string `json:"product"`
	Match   string `json:"match"`
	Source  string `json:"source"`
}

// RadioTable is the parsed onemind.radios.json.
type RadioTable struct {
	Schema  string            `json:"schema"`
	Name    string            `json:"name"`
	Group   string            `json:"group"`
	Kinds   map[string]string `json:"kinds"`
	Devices []KnownRadio      `json:"devices"`
}

var (
	radioKindRe = regexp.MustCompile(`^[a-z]+(-[a-z]+)*$`)
	// A glob udev and path.Match read the same way: no quote, escape, alternation or class syntax.
	radioGlobRe = regexp.MustCompile(`^[a-z0-9 .*?_+-]{1,64}$`)
	radioTextRe = regexp.MustCompile(`^[A-Za-z0-9 .,()+_-]{1,64}$`)
	// A stable name: <kind>-<usb port>, e.g. lora-1-1.2 (a kind has no digits, so the split is exact).
	radioLinkRe = regexp.MustCompile(`^([a-z]+(?:-[a-z]+)*)-([0-9]+-[0-9]+(?:\.[0-9]+)*)$`)
	usbTTYRe    = regexp.MustCompile(`^tty(USB|ACM)[0-9]+$`)
)

// Radios is the table built into this binary.
var Radios = mustRadioTable(schema.Radios)

func mustRadioTable(s string) RadioTable {
	t, err := ParseRadioTable([]byte(s))
	if err != nil {
		panic("sdk/schema/onemind.radios.json: " + err.Error())
	}
	return t
}

// ParseRadioTable reads and checks the table: every row has a known kind, a vvvv:pppp id, a safe
// glob and model, and chip rows come after every product row (first match wins, as in udev).
func ParseRadioTable(b []byte) (RadioTable, error) {
	var t RadioTable
	if err := json.Unmarshal(b, &t); err != nil {
		return t, err
	}
	if t.Schema != RadioTableSchema || t.Name != RadioDir+"/{kind}-{usb_port}" || t.Group != RadioGroup {
		return t, fmt.Errorf("schema, name or group is not %s, %s/{kind}-{usb_port}, %s", RadioTableSchema, RadioDir, RadioGroup)
	}
	for k := range t.Kinds {
		if !radioKindRe.MatchString(k) || k == heartbeat.RadioWiFi || k == heartbeat.RadioBluetooth || k == heartbeat.RadioCellular {
			return t, fmt.Errorf("kind %q", k)
		}
	}
	chip := false
	for i, d := range t.Devices {
		switch {
		case t.Kinds[d.Kind] == "":
			return t, fmt.Errorf("row %d: unknown kind %q", i, d.Kind)
		case !usbIDRe.MatchString(d.ID):
			return t, fmt.Errorf("row %d: id %q is not vvvv:pppp", i, d.ID)
		case !radioGlobRe.MatchString(d.Product):
			return t, fmt.Errorf("row %d: product %q is not a lowercase glob", i, d.Product)
		case !radioTextRe.MatchString(d.Model):
			return t, fmt.Errorf("row %d: model %q", i, d.Model)
		case d.Match == RadioMatchChip:
			chip = true
		case d.Match != RadioMatchProduct:
			return t, fmt.Errorf("row %d: match %q", i, d.Match)
		case chip:
			return t, fmt.Errorf("row %d: a product row after a chip row would never win", i)
		}
	}
	return t, nil
}

var usbIDRe = regexp.MustCompile(`^[0-9a-f]{4}:[0-9a-f]{4}$`)

// Lookup returns the first row a USB device with this id and product string matches, or nil.
func (t RadioTable) Lookup(id, product string) *KnownRadio {
	product = strings.ToLower(strings.TrimSpace(product))
	for i, d := range t.Devices {
		if ok, _ := path.Match(d.Product, product); ok && d.ID == id && product != "" {
			return &t.Devices[i]
		}
	}
	return nil
}

// RadioDevice is the stable name a known radio of kind gets at a USB port path, e.g.
// /dev/onemind/lora-1-1.2.
func RadioDevice(kind, port string) string { return RadioDir + "/" + kind + "-" + port }

// UdevRules renders 70-onemind-radio.rules. The port part of the name comes from the USB device's
// own busnum and devpath attributes, so it equals the kernel's port path ("1-1.2").
func (t RadioTable) UdevRules() string {
	var b strings.Builder
	b.WriteString("# SPDX-License-Identifier: Apache-2.0\n" +
		"# Generated from sdk/schema/onemind.radios.json; do not edit. Regenerate with:\n" +
		"#   go test ./internal/detect -run TestRadioUdevRules -update\n" +
		"# Known USB radio dongles (issue #732) get a stable name, " + RadioDir + "/<kind>-<usb port>, owned by group\n" +
		"# " + RadioGroup + " (mode 0660), so a grant can pass exactly one radio into one app. Any other USB serial line\n" +
		"# keeps the kernel's name and Debian's defaults: listed in the heartbeat, never named, never granted.\n" +
		"ACTION==\"remove\", GOTO=\"onemind_radio_end\"\n" +
		"SUBSYSTEM!=\"tty\", GOTO=\"onemind_radio_end\"\n" +
		"KERNEL!=\"ttyUSB[0-9]*|ttyACM[0-9]*\", GOTO=\"onemind_radio_end\"\n")
	for _, d := range t.Devices {
		vid, pid, _ := strings.Cut(d.ID, ":")
		fmt.Fprintf(&b, "\n# %s (%s, matched by %s)\n", d.Model, d.Kind, d.Match)
		fmt.Fprintf(&b, "SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"%s\", ATTRS{idProduct}==\"%s\", ATTRS{product}==\"%s\", "+
			"SYMLINK+=\"onemind/%s-$attr{busnum}-$attr{devpath}\", GROUP=\"%s\", MODE=\"0660\", GOTO=\"onemind_radio_end\"\n",
			vid, pid, anyCase(d.Product), d.Kind, RadioGroup)
	}
	b.WriteString("\nLABEL=\"onemind_radio_end\"\n")
	return b.String()
}

// anyCase turns a lowercase glob into one udev matches in any case: "zbt-2" -> "[Zz][Bb][Tt]-2".
func anyCase(glob string) string {
	var b strings.Builder
	for _, r := range glob {
		if r >= 'a' && r <= 'z' {
			b.WriteString("[" + strings.ToUpper(string(r)) + string(r) + "]")
		} else {
			b.WriteRune(r)
		}
	}
	return b.String()
}

// serialRadios reports each stable name udev made under /dev/onemind, as Radio{kind, tty}, when the
// link is current: it points at a USB serial line, that line sits on the port the name claims, and
// the device there still matches a table row of that kind. ok is false when there is no RadioDir.
func (c *Collector) serialRadios() (out []heartbeat.Radio, ok bool) {
	links, ok := c.names(strings.TrimPrefix(RadioDir, "/"))
	if !ok {
		return nil, false
	}
	for _, n := range links {
		m := radioLinkRe.FindStringSubmatch(n)
		if m == nil {
			continue
		}
		target, err := os.Readlink(c.path(strings.TrimPrefix(RadioDir, "/") + "/" + n))
		tty := path.Base(target)
		if err != nil || !usbTTYRe.MatchString(tty) || (target != "../"+tty && target != "/dev/"+tty) {
			continue
		}
		port, id, dir := c.usbDevice("sys/class/tty/" + tty + "/device")
		if port != m[2] {
			continue // a stale or hand-made link: the line is not on the port the name claims
		}
		if row := Radios.Lookup(id, readAbs(dir+"/product")); row == nil || row.Kind != m[1] {
			continue
		}
		if out = append(out, heartbeat.Radio{Kind: m[1], Interface: tty}); len(out) == maxListed {
			break
		}
	}
	return out, true
}
