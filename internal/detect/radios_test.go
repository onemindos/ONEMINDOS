// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"sort"
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
		for _, part := range []string{`ATTRS{product}=="`, `GROUP="onemind-radio"`, `MODE="0660"`, `GOTO="onemind_radio_end"`, `-$attr{busnum}-$attr{devpath}"`} {
			if !strings.Contains(l, part) {
				t.Errorf("rule without %s: %s", part, l)
			}
		}
	}
	if lines != len(Radios.Devices) {
		t.Fatalf("%d named rules for %d table rows", lines, len(Radios.Devices))
	}
	for _, part := range []string{`ACTION=="remove", GOTO`, `KERNEL!="ttyUSB[0-9]*|ttyACM[0-9]*", GOTO`, `ATTRS{product}=="*[Zz][Bb][Tt]-2*"`, `SYMLINK+="onemind/zigbee-thread-$attr{busnum}-$attr{devpath}"`} {
		if !strings.Contains(got, part) {
			t.Errorf("rules lack %s", part)
		}
	}
}

func TestRadioTableKindsAreTheGoConstants(t *testing.T) {
	var kinds []string
	for k := range Radios.Kinds {
		kinds = append(kinds, k)
	}
	sort.Strings(kinds)
	if want := []string{RadioLoRa, RadioZigbee, RadioZigbeeThread}; !reflect.DeepEqual(kinds, want) {
		t.Fatalf("kinds %v, want %v", kinds, want)
	}
}

