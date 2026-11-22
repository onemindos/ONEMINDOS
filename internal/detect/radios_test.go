// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// The image ships rules rendered from sdk/schema/onemind.radios.json; this keeps them in step.
const radioRulesFile = "../../os/rootfs/layers/onemind/usr/lib/udev/rules.d/70-onemind-radio.rules"

func TestRadioUdevRules(t *testing.T) {
	got := Radios.UdevRules()
	if *updateGolden {
		if err := os.WriteFile(radioRulesFile, []byte(got), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	want, err := os.ReadFile(radioRulesFile)
	if err != nil {
		t.Fatal(err)
	}
	if got != string(want) {
		t.Fatalf("%s is not what onemind.radios.json renders; run go test ./internal/detect -run TestRadioUdevRules -update", radioRulesFile)
	}
	lines := 0
	for _, l := range strings.Split(got, "\n") {
		if !strings.Contains(l, "SYMLINK+=") {
			continue
		}
		lines++
		// First match wins and only a matched line is named and handed to the radio group.
		for _, part := range []string{`SUBSYSTEMS=="usb", ATTRS{idVendor}=="`, `PROGRAM="/usr/lib/onemind/radio-name `,
			`SYMLINK+="onemind/%c"`, `GROUP="onemind-radio"`, `MODE="0660"`, `GOTO="onemind_radio_end"`} {
			if !strings.Contains(l, part) {
				t.Errorf("rule without %s: %s", part, l)
			}
		}
	}
	if lines != len(Radios.Devices) {
		t.Fatalf("%d named rules for %d table rows", lines, len(Radios.Devices))
	}
	for _, part := range []string{
		`ACTION=="remove", GOTO`, `KERNEL!="ttyUSB[0-9]*|ttyACM[0-9]*", GOTO`,
		`ATTRS{idVendor}=="303a", ATTRS{idProduct}=="831a", ATTRS{product}=="*[Zz][Bb][Tt]-2*", PROGRAM="/usr/lib/onemind/radio-name zigbee-thread"`,
		// The ThinkNode-M2's CH340K is a generic chip: named by id, its card asks the owner.
		`ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7522", PROGRAM="/usr/lib/onemind/radio-name lora"`,
	} {
		if !strings.Contains(got, part) {
			t.Errorf("rules lack %s", part)
		}
	}
}

func TestRadioTableKindsAndConfirm(t *testing.T) {
	for _, k := range RadioKinds {
		if Radios.Kinds[k] == "" {
			t.Errorf("table lacks kind %s", k)
		}
	}
	if c := Radios.Confirm[heartbeat.RadioLoRa]; c.Profile != "meshcore-companion-usb" || c.Label != "MeshCore companion (USB)" {
		t.Fatalf("lora confirm %+v", c)
	}
	if len(Radios.Confirm) != 1 {
		t.Fatalf("only a LoRa radio asks the owner to confirm its firmware: %+v", Radios.Confirm)
	}
}

// A product row needs its own product string; an id row (a generic chip) matches its id alone.
func TestRadioLookup(t *testing.T) {
	for _, tc := range []struct{ id, product, kind, match string }{
		{"303a:831a", "ZBT-2", heartbeat.RadioZigbeeThread, RadioMatchProduct},
		{"303a:4001", "Home Assistant ZBT-2", heartbeat.RadioZigbeeThread, RadioMatchProduct},
		{"10c4:ea60", "SkyConnect v1.0", heartbeat.RadioZigbeeThread, RadioMatchProduct},
		{"10c4:ea60", "Sonoff Zigbee 3.0 USB Dongle Plus", heartbeat.RadioZigbee, RadioMatchProduct},
		{"1a86:55d4", "SONOFF Zigbee 3.0 USB Dongle Plus V2", heartbeat.RadioZigbee, RadioMatchProduct},
		{"1cf1:0030", "ConBee II", heartbeat.RadioZigbee, RadioMatchProduct},
		{"1a86:7522", "USB Serial", heartbeat.RadioLoRa, RadioMatchID},
		{"1a86:7522", "", heartbeat.RadioLoRa, RadioMatchID},
		{"10c4:ea60", "CP2102 USB to UART Bridge Controller", "", ""}, // a bare chip string: not guessed
		{"10c4:ea60", "", "", ""},
		{"1a86:55d4", "USB Single Serial", "", ""}, // same chip on a non-Sonoff board
		{"1a86:7523", "USB Serial", "", ""},        // the CH340 next door is not on the list
		{"303a:4001", "SONOFF Dongle Max CC2674P10", "", ""},
		{"0403:6001", "FT232R USB UART", "", ""},
		{"303a:831b", "ZBT-2", "", ""},
	} {
		row := Radios.Lookup(tc.id, tc.product)
		if tc.kind == "" {
			if row != nil {
				t.Errorf("%s %q matched %+v; an unknown serial device must stay unnamed", tc.id, tc.product, *row)
			}
			continue
		}
		if row == nil || row.Kind != tc.kind || row.Match != tc.match {
			t.Errorf("%s %q = %+v, want %s by %s", tc.id, tc.product, row, tc.kind, tc.match)
		}
	}
}

func TestRadioTableRefusesUnsafeRows(t *testing.T) {
	head := `{"schema":"onemind.radios/v1","name":"/dev/onemind/{kind}{n}","group":"onemind-radio",` +
		`"kinds":{"lora":"x","zigbee":"y","zigbee-thread":"z"},"confirm":{"lora":{"profile":"meshcore-companion-usb","label":"MeshCore companion (USB)"}},"devices":[`
	row := func(kind, id, product, model, match string) string {
		return `{"kind":"` + kind + `","model":"` + model + `","id":"` + id + `","product":` + product + `,"match":"` + match + `"}`
	}
	good := row("zigbee", "1cf1:0030", `"*conbee*"`, "ConBee II", "product") + "," + row("lora", "1a86:7522", `""`, "CH340K", "id")
	if _, err := ParseRadioTable([]byte(head + good + `]}`)); err != nil {
		t.Fatalf("a good table: %v", err)
	}
	for name, devices := range map[string]string{
		"product row after an id row":  row("lora", "1a86:7522", `""`, "CH340K", "id") + "," + row("zigbee", "1cf1:0030", `"*conbee*"`, "ConBee II", "product"),
		"id row with a product glob":   row("lora", "1a86:7522", `"usb*"`, "CH340K", "id"),
		"unknown kind":                 row("zwave", "1cf1:0030", `"*x*"`, "X", "product"),
		"id not vvvv:pppp":             row("zigbee", "1CF1:0030", `"*x*"`, "X", "product"),
		"quote in the glob":            row("zigbee", "1cf1:0030", `"*\", RUN+=\"/bin/sh"`, "X", "product"),
		"udev alternation in the glob": row("zigbee", "1cf1:0030", `"a|b"`, "X", "product"),
		"uppercase glob":               row("zigbee", "1cf1:0030", `"*ConBee*"`, "X", "product"),
		"empty glob on a product row":  row("zigbee", "1cf1:0030", `""`, "X", "product"),
		"newline in the model":         row("zigbee", "1cf1:0030", `"*x*"`, `X\nRUN+=\"x\"`, "product"),
		"unknown match":                row("zigbee", "1cf1:0030", `"*x*"`, "X", "maybe"),
	} {
		if _, err := ParseRadioTable([]byte(head + devices + `]}`)); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	for name, s := range map[string]string{
		"a wifi kind":           strings.Replace(head, `"lora":"x"`, `"wifi":"x"`, 1) + `]}`,
		"a missing kind":        strings.Replace(head, `,"zigbee-thread":"z"`, ``, 1) + `]}`,
		"another dir":           strings.Replace(head, "/dev/onemind/", "/dev/", 1) + `]}`,
		"another group":         strings.Replace(head, `"onemind-radio"`, `"dialout"`, 1) + `]}`,
		"another version":       strings.Replace(head, "radios/v1", "radios/v2", 1) + `]}`,
		"confirm of a non-kind": strings.Replace(head, `"confirm":{"lora"`, `"confirm":{"wifi"`, 1) + `]}`,
		"a bad confirm profile": strings.Replace(head, `"meshcore-companion-usb"`, `"Mesh Core"`, 1) + `]}`,
	} {
		if _, err := ParseRadioTable([]byte(s)); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
}

// The radiohub fixture: the founder's ThinkNode-M2 (CH340K 1a86:7522) named lora0, a ZBT-2 named
// zigbee-thread0, and an FTDI serial adapter nobody knows, listed in tty_ports and never a radio.
func TestRadioHubFixture(t *testing.T) {
	p := fixture(t, "radiohub", "amd64").Capabilities(context.Background())
	lora0, zbt0 := "/dev/onemind/lora0", "/dev/onemind/zigbee-thread0"
	want := []heartbeat.Radio{
		{Kind: heartbeat.RadioLoRa, Interface: "ttyUSB0", Device: &lora0},
		{Kind: heartbeat.RadioZigbeeThread, Interface: "ttyACM0", Device: &zbt0},
	}
	if !reflect.DeepEqual(serialOnly(p.Radios), want) {
		t.Fatalf("radios %+v", p.Radios)
	}
	listed := map[string]string{}
	for _, tp := range p.TTYPorts {
		listed[tp.Name] = *tp.USBID + "@" + *tp.USBPort
	}
	if listed["ttyUSB1"] != "0403:6001@1-3" || listed["ttyUSB0"] != "1a86:7522@1-1" || listed["ttyACM0"] != "303a:831a@1-2" {
		t.Fatalf("tty_ports %+v", listed)
	}
}

// radioTree builds a box with one USB serial device on port 1-4 (ttyUSB3) and the given links.
func radioTree(t *testing.T, id, product string, links map[string]string) *Collector {
	t.Helper()
	root := t.TempDir()
	vid, pid, _ := strings.Cut(id, ":")
	for rel, body := range map[string]string{
		"sys/bus/usb/devices/1-4/idVendor":  vid + "\n",
		"sys/bus/usb/devices/1-4/idProduct": pid + "\n",
		"sys/bus/usb/devices/1-4/product":   product + "\n",
		"sys/class/net/lo/uevent":           "INTERFACE=lo\n",
		"sys/class/tty/ttyS0/type":          "0\n",
	} {
		mustWrite(t, filepath.Join(root, rel), body)
	}
	if err := os.MkdirAll(filepath.Join(root, "sys/bus/usb/devices/1-4/1-4:1.0"), 0o755); err != nil {
		t.Fatal(err)
	}
	mustLink(t, "../../../bus/usb/devices/1-4/1-4:1.0", filepath.Join(root, "sys/class/tty/ttyUSB3/device"))
	for name, target := range links {
		mustLink(t, target, filepath.Join(root, "dev/onemind", name))
	}
	return NewFixture(root, "amd64")
}

func mustWrite(t *testing.T, p, body string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

func mustLink(t *testing.T, target, p string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, p); err != nil {
		t.Fatal(err)
	}
}

func serialOnly(rs []heartbeat.Radio) []heartbeat.Radio {
	out := []heartbeat.Radio{}
	for _, r := range rs {
		if r.Kind != heartbeat.RadioWiFi && r.Kind != heartbeat.RadioBluetooth && r.Kind != heartbeat.RadioCellular {
			out = append(out, r)
		}
	}
	return out
}

func TestSerialRadiosReportOnlyCurrentKnownNames(t *testing.T) {
	dev := func(n string) *string { d := "/dev/onemind/" + n; return &d }
	m2 := func(n string) []heartbeat.Radio {
		return []heartbeat.Radio{{Kind: heartbeat.RadioLoRa, Interface: "ttyUSB3", Device: dev(n)}}
	}
	none := []heartbeat.Radio{}
	for _, tc := range []struct {
		name, id, product string
		links             map[string]string
		want              []heartbeat.Radio
	}{
		{"the M2's CH340K udev named", "1a86:7522", "USB Serial", map[string]string{"lora0": "../ttyUSB3"}, m2("lora0")},
		{"a CH340K with no product string", "1a86:7522", "", map[string]string{"lora0": "../ttyUSB3"}, m2("lora0")},
		{"the second LoRa radio", "1a86:7522", "USB Serial", map[string]string{"lora1": "../ttyUSB3"}, m2("lora1")},
		{"an absolute link into /dev", "1a86:7522", "USB Serial", map[string]string{"lora15": "/dev/ttyUSB3"}, m2("lora15")},
		{"two names for one line: the first wins", "1a86:7522", "", map[string]string{"lora0": "../ttyUSB3", "lora1": "../ttyUSB3"}, m2("lora0")},
		{"a ZBT-2", "303a:831a", "ZBT-2", map[string]string{"zigbee-thread0": "../ttyUSB3"},
			[]heartbeat.Radio{{Kind: heartbeat.RadioZigbeeThread, Interface: "ttyUSB3", Device: dev("zigbee-thread0")}}},
		{"unplugged: udev removed the link", "1a86:7522", "USB Serial", nil, none},
		{"the name claims another kind", "303a:831a", "ZBT-2", map[string]string{"lora0": "../ttyUSB3"}, none},
		{"an unknown serial device someone linked", "0403:6001", "FT232R USB UART", map[string]string{"lora0": "../ttyUSB3"}, none},
		{"the CH340 next door someone linked", "1a86:7523", "USB Serial", map[string]string{"lora0": "../ttyUSB3"}, none},
		{"a kind not in the table", "1a86:7522", "", map[string]string{"zwave0": "../ttyUSB3"}, none},
		{"a number past the limit", "1a86:7522", "", map[string]string{"lora16": "../ttyUSB3"}, none},
		{"a link to a line that is gone", "1a86:7522", "", map[string]string{"lora0": "../ttyUSB9"}, none},
		{"a link to something that is not a USB tty", "1a86:7522", "", map[string]string{"lora0": "../ttyS0"}, none},
		{"a link out of /dev", "1a86:7522", "", map[string]string{"lora0": "/etc/ttyUSB3"}, none},
		{"a name that is not kind-number", "1a86:7522", "", map[string]string{"m2": "../ttyUSB3", "lora-1-4": "../ttyUSB3"}, none},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got := serialOnly(radioTree(t, tc.id, tc.product, tc.links).Capabilities(context.Background()).Radios)
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("radios %+v, want %+v", got, tc.want)
			}
		})
	}
}

// Without /dev/onemind or any radio directory the list stays null (unknown), not empty.
func TestSerialRadiosUnknownWithoutAnyRadioDirectory(t *testing.T) {
	root := t.TempDir()
	mustWrite(t, filepath.Join(root, "sys/bus/usb/devices/.keep"), "")
	if r := NewFixture(root, "amd64").Capabilities(context.Background()).Radios; r != nil {
		t.Fatalf("radios %+v, want null", r)
	}
	mustLink(t, "../ttyUSB0", filepath.Join(root, "dev/onemind/lora0"))
	if r := NewFixture(root, "amd64").Capabilities(context.Background()).Radios; r == nil || len(r) != 0 {
		t.Fatalf("radios %+v, want [] (a dangling link is read and refused)", r)
	}
}

// A wifi, bluetooth or cellular radio never carries a device: the field stays out of the JSON.
func TestNetworkRadiosCarryNoDevice(t *testing.T) {
	for _, r := range fixture(t, "minipc", "amd64").Capabilities(context.Background()).Radios {
		if r.Device != nil {
			t.Errorf("%+v", r)
		}
	}
}
