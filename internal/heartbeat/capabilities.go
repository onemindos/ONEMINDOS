// SPDX-License-Identifier: Apache-2.0

package heartbeat

// CapabilitiesSchema is the value of capabilities.schema.
const CapabilitiesSchema = "onemind.node.capabilities/v1"

// Capabilities is the machine's hardware profile (NodeCapabilities, issue #618): the one fact
// sheet that VM device grants, radio detection, edge model fit and app verdicts read, instead of
// each probing the machine again. It rides in the heartbeat (so it reaches the hub the same way
// from a hub, a worker or a leaf) and is served by GET /v1/nodes under nodes:read.
//
// The unknown rule (every field): JSON null means "could not be read here", never "no" or zero.
// A list is null when the place it is read from does not exist, and [] when it was read and holds
// nothing. Enum strings never use "unknown"; they are null instead.
//
// Privacy (contract §2): no serial number, MAC or IP address, user name or disk model. USB
// devices are named by vendor:product id and port, never by their serial string.
type Capabilities struct {
	Schema       string         `json:"schema"`
	DataDisk     DataDisk       `json:"data_disk"`
	Memory       MemoryProfile  `json:"memory"`
	Accelerators []Accelerator  `json:"accelerators"`
	USB          []USBDevice    `json:"usb"`
	TTYPorts     []TTYPort      `json:"tty_ports"`
	Radios       []Radio        `json:"radios"`
	Cameras      []Camera       `json:"cameras"`
	Power        PowerProfile   `json:"power"`
	Thermal      ThermalProfile `json:"thermal"`
}

// Disk kinds (DataDisk.Kind).
const (
	DiskNVMe    = "nvme"
	DiskSSD     = "ssd"
	DiskHDD     = "hdd"
	DiskSD      = "sd"
	DiskEMMC    = "emmc"
	DiskUSB     = "usb"
	DiskVirtual = "virtual"
)

// DataDisk is the whole disk under the node's data path. SSD is true for nvme and ssd, false for
// hdd, sd and emmc, null for usb and virtual disks (their rotational flag is not trustworthy).
type DataDisk struct {
	Kind *string `json:"kind"`
	SSD  *bool   `json:"ssd"`
}

// MemoryProfile: Unified is true when the main GPU uses system RAM (Jetson, an Intel iGPU with no
// discrete card), false when a discrete GPU has its own VRAM, null when it cannot be told.
type MemoryProfile struct {
	TotalMB *int64 `json:"total_mb"`
	Unified *bool  `json:"unified"`
}

// Accelerator classes and vendors.
const (
	AccelGPU     = "gpu"
	AccelNPU     = "npu"
	VendorNVIDIA = "nvidia"
	VendorAMD    = "amd"
	VendorIntel  = "intel"
	VendorHailo  = "hailo"
)

// Accelerator is one GPU or NPU. PCIID is the vendor:device id "vvvv:dddd" (what kind of card,
// like USBDevice.ID); PCISlot is its PCI address "dddd:bb:dd.f" (which card: the slot a VFIO
// grant binds, and what tells two identical cards apart). Both are null when it is not on PCI,
// like a Jetson GPU. Driver is the bound kernel driver; ComputeCapability is NVIDIA's
// "major.minor"; Device is the full path of the device node an app is granted (/dev/hailo0,
// /dev/accel/accel0).
//
// The naming rule for every list here: a "device" is always a full /dev path, a "..._id" (or
// "id") is always a "vvvv:pppp" string, and a "..._port" is a USB port path.
type Accelerator struct {
	Class             string  `json:"class"`
	Vendor            string  `json:"vendor"`
	Model             *string `json:"model"`
	PCIID             *string `json:"pci_id"`
	PCISlot           *string `json:"pci_slot"`
	Driver            *string `json:"driver"`
	DriverVersion     *string `json:"driver_version"`
	VRAMMB            *int64  `json:"vram_mb"`
	ComputeCapability *string `json:"compute_capability"`
	Integrated        *bool   `json:"integrated"`
	Device            *string `json:"device"`
}

// USBDevice is one USB device (root hubs left out). Port is the kernel's port path ("1-1.2"),
// stable while the device stays in the same socket; ID is "vvvv:pppp"; Class is bDeviceClass and
// InterfaceClasses the sorted bInterfaceClass values, two hex digits each.
type USBDevice struct {
	Port             string   `json:"port"`
	ID               string   `json:"id"`
	Class            *string  `json:"class"`
	InterfaceClasses []string `json:"interface_classes"`
}

// TTY port kinds.
const (
	TTYUSB  = "usb"
	TTYUART = "uart"
)

// TTYPort is one serial line (ttyUSB*, ttyACM*, ttyAMA*, ttyTHS*, a ttyS* with a real UART).
// USBID ("vvvv:pppp") and USBPort name the USB device behind it, null for an on-board UART.
type TTYPort struct {
	Name    string  `json:"name"`
	Kind    string  `json:"kind"`
	USBID   *string `json:"usb_id"`
	USBPort *string `json:"usb_port"`
}

// Radio kinds. WiFi, Bluetooth and cellular are interfaces the kernel registered; Zigbee,
// Zigbee-or-Thread and LoRa are known USB dongles (issue #732, sdk/schema/onemind.radios.json).
const (
	RadioWiFi         = "wifi"
	RadioBluetooth    = "bluetooth"
	RadioCellular     = "cellular"
	RadioZigbee       = "zigbee"
	RadioZigbeeThread = "zigbee-thread"
	RadioLoRa         = "lora"
)

// Radio is one radio. For wifi, bluetooth and cellular, Interface is the kernel's interface
// (wlan0, hci0) and Device is absent. For a known USB dongle, Interface is its serial line
// (ttyUSB0, ttyACM0) and Device the stable name udev gave it, /dev/onemind/<kind><n> (lora0):
// the only path a grant ever passes into an app. A USB serial line that is not a known dongle is
// in TTYPorts only: never a Radio, never named.
type Radio struct {
	Kind      string  `json:"kind"`
	Interface string  `json:"interface"`
	Device    *string `json:"device,omitempty"`
}

// Camera buses.
const (
	CameraUSB = "usb"
	CameraCSI = "csi"
)

// Camera is one camera: a USB video-class device (Device "/dev/video0", USBID "vvvv:pppp") or a
// CSI sensor bound by its driver (Device null, Name the sensor, e.g. "imx708").
type Camera struct {
	Bus    string  `json:"bus"`
	Device *string `json:"device"`
	Name   *string `json:"name"`
	USBID  *string `json:"usb_id"`
}

// Power sources.
const (
	PowerMains   = "mains"
	PowerBattery = "battery"
	PowerUSB     = "usb"
)

// PowerProfile: Source is what powers the machine now; BatteryPct the charge; Undervoltage the
// Raspberry Pi supply alarm. Each is null when this machine does not report it.
type PowerProfile struct {
	Source       *string `json:"source"`
	BatteryPct   *int    `json:"battery_pct"`
	Undervoltage *bool   `json:"undervoltage"`
}

// Thermal states, named after the kernel's trip point types.
const (
	ThermalNormal   = "normal"
	ThermalPassive  = "passive"
	ThermalHot      = "hot"
	ThermalCritical = "critical"
)

// ThermalProfile: MaxC is the hottest zone; State the worst trip point any zone has reached
// (passive means the kernel is slowing the machine to cool it). State is null when no zone
// publishes trip points.
type ThermalProfile struct {
	MaxC  *float64 `json:"max_c"`
	State *string  `json:"state"`
}
