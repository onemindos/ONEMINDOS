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
// udev rules are rendered from it (UdevRules, checked by a golden test), and a named radio is
// reported in the heartbeat only when the USB device behind its link still matches a row of the kind
// its name claims. A USB serial line that matches no row keeps the kernel's name: it is listed in
// tty_ports, never named, never granted (a grant passes only a /dev/onemind name). Nothing here
// opens a device: detection reads sysfs and links only, so no radio is probed before its owner
// confirms it.

// RadioTableSchema is the value of onemind.radios.json's "schema".
const RadioTableSchema = "onemind.radios/v1"

// RadioDir is where udev puts the stable names; RadioGroup owns them (mode 0660); RadioNamer is
// the helper udev runs to pick the number (os/rootfs/layers/onemind/usr/lib/onemind/radio-name).
const (
	RadioDir   = "/dev/onemind"
	RadioGroup = "onemind-radio"
	RadioNamer = "/usr/lib/onemind/radio-name"
)

// How a row identifies its dongle: by its id and a product string only that product uses, or by
// the id alone (a generic USB-serial chip: the card says the id proves nothing).
const (
	RadioMatchProduct = "product"
	RadioMatchID      = "id"
)

// KnownRadio is one row of the table. Product is a lowercase glob over the lowercased USB product
// string; it is empty exactly when Match is "id".
type KnownRadio struct {
	Kind    string `json:"kind"`
	Model   string `json:"model"`
	ID      string `json:"id"`
	Product string `json:"product"`
	Match   string `json:"match"`
	Source  string `json:"source"`
}

// RadioConfirm is what the owner confirms on the card of a radio of that kind before anything may
// open it (lora: "MeshCore companion (USB)").
type RadioConfirm struct {
	Profile string `json:"profile"`
	Label   string `json:"label"`
}

// RadioTable is the parsed onemind.radios.json.
type RadioTable struct {
	Schema  string                  `json:"schema"`
	Name    string                  `json:"name"`
	Group   string                  `json:"group"`
	Kinds   map[string]string       `json:"kinds"`
	Confirm map[string]RadioConfirm `json:"confirm"`
	Devices []KnownRadio            `json:"devices"`
}

var (
	// A glob udev and path.Match read the same way: no quote, escape, alternation or class syntax.
	radioGlobRe    = regexp.MustCompile(`^[a-z0-9 .*?_+-]{1,64}$`)
	radioTextRe    = regexp.MustCompile(`^[A-Za-z0-9 .,()+_-]{1,64}$`)
	radioProfileRe = regexp.MustCompile(`^[a-z][a-z0-9-]{1,39}$`)
	usbIDRe        = regexp.MustCompile(`^[0-9a-f]{4}:[0-9a-f]{4}$`)
	// A stable name: <kind><n>, e.g. lora0 or zigbee-thread1 (a kind has no digits, so the split is exact).
	radioLinkRe = regexp.MustCompile(`^([a-z]+(?:-[a-z]+)*)([0-9]|1[0-5])$`)
	usbTTYRe    = regexp.MustCompile(`^tty(USB|ACM)[0-9]+$`)
)

// RadioKinds are the dongle kinds the image names, in the order the table and udev helper list them.
var RadioKinds = []string{heartbeat.RadioZigbee, heartbeat.RadioZigbeeThread, heartbeat.RadioLoRa}

// MaxRadiosPerKind bounds <n>: the helper never hands out a number above MaxRadiosPerKind-1.
const MaxRadiosPerKind = 16

// Radios is the table built into this binary.
var Radios = mustRadioTable(schema.Radios)

func mustRadioTable(s string) RadioTable {
	t, err := ParseRadioTable([]byte(s))
	if err != nil {
		panic("sdk/schema/onemind.radios.json: " + err.Error())
	}
	return t
}

// ParseRadioTable reads and checks the table: the kinds are exactly RadioKinds, every row has a
// vvvv:pppp id, a safe glob (empty only for an id row) and model, and id rows come after every
// product row (first match wins, as in udev).
func ParseRadioTable(b []byte) (RadioTable, error) {
	var t RadioTable
	if err := json.Unmarshal(b, &t); err != nil {
		return t, err
	}
	if t.Schema != RadioTableSchema || t.Name != RadioDir+"/{kind}{n}" || t.Group != RadioGroup {
		return t, fmt.Errorf("schema, name or group is not %s, %s/{kind}{n}, %s", RadioTableSchema, RadioDir, RadioGroup)
	}
	if len(t.Kinds) != len(RadioKinds) {
		return t, fmt.Errorf("kinds must be exactly %v", RadioKinds)
	}
	for _, k := range RadioKinds {
		if t.Kinds[k] == "" {
			return t, fmt.Errorf("kinds must be exactly %v", RadioKinds)
		}
	}
	for k, c := range t.Confirm {
		if t.Kinds[k] == "" || !radioProfileRe.MatchString(c.Profile) || !radioTextRe.MatchString(c.Label) {
			return t, fmt.Errorf("confirm %q", k)
		}
	}
	idRows := false
	for i, d := range t.Devices {
		switch {
		case t.Kinds[d.Kind] == "":
			return t, fmt.Errorf("row %d: unknown kind %q", i, d.Kind)
		case !usbIDRe.MatchString(d.ID):
			return t, fmt.Errorf("row %d: id %q is not vvvv:pppp", i, d.ID)
		case !radioTextRe.MatchString(d.Model):
			return t, fmt.Errorf("row %d: model %q", i, d.Model)
		case d.Match == RadioMatchID:
			if d.Product != "" {
				return t, fmt.Errorf("row %d: an id row has no product glob", i)
			}
			idRows = true
		case d.Match != RadioMatchProduct:
			return t, fmt.Errorf("row %d: match %q", i, d.Match)
		case !radioGlobRe.MatchString(d.Product):
			return t, fmt.Errorf("row %d: product %q is not a lowercase glob", i, d.Product)
		case idRows:
			return t, fmt.Errorf("row %d: a product row after an id row would never win", i)
		}
	}
	return t, nil
}