// The ids are shared by many products, so the product string decides; anything else is unknown.
func TestRadioLookup(t *testing.T) {
	for _, tc := range []struct{ id, product, kind, match string }{
		{"303a:831a", "ZBT-2", RadioZigbeeThread, RadioMatchProduct},
		{"303a:4001", "Home Assistant ZBT-2", RadioZigbeeThread, RadioMatchProduct},
		{"10c4:ea60", "SkyConnect v1.0", RadioZigbeeThread, RadioMatchProduct},
		{"10c4:ea60", "Sonoff Zigbee 3.0 USB Dongle Plus", RadioZigbee, RadioMatchProduct},
		{"1a86:55d4", "SONOFF Zigbee 3.0 USB Dongle Plus V2", RadioZigbee, RadioMatchProduct},
		{"1cf1:0030", "ConBee II", RadioZigbee, RadioMatchProduct},
		{"10c4:ea60", "CP2102 USB to UART Bridge Controller\n", RadioLoRa, RadioMatchChip},
		{"10c4:ea60", "CP2102N USB to UART Bridge Controller", "", ""}, // another chip: not guessed
		{"10c4:ea60", "", "", ""},                  // no product string
		{"1a86:55d4", "USB Single Serial", "", ""}, // same chip on a non-Sonoff board
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
	head := `{"schema":"onemind.radios/v1","name":"/dev/onemind/{kind}-{usb_port}","group":"onemind-radio","kinds":{"lora":"x","zigbee":"y"},"devices":[`
	row := func(kind, id, product, model, match string) string {
		return `{"kind":"` + kind + `","model":"` + model + `","id":"` + id + `","product":` + product + `,"match":"` + match + `"}`
	}
	good := row("zigbee", "1cf1:0030", `"*conbee*"`, "ConBee II", "product")
	if _, err := ParseRadioTable([]byte(head + good + `]}`)); err != nil {
		t.Fatalf("a good table: %v", err)
	}
	for name, devices := range map[string]string{
		"product row after a chip row": row("lora", "10c4:ea60", `"cp2102*"`, "Heltec", "chip") + "," + good,
		"unknown kind":                 row("zwave", "1cf1:0030", `"*x*"`, "X", "product"),
		"id not vvvv:pppp":             row("zigbee", "1CF1:0030", `"*x*"`, "X", "product"),
		"quote in the glob":            row("zigbee", "1cf1:0030", `"*\", RUN+=\"/bin/sh"`, "X", "product"),
		"udev alternation in the glob": row("zigbee", "1cf1:0030", `"a|b"`, "X", "product"),
		"uppercase glob":               row("zigbee", "1cf1:0030", `"*ConBee*"`, "X", "product"),
		"empty glob (any device)":      row("zigbee", "1cf1:0030", `""`, "X", "product"),
		"newline in the model":         row("zigbee", "1cf1:0030", `"*x*"`, `X\nRUN+=\"x\"`, "product"),
		"unknown match":                row("zigbee", "1cf1:0030", `"*x*"`, "X", "maybe"),
	} {
		if _, err := ParseRadioTable([]byte(head + devices + `]}`)); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	for name, s := range map[string]string{
		"a wifi kind":     strings.Replace(head, `"lora":"x"`, `"wifi":"x"`, 1) + `]}`,
		"another dir":     strings.Replace(head, "/dev/onemind/", "/dev/", 1) + `]}`,
		"another group":   strings.Replace(head, `"onemind-radio"`, `"dialout"`, 1) + `]}`,
		"another version": strings.Replace(head, "radios/v1", "radios/v2", 1) + `]}`,
	} {
		if _, err := ParseRadioTable([]byte(s)); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
}

// radioTree builds a box with one USB serial device on port 1-4 (ttyUSB3) and the given links.
func radioTree(t *testing.T, id, product string, links map[string]string) *Collector {
	t.Helper()
	root := t.TempDir()
	vid, pid, _ := strings.Cut(id, ":")
	files := map[string]string{
		"sys/bus/usb/devices/1-4/idVendor":  vid + "\n",
		"sys/bus/usb/devices/1-4/idProduct": pid + "\n",
		"sys/bus/usb/devices/1-4/product":   product + "\n",
		"sys/class/net/lo/uevent":           "INTERFACE=lo\n",
	}
	for rel, body := range files {
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

func serialOnly(c *Collector) []heartbeat.Radio {
	out := []heartbeat.Radio{}
	for _, r := range c.Capabilities(context.Background()).Radios {
		if r.Kind != heartbeat.RadioWiFi && r.Kind != heartbeat.RadioBluetooth && r.Kind != heartbeat.RadioCellular {
			out = append(out, r)
		}
	}
	return out
}

func TestSerialRadiosReportOnlyCurrentKnownNames(t *testing.T) {
	zbt2 := []heartbeat.Radio{{Kind: RadioZigbeeThread, Interface: "ttyUSB3"}}
	for _, tc := range []struct {
		name, id, product string
		links             map[string]string
		want              []heartbeat.Radio
	}{
		{"a ZBT-2 udev named", "303a:831a", "ZBT-2", map[string]string{"zigbee-thread-1-4": "../ttyUSB3"}, zbt2},
		{"an absolute link into /dev", "303a:831a", "ZBT-2", map[string]string{"zigbee-thread-1-4": "/dev/ttyUSB3"}, zbt2},
		{"unplugged: udev removed the link", "303a:831a", "ZBT-2", nil, []heartbeat.Radio{}},
		{"the name claims another port", "303a:831a", "ZBT-2", map[string]string{"zigbee-thread-1-5": "../ttyUSB3"}, []heartbeat.Radio{}},
		{"the name claims another kind", "303a:831a", "ZBT-2", map[string]string{"lora-1-4": "../ttyUSB3"}, []heartbeat.Radio{}},
		{"an unknown serial device someone linked", "0403:6001", "FT232R USB UART", map[string]string{"lora-1-4": "../ttyUSB3"}, []heartbeat.Radio{}},
		{"a kind not in the table", "303a:831a", "ZBT-2", map[string]string{"zwave-1-4": "../ttyUSB3"}, []heartbeat.Radio{}},
		{"a link to something that is not a USB tty", "303a:831a", "ZBT-2", map[string]string{"zigbee-thread-1-4": "../sda"}, []heartbeat.Radio{}},
		{"a link out of /dev", "303a:831a", "ZBT-2", map[string]string{"zigbee-thread-1-4": "/etc/ttyUSB3"}, []heartbeat.Radio{}},
		{"a name that is not kind-port", "303a:831a", "ZBT-2", map[string]string{"zbt2": "../ttyUSB3"}, []heartbeat.Radio{}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got := serialOnly(radioTree(t, tc.id, tc.product, tc.links))
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
	mustLink(t, "../ttyUSB0", filepath.Join(root, "dev/onemind/lora-1-1"))
	if r := NewFixture(root, "amd64").Capabilities(context.Background()).Radios; r == nil || len(r) != 0 {
		t.Fatalf("radios %+v, want [] (a dangling link is read and refused)", r)
	}
}
