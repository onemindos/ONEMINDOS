// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// What an owner-approved device grant to a virtual machine reads (#690). Read from the same /sys
// tree as the rest of the hardware profile: no second detector, no new tool.
//
// /sys/kernel/iommu_groups/N/devices/<pci address> exists only when the kernel runs with an IOMMU
// (Intel VT-d or AMD-Vi switched on in the firmware). Without it nothing can be passed through
// safely, so the whole section stays absent.

var driverNameRe = regexp.MustCompile(`^[A-Za-z0-9_.-]{1,32}$`)

// maxGroupDevices bounds one group's list; a group larger than this is not a passthrough candidate.
const maxGroupDevices = 32

func (c *Collector) passthrough(accel []heartbeat.Accelerator, usb []heartbeat.USBDevice) *heartbeat.Passthrough {
	groups, ok := c.names("sys/kernel/iommu_groups")
	if !ok || len(groups) == 0 {
		return nil
	}
	want := map[string]bool{}
	for _, a := range accel {
		if a.PCISlot != nil {
			want[*a.PCISlot] = true
		}
	}
	p := &heartbeat.Passthrough{IOMMUGroups: []heartbeat.IOMMUGroup{}, USBDrivers: map[string][]string{}}
	for _, g := range groups {
		n, err := strconv.Atoi(g)
		if err != nil || n < 0 {
			continue
		}
		devs, _ := c.names("sys/kernel/iommu_groups/" + g + "/devices")
		slots, hit := []string{}, false
		for _, d := range devs {
			// Fixtures write ':' as '-'; a real PCI address never holds '-'.
			s := strings.ToLower(strings.ReplaceAll(d, "-", ":"))
			if !pciSlotRe.MatchString(s) {
				continue
			}
			slots, hit = append(slots, s), hit || want[s]
		}
		if !hit || len(slots) > maxGroupDevices {
			continue
		}
		sort.Strings(slots)
		p.IOMMUGroups = append(p.IOMMUGroups, heartbeat.IOMMUGroup{Group: n, Devices: slots})
	}
	sort.Slice(p.IOMMUGroups, func(i, j int) bool { return p.IOMMUGroups[i].Group < p.IOMMUGroups[j].Group })
	if len(p.IOMMUGroups) > maxListed {
		p.IOMMUGroups = p.IOMMUGroups[:maxListed]
	}
	for _, u := range usb {
		if drv := c.usbDrivers(u.Port); len(drv) > 0 {
			p.USBDrivers[u.Port] = drv
		}
	}
	return p
}

// usbDrivers lists the drivers bound to a USB device's interfaces (its "<if>/driver" links), not
// the generic "usb" driver every device has, and not a child device behind a hub.
func (c *Collector) usbDrivers(port string) []string {
	dir := c.path("sys/bus/usb/devices/" + port)
	links, _ := filepath.Glob(filepath.Join(dir, "*", "driver"))
	seen := map[string]bool{}
	out := []string{}
	for _, l := range links {
		if readAbs(filepath.Join(filepath.Dir(l), "idVendor")) != "" {
			continue // a device behind a hub reports for itself
		}
		to, err := os.Readlink(l)
		if err != nil {
			continue
		}
		if name := filepath.Base(to); driverNameRe.MatchString(name) && !seen[name] {
			seen[name] = true
			out = append(out, name)
		}
	}
	sort.Strings(out)
	return out
}
