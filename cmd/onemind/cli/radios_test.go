// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"strings"
	"testing"
)

// `onemind radios` shows each radio-found card with its type and port; an unknown serial device
// is listed with no name (#732).
func TestRadiosListsKnownAndUnknownSerialDevices(t *testing.T) {
	isolate(t)
	g := newFakeGW(t)
	t.Setenv("ONEMIND_HUB", g.srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "radios")
	if r.code != 0 {
		t.Fatalf("radios %+v", r)
	}
	lines := strings.Split(strings.TrimSpace(r.out), "\n")
	if len(lines) != 4 || !strings.HasPrefix(lines[0], "NODE_ID") {
		t.Fatalf("radios table %q", r.out)
	}
	for i, want := range [][]string{
		{"zigbee-thread", "Home Assistant Connect ZBT-2", "1-2", "ttyACM0", "/dev/onemind/zigbee-thread-1-2"},
		{"lora", "Heltec WiFi LoRa 32 V3 (chip)", "1-1", "/dev/onemind/lora-1-1"},
		{"unknown", "1-3", "ttyUSB1"},
	} {
		for _, w := range want {
			if !strings.Contains(lines[i+1], w) {
				t.Errorf("row %d %q lacks %q", i+1, lines[i+1], w)
			}
		}
	}
	if strings.Contains(lines[3], "/dev/onemind") {
		t.Errorf("an unknown serial device was named: %q", lines[3])
	}
	if r := run(t, "", false, "radios", "--json"); r.code != 0 || !strings.Contains(r.out, `"device": null`) {
		t.Fatalf("radios --json %+v", r)
	}
}
