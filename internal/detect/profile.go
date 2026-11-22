// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"bufio"
	"bytes"
	"context"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// The hardware profile (NodeCapabilities, #618; heartbeat/capabilities.go). Everything is read
// from /sys and /proc under Collector.Root; the only tool is nvidia-smi on a live system, for
// the VRAM and compute capability NVIDIA does not put in sysfs. No new daemon, no new package.
// Whatever cannot be read stays null: a missing file is "unknown", never "no".

// maxListed bounds each list so a hub full of USB hubs cannot push the heartbeat past the
// gateway's 64 KiB limit.
const maxListed = 64

// Capabilities collects the hardware profile on its own (CLI and tests).
func (c *Collector) Capabilities(ctx context.Context) *heartbeat.Capabilities {
	mem, _ := c.Memory()
	board := c.Board()
	return c.capabilities(ctx, board, mem, c.GPU(ctx, board))
}

func (c *Collector) capabilities(ctx context.Context, board string, memMB int64, gpu heartbeat.GPU) *heartbeat.Capabilities {
	accel := c.accelerators(ctx, board, gpu)
	p := &heartbeat.Capabilities{
		Schema:       heartbeat.CapabilitiesSchema,
		DataDisk:     c.dataDisk(),
		Memory:       heartbeat.MemoryProfile{Unified: unifiedMemory(board, accel)},
		Accelerators: accel,
		USB:          c.usbDevices(),
		TTYPorts:     c.ttyPorts(),
		Radios:       c.radios(),
		Cameras:      c.cameras(),
		Power:        c.power(),
		Thermal:      c.thermal(),
	}
	if memMB > 0 {
		p.Memory.TotalMB = &memMB
	}
	return p
}

func ptr[T any](v T) *T { return &v }

