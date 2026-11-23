// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

// vfioBox builds a sysfs tree like an x86 PC with VT-d on (#690): an RTX card whose group holds
// only its own two functions (VGA and HDMI audio), a second card sharing its group with a USB
// controller, a keyboard (usbhid bound), a USB stick (usb-storage bound) and a dongle with no
// driver. Links are made the way the kernel makes them, so the probe reads link names only.
func vfioBox(t *testing.T, iommu bool) *Collector {
	t.Helper()
	root := t.TempDir()
	files := map[string]string{
		"sys/bus/pci/devices/0000:01:00.0/uevent": "DRIVER=nvidia\nPCI_CLASS=30000\nPCI_ID=10DE:2684\nPCI_SLOT_NAME=0000:01:00.0",
		"sys/bus/pci/devices/0000:05:00.0/uevent": "DRIVER=amdgpu\nPCI_CLASS=30000\nPCI_ID=1002:744C\nPCI_SLOT_NAME=0000:05:00.0",
		"sys/bus/usb/devices/usb1/idVendor":       "1d6b", "sys/bus/usb/devices/usb1/idProduct": "0002",
		"sys/bus/usb/devices/1-1/idVendor": "046d", "sys/bus/usb/devices/1-1/idProduct": "c31c",
		"sys/bus/usb/devices/1-1/1-1:1.0/bInterfaceClass": "03",
		"sys/bus/usb/devices/1-1/1-1:1.1/bInterfaceClass": "03",
		"sys/bus/usb/devices/1-2/idVendor":                "0781", "sys/bus/usb/devices/1-2/idProduct": "5583",
		"sys/bus/usb/devices/1-2/1-2:1.0/bInterfaceClass": "08",
		"sys/bus/usb/devices/1-3/idVendor":                "1a86", "sys/bus/usb/devices/1-3/idProduct": "55d4",
		"sys/bus/usb/devices/1-3/1-3:1.0/bInterfaceClass": "ff",
		"sys/bus/usb/drivers/usbhid/.keep":                "", "sys/bus/usb/drivers/usb-storage/.keep": "",
	}
	if iommu {
		for _, f := range []string{"1/devices/0000:01:00.0", "1/devices/0000:01:00.1", "7/devices/0000:05:00.0",
			"7/devices/0000:06:00.0", "9/devices/0000:00:14.0"} {
			files["sys/kernel/iommu_groups/"+f] = ""
		}
	}
	for rel, body := range files {
		p := filepath.Join(root, rel)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	for link, to := range map[string]string{
		"sys/bus/usb/devices/1-1/1-1:1.0/driver": "../../../drivers/usbhid",
		"sys/bus/usb/devices/1-1/1-1:1.1/driver": "../../../drivers/usbhid",
		"sys/bus/usb/devices/1-2/1-2:1.0/driver": "../../../drivers/usb-storage",
		"sys/bus/usb/devices/1-1/driver":         "../../drivers/usb", // the device-level driver every device has
	} {
		if err := os.Symlink(to, filepath.Join(root, link)); err != nil {
			t.Fatal(err)
		}
	}
	return NewFixture(root, "amd64")
}

func TestPassthroughReportsIOMMUGroupsOfAcceleratorsAndUSBDrivers(t *testing.T) {
	p := vfioBox(t, true).Capabilities(context.Background())
	if p.Passthrough == nil {
		t.Fatal("passthrough missing on a box with IOMMU groups")
	}
	b, _ := json.Marshal(p.Passthrough)
	// Group 9 (a USB controller only) holds no accelerator, so it is left out. Group 7 shows the
	// AMD card sharing with 0000:06:00.0, which a grant then refuses.
	want := `{"iommu_groups":[{"group":1,"devices":["0000:01:00.0","0000:01:00.1"]},` +
		`{"group":7,"devices":["0000:05:00.0","0000:06:00.0"]}],` +
		`"usb_drivers":{"1-1":["usbhid"],"1-2":["usb-storage"]}}`
	if string(b) != want {
		t.Fatalf("passthrough:\n got %s\nwant %s", b, want)
	}
	privacy(t, string(b))
}

// Without an IOMMU (VT-d off in the firmware, or an ARM board) nothing can be passed through, so
// the section is absent: the gateway then refuses every grant with "turn on VT-d".
func TestPassthroughAbsentWithoutIOMMU(t *testing.T) {
	p := vfioBox(t, false).Capabilities(context.Background())
	if p.Passthrough != nil {
		t.Fatalf("passthrough without IOMMU = %#v", p.Passthrough)
	}
	b, _ := json.Marshal(p)
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatal(err)
	}
	if _, ok := m["passthrough"]; ok {
		t.Fatal("passthrough key present without IOMMU")
	}
}

// A planted group entry or driver link with a name outside the kernel's shapes is dropped, never
// passed to the gateway (the hub trusts only what fits the schema).
func TestPassthroughDropsMalformedNames(t *testing.T) {
	c := vfioBox(t, true)
	for _, f := range []string{"sys/kernel/iommu_groups/1/devices/not-a-slot", "sys/kernel/iommu_groups/x/devices/0000:01:00.2"} {
		p := filepath.Join(c.Root, f)
		_ = os.MkdirAll(filepath.Dir(p), 0o755)
		_ = os.WriteFile(p, nil, 0o644)
	}
	if err := os.Symlink("../../../drivers/bad name!", filepath.Join(c.Root, "sys/bus/usb/devices/1-3/1-3:1.0/driver")); err != nil {
		t.Fatal(err)
	}
	pt := c.Capabilities(context.Background()).Passthrough
	if pt == nil || len(pt.IOMMUGroups) != 2 || !reflect.DeepEqual(pt.IOMMUGroups[0].Devices, []string{"0000:01:00.0", "0000:01:00.1"}) {
		t.Fatalf("groups = %#v", pt)
	}
	if _, ok := pt.USBDrivers["1-3"]; ok {
		t.Fatalf("malformed driver name passed through: %#v", pt.USBDrivers)
	}
}
