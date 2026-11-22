// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"os"
	"path/filepath"
	"regexp"
	"testing"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

var updateGolden = flag.Bool("update", false, "rewrite testdata/profile/*.json from the fixtures")

// smiRTX is what nvidia-smi prints for the RTX box's card (VRAM in MiB, compute capability).
const smiRTX = "00000000:01:00.0, 8188, 8.9\n"

// The acceptance test of #618: a Raspberry Pi 5 (Hailo-8L HAT, SD card, camera module), an x86
// mini PC (Intel iGPU and NPU, NVMe, USB radios, webcam) and an RTX box produce the documents in
// testdata/profile/, which are the reviewed shape later work reads. Run with -update to rewrite.
func TestProfileGoldenDocuments(t *testing.T) {
	for _, tc := range []struct{ dir, arch string }{{"rpi5", "arm64"}, {"minipc", "amd64"}, {"x86efi", "amd64"}} {
		t.Run(tc.dir, func(t *testing.T) {
			c := fixture(t, tc.dir, tc.arch)
			if tc.dir == "x86efi" {
				fakeTools(c, map[string]string{
					"nvidia-smi --query-gpu=pci.bus_id,memory.total,compute_cap --format=csv,noheader,nounits": smiRTX,
				}, "nvidia-smi")
			}
			got, err := json.MarshalIndent(c.Capabilities(context.Background()), "", "  ")
			if err != nil {
				t.Fatal(err)
			}
			got = append(got, '\n')
			golden := filepath.Join("testdata", "profile", tc.dir+".json")
			if *updateGolden {
				if err := os.WriteFile(golden, got, 0o644); err != nil {
					t.Fatal(err)
				}
			}
			want, err := os.ReadFile(golden)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(got, want) {
				t.Fatalf("%s profile differs from %s:\n%s", tc.dir, golden, got)
			}
			privacy(t, string(got))
		})
	}
}

func privacy(t *testing.T, s string) {
	t.Helper()
	for _, bad := range []*regexp.Regexp{
		regexp.MustCompile(`(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}`),
		regexp.MustCompile(`\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`),
		regexp.MustCompile(`(?i)serial|by-id|GPU-0000|uuid`),
	} {
		if bad.MatchString(s) {
			t.Errorf("privacy leak %v in %s", bad, s)
		}
	}
}

// With nothing to read (no /sys, no /proc) every field is null: unknown, never false or empty.
func TestProfileMissingFilesStayUnknown(t *testing.T) {
	p := NewFixture(t.TempDir(), "amd64").Capabilities(context.Background())
	b, _ := json.Marshal(p)
	want := `{"schema":"onemind.node.capabilities/v1","data_disk":{"kind":null,"ssd":null},` +
		`"memory":{"total_mb":null,"unified":null},"accelerators":null,"usb":null,"tty_ports":null,` +
		`"radios":null,"cameras":null,"power":{"source":null,"battery_pct":null,"undervoltage":null},` +
		`"thermal":{"max_c":null,"state":null}}`
	if string(b) != want {
		t.Fatalf("empty root:\n got %s\nwant %s", b, want)
	}
}