// Lookup returns the first row a USB device with this id and product string matches, or nil.
func (t RadioTable) Lookup(id, product string) *KnownRadio {
	product = strings.ToLower(strings.TrimSpace(product))
	for i, d := range t.Devices {
		if d.ID != id {
			continue
		}
		if d.Match == RadioMatchID {
			return &t.Devices[i]
		}
		if ok, _ := path.Match(d.Product, product); ok && product != "" {
			return &t.Devices[i]
		}
	}
	return nil
}

// UdevRules renders 70-onemind-radio.rules. The helper prints <kind><n>; it only reads sysfs and
// its own claims in /run, never the device.
func (t RadioTable) UdevRules() string {
	var b strings.Builder
	b.WriteString("# SPDX-License-Identifier: Apache-2.0\n" +
		"# Generated from sdk/schema/onemind.radios.json; do not edit. Regenerate with:\n" +
		"#   go test ./internal/detect -run TestRadioUdevRules -update\n" +
		"# Known USB radio dongles (issue #732) get a stable name, " + RadioDir + "/<kind><n> (the first LoRa radio is\n" +
		"# lora0), owned by group " + RadioGroup + " (mode 0660), so a grant can pass exactly one radio into one app.\n" +
		"# " + RadioNamer + " picks <n>; nothing here opens the device. Any other USB serial line keeps the\n" +
		"# kernel's name and Debian's defaults: listed in the heartbeat, never named, never granted.\n" +
		"ACTION==\"remove\", GOTO=\"onemind_radio_end\"\n" +
		"SUBSYSTEM!=\"tty\", GOTO=\"onemind_radio_end\"\n" +
		"KERNEL!=\"ttyUSB[0-9]*|ttyACM[0-9]*\", GOTO=\"onemind_radio_end\"\n")
	for _, d := range t.Devices {
		vid, pid, _ := strings.Cut(d.ID, ":")
		fmt.Fprintf(&b, "\n# %s (%s, matched by %s)\n", d.Model, d.Kind, d.Match)
		fmt.Fprintf(&b, "SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"%s\", ATTRS{idProduct}==\"%s\", ", vid, pid)
		if d.Match == RadioMatchProduct {
			fmt.Fprintf(&b, "ATTRS{product}==\"%s\", ", anyCase(d.Product))
		}
		fmt.Fprintf(&b, "PROGRAM=\"%s %s\", SYMLINK+=\"onemind/%%c\", GROUP=\"%s\", MODE=\"0660\", GOTO=\"onemind_radio_end\"\n",
			RadioNamer, d.Kind, RadioGroup)
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

// serialRadios reports each stable name udev made under /dev/onemind as Radio{kind, tty, device}
// when the link is current: it points at a USB serial line and the USB device behind that line
// still matches a table row of the kind the name claims. ok is false when there is no RadioDir.
func (c *Collector) serialRadios() (out []heartbeat.Radio, ok bool) {
	dir := strings.TrimPrefix(RadioDir, "/")
	links, ok := c.names(dir)
	if !ok {
		return nil, false
	}
	seen := map[string]bool{}
	for _, n := range links {
		m := radioLinkRe.FindStringSubmatch(n)
		if m == nil || Radios.Kinds[m[1]] == "" {
			continue
		}
		target, err := os.Readlink(c.path(dir + "/" + n))
		tty := path.Base(target)
		if err != nil || !usbTTYRe.MatchString(tty) || (target != "../"+tty && target != "/dev/"+tty) || seen[tty] {
			continue // one name per line: a second link to the same line is stale
		}
		_, id, usb := c.usbDevice("sys/class/tty/" + tty + "/device")
		if usb == "" {
			continue // unplugged, or not a USB line: a stale or hand-made link
		}
		if row := Radios.Lookup(id, readAbs(usb+"/product")); row == nil || row.Kind != m[1] {
			continue
		}
		seen[tty] = true
		dev := RadioDir + "/" + n
		if out = append(out, heartbeat.Radio{Kind: m[1], Interface: tty, Device: &dev}); len(out) == maxListed {
			break
		}
	}
	return out, true
}