func strPtr(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// names lists a directory under Root (sorted); ok is false when it does not exist.
func (c *Collector) names(rel string) ([]string, bool) {
	ents, err := os.ReadDir(c.path(rel))
	if err != nil {
		return nil, false
	}
	out := make([]string, 0, len(ents))
	for _, e := range ents {
		out = append(out, e.Name())
	}
	sort.Strings(out)
	return out, true
}

func readAbs(p string) string {
	b, err := os.ReadFile(p)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

// usbParent follows a sysfs "device" link up to the USB device that owns it and returns its port
// path ("1-1.2") and "vvvv:pppp". It never leaves Root.
func (c *Collector) usbParent(rel string) (port, id string) {
	root, err := filepath.EvalSymlinks(c.path(""))
	if err != nil {
		return "", ""
	}
	p, err := filepath.EvalSymlinks(c.path(rel))
	if err != nil {
		return "", ""
	}
	inside := func(p string) bool {
		return p != root && (root == string(filepath.Separator) || strings.HasPrefix(p, root+string(filepath.Separator)))
	}
	for i := 0; i < 5 && inside(p); i++ {
		if v := readAbs(filepath.Join(p, "idVendor")); v != "" {
			if pid := readAbs(filepath.Join(p, "idProduct")); pid != "" {
				return filepath.Base(p), strings.ToLower(v + ":" + pid)
			}
		}
		p = filepath.Dir(p)
	}
	return "", ""
}

// ---- data disk -------------------------------------------------------------------

// dataDisk finds the whole disk under DiskPath: the mount from /proc/self/mountinfo, its
// major:minor in /sys/block (through a device-mapper slave), then the disk's kind.
func (c *Collector) dataDisk() heartbeat.DataDisk {
	disk := c.diskFor(c.mountDev(), 0)
	kind := c.diskKind(disk)
	d := heartbeat.DataDisk{Kind: strPtr(kind)}
	switch kind {
	case heartbeat.DiskNVMe, heartbeat.DiskSSD:
		d.SSD = ptr(true)
	case heartbeat.DiskHDD, heartbeat.DiskSD, heartbeat.DiskEMMC:
		d.SSD = ptr(false)
	}
	return d
}

func (c *Collector) mountDev() string {
	want := c.DiskPath
	if want == "" {
		want = "/"
	}
	b, err := c.read("proc/self/mountinfo")
	if err != nil {
		return ""
	}
	best, dev := -1, ""
	sc := bufio.NewScanner(bytes.NewReader(b))
	for sc.Scan() {
		f := strings.Fields(sc.Text())
		if len(f) < 5 {
			continue
		}
		mp := f[4]
		if (want == mp || mp == "/" || strings.HasPrefix(want, mp+"/")) && len(mp) > best {
			best, dev = len(mp), f[2]
		}
	}
	return dev
}

// diskFor returns the /sys/block name of the disk holding major:minor (or a block device name
// when depth > 0, for a device-mapper slave).
func (c *Collector) diskFor(dev string, depth int) string {
	if dev == "" || depth > 3 {
		return ""
	}
	disks, _ := c.names("sys/block")
	for _, d := range disks {
		parts, _ := c.names("sys/block/" + d)
		for _, sub := range append([]string{""}, parts...) {
			rel := filepath.Join("sys/block", d, sub)
			if sub != "" && !c.exists(filepath.Join(rel, "partition")) {
				continue
			}
			if c.readTrim(filepath.Join(rel, "dev")) != dev && (depth == 0 || filepath.Base(rel) != dev) {
				continue
			}
			if strings.HasPrefix(d, "dm-") {
				slaves, _ := c.names("sys/block/" + d + "/slaves")
				if len(slaves) == 0 {
					return ""
				}
				return c.diskFor(slaves[0], depth+1)
			}
			return d
		}
	}
	return ""
}

func (c *Collector) diskKind(d string) string {
	rel := "sys/block/" + d
	switch {
	case d == "":
		return ""
	case strings.HasPrefix(d, "nvme"):
		return heartbeat.DiskNVMe
	case strings.HasPrefix(d, "mmcblk"):
		switch c.readTrim(rel + "/device/type") {
		case "SD":
			return heartbeat.DiskSD
		case "MMC":
			return heartbeat.DiskEMMC
		}
		return ""
	case strings.HasPrefix(d, "vd") || strings.HasPrefix(d, "xvd"):
		return heartbeat.DiskVirtual
	}
	if real, err := filepath.EvalSymlinks(c.path(rel)); err == nil && strings.Contains(real, "/usb") {
		return heartbeat.DiskUSB
	}
	switch strings.ToLower(c.readTrim(rel + "/device/vendor")) {
	case "qemu", "vmware", "vmware,", "msft", "vbox", "virtio":
		return heartbeat.DiskVirtual
	}
	switch c.readTrim(rel + "/queue/rotational") {
	case "0":
		return heartbeat.DiskSSD
	case "1":
		return heartbeat.DiskHDD
	}
	return ""
}

// ---- accelerators ------------------------------------------------------------------

// accelerators lists GPUs and NPUs from each PCI device's uevent (PCI_ID, PCI_CLASS, DRIVER,
// PCI_SLOT_NAME), plus the Jetson's integrated GPU and a Hailo seen only as /dev/hailo0.
// It is null when there is no /sys/bus/pci and nothing else answered.
func (c *Collector) accelerators(ctx context.Context, board string, gpu heartbeat.GPU) []heartbeat.Accelerator {
	devs, pciOK := c.names("sys/bus/pci/devices")
	var out []heartbeat.Accelerator
	if pciOK {
		out = []heartbeat.Accelerator{}
	}
	smi := c.nvidiaSMI(ctx)
	hailo, npu := 0, 0
	for _, name := range devs {
		rel := "sys/bus/pci/devices/" + name
		b, err := c.read(rel + "/uevent")
		if err != nil {
			continue
		}
		kv := parseKV(b, "=")
		id := strings.ToLower(kv["PCI_ID"])
		vendor, _, _ := strings.Cut(id, ":")
		cls, _ := strconv.ParseUint(kv["PCI_CLASS"], 16, 32)
		slot := strings.ToLower(kv["PCI_SLOT_NAME"])
		var a heartbeat.Accelerator
		switch {
		case vendor == "1e60": // Hailo Technologies
			a = heartbeat.Accelerator{Class: heartbeat.AccelNPU, Vendor: heartbeat.VendorHailo}
			if dev := "dev/hailo" + strconv.Itoa(hailo); c.exists(dev) {
				a.Device = ptr("/" + dev)
			}
			hailo++
		case vendor == "8086" && cls>>16 == 0x12: // Intel NPU: a processing accelerator
			a = heartbeat.Accelerator{Class: heartbeat.AccelNPU, Vendor: heartbeat.VendorIntel}
			if dev := "dev/accel/accel" + strconv.Itoa(npu); c.exists(dev) {
				a.Device = ptr("/" + dev)
			}
			npu++
		case cls>>16 == 0x03 && vendor == "10de":
			a = heartbeat.Accelerator{Class: heartbeat.AccelGPU, Vendor: heartbeat.VendorNVIDIA, Integrated: ptr(false)}
			a.Model = strPtr(c.nvidiaModel(slot))
			if s, ok := smi[slotKey(slot)]; ok {
				a.VRAMMB, a.ComputeCapability = s.vram, s.cc
			}
		case cls>>16 == 0x03 && vendor == "1002":
			a = heartbeat.Accelerator{Class: heartbeat.AccelGPU, Vendor: heartbeat.VendorAMD}
			if n, err := strconv.ParseInt(c.readTrim(rel+"/mem_info_vram_total"), 10, 64); err == nil && n > 0 {
				a.VRAMMB = ptr(n >> 20)
			}
		case cls>>16 == 0x03 && vendor == "8086":
			// Intel's integrated GPU always sits at 00:02.0; an Arc card is elsewhere.
			a = heartbeat.Accelerator{Class: heartbeat.AccelGPU, Vendor: heartbeat.VendorIntel,
				Integrated: ptr(strings.HasSuffix(slot, "00:02.0"))}
		default:
			continue
		}
		if pciIDRe.MatchString(id) {
			a.PCIID = &id
		}
		if pciSlotRe.MatchString(slot) {
			a.PCISlot = &slot
		}
		if drv := kv["DRIVER"]; drv != "" {
			a.Driver = &drv
			a.DriverVersion = strPtr(c.readTrim("sys/bus/pci/drivers/" + drv + "/module/version"))
		}
		out = append(out, a)
	}
	if hailo == 0 && c.exists("dev/hailo0") {
		out = append(out, heartbeat.Accelerator{Class: heartbeat.AccelNPU, Vendor: heartbeat.VendorHailo, Device: ptr("/dev/hailo0")})
	}
	if board == heartbeat.BoardJetsonOrin {
		// The Jetson GPU is not on PCI (nvgpu driver) and shares system memory.
		out = append(out, heartbeat.Accelerator{Class: heartbeat.AccelGPU, Vendor: heartbeat.VendorNVIDIA,
			Model: gpu.Model, Driver: ptr("nvgpu"), DriverVersion: strPtr(c.readTrim("sys/module/nvgpu/version")),
			Integrated: ptr(true)})
	}
	if len(out) > maxListed {
		out = out[:maxListed]
	}
	return out
}

// slotKey normalises a PCI address for matching: nvidia-smi prints "00000000:01:00.0", sysfs
// "0000:01:00.0", and the fixtures write ':' as '-'.
func slotKey(s string) string {
	s = strings.ToLower(strings.ReplaceAll(s, "-", ":"))
	if len(s) > 12 {
		s = s[len(s)-12:]
	}
	return s
}

func (c *Collector) nvidiaModel(slot string) string {
	matches, _ := filepath.Glob(c.path("proc/driver/nvidia/gpus/*/information"))
	for _, p := range matches {
		if slotKey(filepath.Base(filepath.Dir(p))) == slotKey(slot) {
			b, err := readFile(p)
			if err == nil {
				return parseKV(b, ":")["Model"]
			}
		}
	}
	return ""
}

type smiGPU struct {
	vram *int64
	cc   *string
}

// nvidiaSMI reads VRAM and compute capability per card (live only; nvidia-smi 510+ knows
// compute_cap). A missing or failing nvidia-smi leaves both unknown.
func (c *Collector) nvidiaSMI(ctx context.Context) map[string]smiGPU {
	out := map[string]smiGPU{}
	if !c.has("nvidia-smi") {
		return out
	}
	b, err := c.run(ctx, "nvidia-smi", "--query-gpu=pci.bus_id,memory.total,compute_cap", "--format=csv,noheader,nounits")
	if err != nil {
		return out
	}
	for _, line := range strings.Split(string(b), "\n") {
		f := strings.Split(line, ",")
		if len(f) != 3 {
			continue
		}
		var g smiGPU
		if n, err := strconv.ParseInt(strings.TrimSpace(f[1]), 10, 64); err == nil && n > 0 {
			g.vram = &n
		}
		if cc := strings.TrimSpace(f[2]); ccRe.MatchString(cc) {
			g.cc = &cc
		}
		out[slotKey(strings.TrimSpace(f[0]))] = g
	}
	return out
}

func unifiedMemory(board string, accel []heartbeat.Accelerator) *bool {
	if board == heartbeat.BoardJetsonOrin {
		return ptr(true)
	}
	integrated := false
	for _, a := range accel {
		if a.Class != heartbeat.AccelGPU || a.Integrated == nil {
			continue
		}
		if !*a.Integrated {
			return ptr(false)
		}
		integrated = true
	}
	if integrated {
		return ptr(true)
	}
	return nil
}

// ---- USB, serial lines, radios, cameras ------------------------------------------------

func (c *Collector) usbDevices() []heartbeat.USBDevice {
	names, ok := c.names("sys/bus/usb/devices")
	if !ok {
		return nil
	}
	out := []heartbeat.USBDevice{}
	for _, n := range names {
		rel := "sys/bus/usb/devices/" + n
		vid, pid := c.readTrim(rel+"/idVendor"), c.readTrim(rel+"/idProduct")
		if vid == "" || pid == "" || vid == "1d6b" { // an interface, or a Linux root hub
			continue
		}
		d := heartbeat.USBDevice{Port: n, ID: strings.ToLower(vid + ":" + pid),
			Class: strPtr(strings.ToLower(c.readTrim(rel + "/bDeviceClass"))), InterfaceClasses: []string{}}
		seen := map[string]bool{}
		matches, _ := filepath.Glob(filepath.Join(c.path(rel), "*", "bInterfaceClass"))
		for _, m := range matches {
			if v := strings.ToLower(readAbs(m)); v != "" && !seen[v] {
				seen[v] = true
				d.InterfaceClasses = append(d.InterfaceClasses, v)
			}
		}
		sort.Strings(d.InterfaceClasses)
		if out = append(out, d); len(out) == maxListed {
			break
		}
	}
	return out
}

var (
	ttyRe   = regexp.MustCompile(`^tty(USB|ACM|AMA|THS|S)[0-9]+$`)
	hciRe   = regexp.MustCompile(`^hci[0-9]+$`)
	videoRe = regexp.MustCompile(`^video[0-9]+$`)
	ccRe    = regexp.MustCompile(`^[0-9]+\.[0-9]+$`)
	// A PCI vendor:device id and a PCI address (domain:bus:device.function), as sysfs writes them.
	pciIDRe   = regexp.MustCompile(`^[0-9a-f]{4}:[0-9a-f]{4}$`)
	pciSlotRe = regexp.MustCompile(`^[0-9a-f]{4,8}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$`)
)

func (c *Collector) ttyPorts() []heartbeat.TTYPort {
	names, ok := c.names("sys/class/tty")
	if !ok {
		return nil
	}
	out := []heartbeat.TTYPort{}
	for _, n := range names {
		m := ttyRe.FindStringSubmatch(n)
		rel := "sys/class/tty/" + n
		if m == nil || !c.exists(rel+"/device") {
			continue
		}
		if t := c.readTrim(rel + "/type"); m[1] == "S" && (t == "" || t == "0") {
			continue // the kernel makes ttyS0-31 whether or not a UART is there
		}
		p := heartbeat.TTYPort{Name: n, Kind: heartbeat.TTYUART}
		if m[1] == "USB" || m[1] == "ACM" {
			p.Kind = heartbeat.TTYUSB
			port, id := c.usbParent(rel + "/device")
			p.USBID, p.USBPort = strPtr(id), strPtr(port)
		}
		if out = append(out, p); len(out) == maxListed {
			break
		}
	}
	return out
}

func (c *Collector) radios() []heartbeat.Radio {
	nets, netOK := c.names("sys/class/net")
	bts, btOK := c.names("sys/class/bluetooth")
	if !netOK && !btOK {
		return nil
	}
	out := []heartbeat.Radio{}
	for _, n := range nets {
		b, _ := c.read("sys/class/net/" + n + "/uevent")
		switch parseKV(b, "=")["DEVTYPE"] {
		case "wlan":
			out = append(out, heartbeat.Radio{Kind: heartbeat.RadioWiFi, Interface: n})
		case "wwan":
			out = append(out, heartbeat.Radio{Kind: heartbeat.RadioCellular, Interface: n})
		}
	}
	for _, n := range bts {
		if hciRe.MatchString(n) {
			out = append(out, heartbeat.Radio{Kind: heartbeat.RadioBluetooth, Interface: n})
		}
	}
	return out
}

// csiSensors are the kernel drivers of the Raspberry Pi camera modules (v1 ov5647, v2 imx219,
// HQ imx477, v3 imx708, global shutter imx296, AI camera imx500).
var csiSensors = []string{"imx219", "imx296", "imx477", "imx500", "imx708", "ov5647"}

var i2cDevRe = regexp.MustCompile(`^[0-9]+-[0-9a-f]{4}$`)

// cameras lists USB video-class cameras (interface class 0e, the first video node of each) and
// CSI sensors bound on I2C. It is null when the machine has no sysfs bus tree to look in.
func (c *Collector) cameras() []heartbeat.Camera {
	if !c.exists("sys/bus") {
		return nil
	}
	out := []heartbeat.Camera{}
	nodes, _ := c.names("sys/class/video4linux")
	for _, n := range nodes {
		rel := "sys/class/video4linux/" + n
		if idx := c.readTrim(rel + "/index"); idx != "" && idx != "0" {
			continue // UVC's second node carries metadata, not pictures
		}
		if strings.ToLower(c.readTrim(rel+"/device/bInterfaceClass")) != "0e" {
			continue
		}
		_, id := c.usbParent(rel + "/device")
		cam := heartbeat.Camera{Bus: heartbeat.CameraUSB, Name: strPtr(c.readTrim(rel + "/name")), USBID: strPtr(id)}
		if videoRe.MatchString(n) {
			cam.Device = ptr("/dev/" + n)
		}
		out = append(out, cam)
	}
	for _, drv := range csiSensors {
		devs, _ := c.names("sys/bus/i2c/drivers/" + drv)
		for _, d := range devs {
			if i2cDevRe.MatchString(d) {
				out = append(out, heartbeat.Camera{Bus: heartbeat.CameraCSI, Name: ptr(drv)})
			}
		}
	}
	if len(out) > maxListed {
		out = out[:maxListed]
	}
	return out
}

// ---- power and thermal -------------------------------------------------------------

func (c *Collector) power() heartbeat.PowerProfile {
	var p heartbeat.PowerProfile
	supplies, _ := c.names("sys/class/power_supply")
	mains, usb, discharging := false, false, false
	for _, s := range supplies {
		rel := "sys/class/power_supply/" + s
		online := c.readTrim(rel+"/online") == "1"
		switch c.readTrim(rel + "/type") {
		case "Mains":
			mains = mains || online
		case "USB":
			usb = usb || online
		case "Battery":
			if n, err := strconv.Atoi(c.readTrim(rel + "/capacity")); err == nil && p.BatteryPct == nil && n >= 0 && n <= 100 {
				p.BatteryPct = &n
			}
			discharging = discharging || c.readTrim(rel+"/status") == "Discharging"
		}
	}
	switch {
	case mains:
		p.Source = ptr(heartbeat.PowerMains)
	case usb:
		p.Source = ptr(heartbeat.PowerUSB)
	case discharging:
		p.Source = ptr(heartbeat.PowerBattery)
	}
	mons, _ := c.names("sys/class/hwmon")
	for _, m := range mons {
		rel := "sys/class/hwmon/" + m
		if c.readTrim(rel+"/name") != "rpi_volt" {
			continue
		}
		switch c.readTrim(rel + "/in0_lcrit_alarm") {
		case "0":
			p.Undervoltage = ptr(false)
		case "1":
			p.Undervoltage = ptr(true)
		}
	}
	return p
}

var thermalRank = map[string]int{heartbeat.ThermalPassive: 1, heartbeat.ThermalHot: 2, heartbeat.ThermalCritical: 3}

func (c *Collector) thermal() heartbeat.ThermalProfile {
	var t heartbeat.ThermalProfile
	zones, _ := c.names("sys/class/thermal")
	worst, known := 0, false
	for _, z := range zones {
		if !strings.HasPrefix(z, "thermal_zone") {
			continue
		}
		rel := "sys/class/thermal/" + z
		milli, err := strconv.ParseInt(c.readTrim(rel+"/temp"), 10, 64)
		if err != nil || milli < 1000 || milli > 150000 {
			continue
		}
		if v := round1(float64(milli) / 1000); t.MaxC == nil || v > *t.MaxC {
			t.MaxC = &v
		}
		trips, _ := filepath.Glob(c.path(rel + "/trip_point_*_type"))
		for _, tp := range trips {
			trip, err := strconv.ParseInt(readAbs(strings.TrimSuffix(tp, "_type")+"_temp"), 10, 64)
			if err != nil {
				continue
			}
			known = true
			if r := thermalRank[readAbs(tp)]; r > worst && milli >= trip {
				worst = r
			}
		}
	}
	if known {
		state := heartbeat.ThermalNormal
		for name, r := range thermalRank {
			if r == worst {
				state = name
			}
		}
		t.State = &state
	}
	return t
}
