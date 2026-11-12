// Package detect builds the node heartbeat (contract §2) by reading the
// machine's files and, on a live system only, by asking a few tools
// (k3s, rauc, nvidia-smi, systemd-detect-virt).
//
// Every file is read under Collector.Root. On a real node Root is "/". Tests
// point Root at a fixture tree in testdata/ (a fake Raspberry Pi 5, Jetson,
// DigitalOcean droplet, plain x86 VM...), so the same code is tested against
// many boards on one laptop.
package detect

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/version"
)

// Runner runs a command and returns its standard output.
type Runner func(ctx context.Context, name string, args ...string) ([]byte, error)

// LookPather reports where a command lives, like exec.LookPath.
type LookPather func(name string) (string, error)

// Collector gathers one heartbeat. The zero value is not useful; use New.
type Collector struct {
	Root     string     // filesystem prefix; "/" on a live system
	Arch     string     // GOARCH-style ("amd64", "arm64"); defaults to runtime.GOARCH
	Role     string     // "hub" or "node" (ONEMIND_NODE_ROLE)
	NodeID   string     // explicit id (ONEMIND_NODE_ID); empty = derive from machine-id
	Hostname string     // empty = read from Root
	DiskPath string     // path whose filesystem is measured for disk_*; default "/"
	Run      Runner     // nil = no commands are run (fixture mode)
	LookPath LookPather // nil = commands are treated as absent
	Timeout  time.Duration
	Now      func() time.Time
}

// New returns a Collector for the live system at "/" that may run tools.
func New() *Collector {
	return &Collector{
		Root:     "/",
		Arch:     runtime.GOARCH,
		Role:     "node",
		DiskPath: "/",
		Run:      execRunner,
		LookPath: exec.LookPath,
		Timeout:  5 * time.Second,
		Now:      time.Now,
	}
}

// NewFixture returns a Collector that reads only files under root and runs no
// commands. Used by tests and by `onemind node info --root DIR`.
func NewFixture(root, arch string) *Collector {
	return &Collector{Root: root, Arch: arch, Role: "node", DiskPath: "/", Timeout: 5 * time.Second, Now: time.Now}
}

func execRunner(ctx context.Context, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Env = append(os.Environ(), "LC_ALL=C")
	return cmd.Output()
}

// Collect gathers a full heartbeat. It never fails: anything it cannot
// detect gets the contract's "unknown"/zero/null value.
func (c *Collector) Collect(ctx context.Context) heartbeat.Status {
	now := time.Now
	if c.Now != nil {
		now = c.Now
	}
	arch := c.Arch
	if arch == "" {
		arch = runtime.GOARCH
	}
	role := c.Role
	if role == "" {
		role = "node"
	}
	board := c.Board()
	st := heartbeat.Status{
		Schema:       heartbeat.Schema,
		NodeID:       c.ID(),
		Hostname:     c.hostname(),
		Role:         role,
		Board:        board,
		Arch:         arch,
		OS:           c.OSRelease(),
		Kernel:       c.readTrim("proc/sys/kernel/osrelease"),
		TPM2:         c.TPM2(),
		SecureBoot:   c.SecureBoot(),
		K3s:          c.K3s(ctx),
		RAUC:         c.RAUC(ctx),
		GPU:          c.GPU(ctx, board),
		UptimeS:      c.Uptime(),
		AgentVersion: version.Version,
		ObservedAt:   now().UTC().Format(time.RFC3339),
	}
	st.CPUModel, st.CPUs = c.CPU()
	st.MemTotalMB, st.MemAvailableMB = c.Memory()
	st.DiskTotalGB, st.DiskFreeGB = c.Disk()
	return st
}

// ---- helpers ---------------------------------------------------------------

func (c *Collector) path(rel string) string {
	return filepath.Join(c.Root, strings.TrimPrefix(rel, "/"))
}

func (c *Collector) read(rel string) ([]byte, error) { return os.ReadFile(c.path(rel)) }

func (c *Collector) readTrim(rel string) string {
	b, err := c.read(rel)
	if err != nil {
		return ""
	}
	// device-tree strings end in NUL bytes.
	return strings.TrimSpace(strings.TrimRight(string(b), "\x00"))
}

func (c *Collector) exists(rel string) bool {
	_, err := os.Stat(c.path(rel))
	return err == nil
}

// live reports whether commands may be run: a Runner is set and we are
// looking at the real root, so tool output describes the same machine.
func (c *Collector) live() bool { return c.Run != nil && c.LookPath != nil }

func (c *Collector) has(cmd string) bool {
	if !c.live() {
		return false
	}
	_, err := c.LookPath(cmd)
	return err == nil
}