// Each field on its own: the file that feeds it present, then absent or unreadable.
func TestProfileFieldsOneByOne(t *testing.T) {
	ctx := context.Background()
	write := func(t *testing.T, root string, files map[string]string) *Collector {
		t.Helper()
		for rel, body := range files {
			p := filepath.Join(root, rel)
			if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		return NewFixture(root, "amd64")
	}

	t.Run("data_disk", func(t *testing.T) {
		cases := []struct {
			files map[string]string
			kind  string
			ssd   *bool
		}{
			{map[string]string{"proc/self/mountinfo": "1 0 8:1 / / rw - ext4 /dev/sda1 rw", "sys/block/sda/dev": "8:0",
				"sys/block/sda/queue/rotational": "1", "sys/block/sda/sda1/dev": "8:1", "sys/block/sda/sda1/partition": "1"}, "hdd", ptr(false)},
			{map[string]string{"proc/self/mountinfo": "1 0 179:2 / / rw - ext4 /dev/root rw", "sys/block/mmcblk0/dev": "179:0",
				"sys/block/mmcblk0/device/type": "MMC", "sys/block/mmcblk0/mmcblk0p2/dev": "179:2",
				"sys/block/mmcblk0/mmcblk0p2/partition": "2"}, "emmc", ptr(false)},
			{map[string]string{"proc/self/mountinfo": "1 0 252:1 / / rw - ext4 /dev/vda1 rw", "sys/block/vda/dev": "252:0",
				"sys/block/vda/vda1/dev": "252:1", "sys/block/vda/vda1/partition": "1"}, "virtual", nil},
			// The mount is there but /sys/block does not know the device (an overlay root): unknown.
			{map[string]string{"proc/self/mountinfo": "1 0 0:25 / / rw - overlay overlay rw"}, "", nil},
			// The disk is there but has no rotational flag: unknown, not an SSD.
			{map[string]string{"proc/self/mountinfo": "1 0 8:1 / / rw - ext4 /dev/sda1 rw", "sys/block/sda/dev": "8:0",
				"sys/block/sda/sda1/dev": "8:1", "sys/block/sda/sda1/partition": "1"}, "", nil},
		}
		for i, tc := range cases {
			d := write(t, t.TempDir(), tc.files).dataDisk()
			if deref(d.Kind) != tc.kind || !sameBool(d.SSD, tc.ssd) {
				t.Errorf("case %d: data_disk = %v/%v, want %q/%v", i, deref(d.Kind), d.SSD, tc.kind, tc.ssd)
			}
		}
	})

	t.Run("accelerators", func(t *testing.T) {
		// A PCI tree with no accelerator in it is a known empty list.
		c := write(t, t.TempDir(), map[string]string{"sys/bus/pci/devices/x/uevent": "PCI_CLASS=20000\nPCI_ID=10EC:8125"})
		if a := c.accelerators(ctx, heartbeat.BoardX86EFI, heartbeat.GPU{}); a == nil || len(a) != 0 {
			t.Fatalf("no accelerators = %#v", a)
		}
		// A Hailo seen only as /dev/hailo0 (no PCI tree) is still reported; VRAM and driver stay unknown.
		c = write(t, t.TempDir(), map[string]string{"dev/hailo0": ""})
		a := c.accelerators(ctx, heartbeat.BoardRPi5, heartbeat.GPU{})
		if len(a) != 1 || a[0].Vendor != heartbeat.VendorHailo || a[0].Class != heartbeat.AccelNPU || a[0].Driver != nil || a[0].VRAMMB != nil {
			t.Fatalf("hailo by device node = %#v", a)
		}
		// The Jetson GPU is integrated and makes memory unified.
		jet := fixture(t, "jetson", "arm64").Capabilities(ctx)
		if len(jet.Accelerators) != 1 || jet.Accelerators[0].Integrated == nil || !*jet.Accelerators[0].Integrated ||
			jet.Memory.Unified == nil || !*jet.Memory.Unified {
			t.Fatalf("jetson = %#v / %#v", jet.Accelerators, jet.Memory)
		}
		// Without nvidia-smi the RTX card's VRAM and compute capability are unknown, not zero.
		rtx := fixture(t, "x86efi", "amd64").Capabilities(ctx)
		for _, g := range rtx.Accelerators {
			if g.Vendor == heartbeat.VendorNVIDIA && (g.VRAMMB != nil || g.ComputeCapability != nil) {
				t.Fatalf("rtx without nvidia-smi = %#v", g)
			}
		}
	})

	t.Run("usb_tty_radios_cameras", func(t *testing.T) {
		c := write(t, t.TempDir(), map[string]string{
			"sys/bus/usb/devices/usb1/idVendor": "1d6b", "sys/bus/usb/devices/usb1/idProduct": "0002",
			"sys/class/tty/ttyS3/type": "0", "sys/class/tty/ttyS3/device/uevent": "",
			"sys/class/net/eth0/uevent": "INTERFACE=eth0",
		})
		if u := c.usbDevices(); u == nil || len(u) != 0 {
			t.Errorf("only a root hub: usb = %#v, want []", u)
		}
		if p := c.ttyPorts(); p == nil || len(p) != 0 {
			t.Errorf("a ttyS with no UART: tty_ports = %#v, want []", p)
		}
		if r := c.radios(); r == nil || len(r) != 0 {
			t.Errorf("wired only: radios = %#v, want []", r)
		}
		if cams := c.cameras(); cams == nil || len(cams) != 0 {
			t.Errorf("no camera: cameras = %#v, want []", cams)
		}
	})

	t.Run("power", func(t *testing.T) {
		c := write(t, t.TempDir(), map[string]string{
			"sys/class/power_supply/BAT0/type": "Battery", "sys/class/power_supply/BAT0/capacity": "57",
			"sys/class/power_supply/BAT0/status": "Discharging", "sys/class/power_supply/AC/type": "Mains",
			"sys/class/power_supply/AC/online": "0",
		})
		p := c.power()
		if deref(p.Source) != heartbeat.PowerBattery || p.BatteryPct == nil || *p.BatteryPct != 57 || p.Undervoltage != nil {
			t.Fatalf("on battery = %#v", p)
		}
		// A battery that is charging with no supply saying so: the source is unknown.
		c = write(t, t.TempDir(), map[string]string{"sys/class/power_supply/BAT0/type": "Battery",
			"sys/class/power_supply/BAT0/status": "Charging"})
		if p := c.power(); p.Source != nil || p.BatteryPct != nil {
			t.Fatalf("charging, no capacity = %#v", p)
		}
	})

	t.Run("thermal", func(t *testing.T) {
		// A temperature with no trip points: the hottest reading is known, the state is not.
		c := write(t, t.TempDir(), map[string]string{"sys/class/thermal/thermal_zone0/temp": "70000"})
		if th := c.thermal(); th.MaxC == nil || *th.MaxC != 70 || th.State != nil {
			t.Fatalf("no trips = %#v", th)
		}
		c = write(t, t.TempDir(), map[string]string{"sys/class/thermal/thermal_zone0/temp": "106000",
			"sys/class/thermal/thermal_zone0/trip_point_0_type": "critical", "sys/class/thermal/thermal_zone0/trip_point_0_temp": "105000"})
		if th := c.thermal(); deref(th.State) != heartbeat.ThermalCritical {
			t.Fatalf("critical = %#v", th)
		}
	})
}

// The profile rides in the heartbeat, so the hub (and a leaf's link) carries it.
func TestHeartbeatCarriesCapabilities(t *testing.T) {
	st := fixture(t, "minipc", "amd64").Collect(context.Background())
	if st.Capabilities == nil || st.Capabilities.Schema != heartbeat.CapabilitiesSchema {
		t.Fatalf("heartbeat capabilities = %#v", st.Capabilities)
	}
	b, err := json.Marshal(st)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(b, []byte(`"capabilities":{"schema":"onemind.node.capabilities/v1"`)) {
		t.Fatalf("heartbeat JSON has no capabilities object: %s", b)
	}
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func sameBool(a, b *bool) bool { return (a == nil && b == nil) || (a != nil && b != nil && *a == *b) }