func (c *Collector) run(ctx context.Context, name string, args ...string) ([]byte, error) {
	if !c.live() {
		return nil, errors.New("commands disabled")
	}
	t := c.Timeout
	if t <= 0 {
		t = 5 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, t)
	defer cancel()
	return c.Run(ctx, name, args...)
}

// ---- identity ----------------------------------------------------------------

// ID returns the node id: ONEMIND_NODE_ID if set, else the first 12 hex
// characters of sha256(machine-id). The raw machine-id never leaves the box.
// If there is no machine-id (a Mac, a bare container) it hashes the hostname
// instead, so the id is still stable but says nothing about the hardware.
func (c *Collector) ID() string {
	if c.NodeID != "" {
		return c.NodeID
	}
	if mid := c.readTrim("etc/machine-id"); mid != "" {
		return HashID(mid)
	}
	if mid := c.readTrim("var/lib/dbus/machine-id"); mid != "" {
		return HashID(mid)
	}
	return HashID("hostname:" + c.hostname())
}

// HashID is sha256(s), first 12 hex characters.
func HashID(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])[:12]
}

func (c *Collector) hostname() string {
	if c.Hostname != "" {
		return c.Hostname
	}
	if c.Root == "/" || c.Root == "" {
		if h, err := os.Hostname(); err == nil {
			return h
		}
	}
	if h := c.readTrim("etc/hostname"); h != "" {
		return h
	}
	return "unknown"
}

// ---- board -------------------------------------------------------------------

// hypervisor DMI vendor/product strings (lower case substrings).
var vmMarkers = []string{
	"qemu", "kvm", "vmware", "virtualbox", "innotek", "xen", "bochs",
	"parallels", "amazon ec2", "google compute engine", "openstack",
	"hetzner", "linode", "akamai", "vultr", "apple virtualization",
	"virtual machine", "cloud hypervisor", "firecracker",
}

// Board classifies the machine (contract §2). Order matters:
//  1. Jetson: /etc/nv_tegra_release (NVIDIA L4T writes it).
//  2. Raspberry Pi 5: /proc/device-tree/model says "Raspberry Pi 5".
//  3. DigitalOcean droplet: DMI vendor "DigitalOcean" (it is also a VM, but
//     it boots BIOS-only, so it needs its own board; learning 06 §4).
//  4. Other VM: DMI vendor/product names a hypervisor, or systemd-detect-virt
//     says so (live only).
//  5. UEFI firmware (/sys/firmware/efi): x86_64-efi or arm64-efi by arch.
//  6. Otherwise unknown (BIOS-only bare metal, or a Mac dev run).
func (c *Collector) Board() string {
	if c.exists("etc/nv_tegra_release") {
		return heartbeat.BoardJetsonOrin
	}
	model := strings.ToLower(c.readTrim("proc/device-tree/model"))
	if strings.Contains(model, "raspberry pi 5") {
		return heartbeat.BoardRPi5
	}
	vendor := strings.ToLower(c.readTrim("sys/class/dmi/id/sys_vendor"))
	product := strings.ToLower(c.readTrim("sys/class/dmi/id/product_name"))
	if strings.Contains(vendor, "digitalocean") {
		return heartbeat.BoardVMDO
	}
	if c.isVM(vendor, product) {
		return heartbeat.BoardVM
	}
	if c.exists("sys/firmware/efi") {
		switch c.archOrDefault() {
		case "amd64":
			return heartbeat.BoardX86EFI
		case "arm64":
			return heartbeat.BoardARM64EFI
		}
	}
	return heartbeat.BoardUnknown
}

func (c *Collector) archOrDefault() string {
	if c.Arch != "" {
		return c.Arch
	}
	return runtime.GOARCH
}

func (c *Collector) isVM(vendor, product string) bool {
	for _, m := range vmMarkers {
		if strings.Contains(vendor, m) || strings.Contains(product, m) {
			return true
		}
	}
	if c.has("systemd-detect-virt") {
		// --vm: ignore containers; a container on bare metal is not a VM.
		out, err := c.run(context.Background(), "systemd-detect-virt", "--vm")
		v := strings.TrimSpace(string(out))
		if err == nil && v != "" && v != "none" {
			return true
		}
	}
	return false
}

// ---- OS, kernel, CPU, memory, uptime ----------------------------------------

// OSRelease parses /etc/os-release (or /usr/lib/os-release).
func (c *Collector) OSRelease() heartbeat.OS {
	b, err := c.read("etc/os-release")
	if err != nil {
		b, err = c.read("usr/lib/os-release")
		if err != nil {
			return heartbeat.OS{}
		}
	}
	kv := parseKV(b, "=")
	return heartbeat.OS{ID: kv["ID"], VersionID: kv["VERSION_ID"], Pretty: kv["PRETTY_NAME"]}
}

func parseKV(b []byte, sep string) map[string]string {
	out := map[string]string{}
	sc := bufio.NewScanner(bytes.NewReader(b))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, sep)
		if !ok {
			continue
		}
		v = strings.TrimSpace(v)
		if uq, err := strconv.Unquote(v); err == nil {
			v = uq
		} else {
			v = strings.Trim(v, `"'`)
		}
		out[strings.TrimSpace(k)] = v
	}
	return out
}

// CPU returns the CPU model and the number of logical CPUs from /proc/cpuinfo.
// On ARM boards cpuinfo often has no "model name"; then the device-tree model
// is used (e.g. "Raspberry Pi 5 Model B Rev 1.0"; it has no serial).
func (c *Collector) CPU() (string, int) {
	b, err := c.read("proc/cpuinfo")
	if err != nil {
		if c.Root == "/" {
			return "", runtime.NumCPU()
		}
		return "", 0
	}
	model, n := "", 0
	sc := bufio.NewScanner(bytes.NewReader(b))
	for sc.Scan() {
		k, v, ok := strings.Cut(sc.Text(), ":")
		if !ok {
			continue
		}
		k, v = strings.TrimSpace(k), strings.TrimSpace(v)
		switch k {
		case "processor":
			n++
		case "model name":
			if model == "" {
				model = v
			}
		case "Model", "Hardware":
			if model == "" {
				model = v
			}
		}
	}
	if model == "" {
		model = c.readTrim("proc/device-tree/model")
	}
	return model, n
}

// Memory returns MemTotal and MemAvailable in MiB from /proc/meminfo.
func (c *Collector) Memory() (int64, int64) {
	b, err := c.read("proc/meminfo")
	if err != nil {
		return 0, 0
	}
	kv := parseKV(b, ":")
	kb := func(k string) int64 {
		f := strings.Fields(kv[k])
		if len(f) == 0 {
			return 0
		}
		n, _ := strconv.ParseInt(f[0], 10, 64)
		return n / 1024
	}
	return kb("MemTotal"), kb("MemAvailable")
}

// Uptime returns whole seconds since boot from /proc/uptime.
func (c *Collector) Uptime() int64 {
	f := strings.Fields(c.readTrim("proc/uptime"))
	if len(f) == 0 {
		return 0
	}
	v, err := strconv.ParseFloat(f[0], 64)
	if err != nil {
		return 0
	}
	return int64(v)
}

// BootID returns this boot's random id (/proc/sys/kernel/random/boot_id).
// Gate G6 (brief 30 §7) checks that the local API reports it.
func (c *Collector) BootID() string { return c.readTrim("proc/sys/kernel/random/boot_id") }

// Disk returns total and free GB (10^9 bytes) of the filesystem holding DiskPath.
func (c *Collector) Disk() (float64, float64) {
	p := c.DiskPath
	if p == "" {
		p = "/"
	}
	total, free, err := statfs(c.path(p))
	if err != nil {
		return 0, 0
	}
	return round1(float64(total) / 1e9), round1(float64(free) / 1e9)
}

func round1(f float64) float64 { return float64(int64(f*10+0.5)) / 10 }

// ---- trust: TPM and Secure Boot ------------------------------------------------

// TPM2 reports a TPM 2.0 chip: /sys/class/tpm/tpm0 with tpm_version_major = 2
// (kernel 5.6+), or the TPM2-only resource manager /dev/tpmrm0.
func (c *Collector) TPM2() bool {
	if c.readTrim("sys/class/tpm/tpm0/tpm_version_major") == "2" {
		return true
	}
	return c.exists("sys/class/tpm/tpmrm0") || c.exists("dev/tpmrm0")
}

// secureBootVar is the EFI global variable SecureBoot (UEFI spec, vendor
// GUID 8be4df61-93ca-11d2-aa0d-00e098032b8c). efivarfs files start with 4
// bytes of attributes, then the 1-byte value.
const secureBootVar = "sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"

// SecureBoot returns enabled/disabled from efivars, unsupported on non-UEFI
// firmware, or unknown when UEFI is present but the variable is unreadable.
func (c *Collector) SecureBoot() string {
	if !c.exists("sys/firmware/efi") {
		return heartbeat.SecureBootUnsupported
	}
	b, err := c.read(secureBootVar)
	if err != nil || len(b) < 5 {
		return heartbeat.SecureBootUnknown
	}
	if b[4] == 1 {
		return heartbeat.SecureBootEnabled
	}
	return heartbeat.SecureBootDisabled
}
