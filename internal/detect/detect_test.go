package detect

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

var fixedNow = func() time.Time { return time.Date(2026, 11, 11, 22, 0, 0, 0, time.UTC) }

func fixture(t *testing.T, name, arch string) *Collector {
	t.Helper()
	c := NewFixture(filepath.Join("testdata", name), arch)
	c.Now = fixedNow
	return c
}

// fakeTools makes the listed commands "installed" and answers them from a map
// of "name arg1 arg2..." -> output. A missing key returns an error.
func fakeTools(c *Collector, answers map[string]string, installed ...string) {
	set := map[string]bool{}
	for _, n := range installed {
		set[n] = true
	}
	c.LookPath = func(n string) (string, error) {
		if set[n] {
			return "/usr/bin/" + n, nil
		}
		return "", errors.New("not found")
	}
	c.Run = func(_ context.Context, name string, args ...string) ([]byte, error) {
		key := strings.Join(append([]string{name}, args...), " ")
		if out, ok := answers[key]; ok {
			return []byte(out), nil
		}
		return nil, errors.New("exit status 1")
	}
}

func TestBoards(t *testing.T) {
	cases := []struct{ dir, arch, want string }{
		{"rpi5", "arm64", heartbeat.BoardRPi5},
		{"jetson", "arm64", heartbeat.BoardJetsonOrin},
		{"droplet", "amd64", heartbeat.BoardVMDO},
		{"x86vm", "amd64", heartbeat.BoardVM},
		{"x86efi", "amd64", heartbeat.BoardX86EFI},
		{"x86efi", "arm64", heartbeat.BoardARM64EFI}, // same tree read as an arm64 EFI box
		{"does-not-exist", "amd64", heartbeat.BoardUnknown},
	}
	for _, tc := range cases {
		t.Run(tc.dir+"/"+tc.arch, func(t *testing.T) {
			if got := fixture(t, tc.dir, tc.arch).Board(); got != tc.want {
				t.Fatalf("board = %q, want %q", got, tc.want)
			}
		})
	}
}

func TestSystemdDetectVirtLiveOnly(t *testing.T) {
	// Bare-metal-looking DMI, but systemd-detect-virt says kvm -> vm.
	c := fixture(t, "x86efi", "amd64")
	fakeTools(c, map[string]string{"systemd-detect-virt --vm": "kvm\n"}, "systemd-detect-virt")
	if got := c.Board(); got != heartbeat.BoardVM {
		t.Fatalf("board = %q, want vm", got)
	}
	fakeTools(c, map[string]string{"systemd-detect-virt --vm": "none\n"}, "systemd-detect-virt")
	if got := c.Board(); got != heartbeat.BoardX86EFI {
		t.Fatalf("board = %q, want x86_64-efi", got)
	}
}

func TestNodeID(t *testing.T) {
	c := fixture(t, "rpi5", "arm64")
	want := HashID("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01")
	if got := c.ID(); got != want {
		t.Fatalf("id = %q, want %q", got, want)
	}
	if !regexp.MustCompile(`^[0-9a-f]{12}$`).MatchString(want) {
		t.Fatalf("id %q is not 12 hex chars", want)
	}
	c.NodeID = "override0001"
	if got := c.ID(); got != "override0001" {
		t.Fatalf("override ignored: %q", got)
	}
	// No machine-id: falls back to a hostname hash, still 12 hex.
	n := NewFixture(t.TempDir(), "amd64")
	n.Hostname = "mac-dev"
	if got := n.ID(); got != HashID("hostname:mac-dev") {
		t.Fatalf("fallback id = %q", got)
	}
}

func TestRPi5Full(t *testing.T) {
	c := fixture(t, "rpi5", "arm64")
	c.Role = "node"
	s := c.Collect(context.Background())
	if s.Schema != heartbeat.Schema || s.Hostname != "pi5" || s.Arch != "arm64" || s.Role != "node" {
		t.Fatalf("identity fields wrong: %+v", s)
	}
	if s.OS.ID != "debian" || s.OS.VersionID != "13" || s.OS.Pretty != "Debian GNU/Linux 13 (trixie)" {
		t.Fatalf("os = %+v", s.OS)
	}
	if s.Kernel != "6.12.25+rpt-rpi-2712" {
		t.Fatalf("kernel = %q", s.Kernel)
	}
	if s.CPUs != 4 || s.CPUModel != "Raspberry Pi 5 Model B Rev 1.0" {
		t.Fatalf("cpu = %q x%d", s.CPUModel, s.CPUs)
	}
	if s.MemTotalMB != 8052 || s.MemAvailableMB != 7168 {
		t.Fatalf("mem = %d/%d", s.MemTotalMB, s.MemAvailableMB)
	}
	if s.UptimeS != 3600 {
		t.Fatalf("uptime = %d", s.UptimeS)
	}
	if s.TPM2 || s.SecureBoot != heartbeat.SecureBootUnsupported {
		t.Fatalf("trust = %v %q", s.TPM2, s.SecureBoot)
	}
	if !s.K3s.Present || s.K3s.Role == nil || *s.K3s.Role != "agent" || s.K3s.Ready {
		t.Fatalf("k3s = %+v", s.K3s)
	}
	if s.RAUC.Present || s.RAUC.BootedSlot != nil || s.RAUC.Slots == nil {
		t.Fatalf("rauc = %+v", s.RAUC)
	}
	if s.GPU.NVIDIA || s.GPU.Model != nil {
		t.Fatalf("gpu = %+v", s.GPU)
	}
	if s.ObservedAt != "2026-11-11T22:00:00Z" {
		t.Fatalf("observed_at = %q", s.ObservedAt)
	}
	if c.BootID() != "b0000000-0000-4000-8000-000000000001" {
		t.Fatalf("boot_id = %q", c.BootID())
	}
}

func TestJetson(t *testing.T) {
	s := fixture(t, "jetson", "arm64").Collect(context.Background())
	if s.Board != heartbeat.BoardJetsonOrin || s.OS.ID != "ubuntu" || s.CPUs != 6 {
		t.Fatalf("jetson = %+v", s)
	}
	if !s.GPU.NVIDIA || s.GPU.Model == nil || !strings.Contains(*s.GPU.Model, "Orin") {
		t.Fatalf("gpu = %+v", s.GPU)
	}
	if s.SecureBoot != heartbeat.SecureBootDisabled {
		t.Fatalf("secure_boot = %q", s.SecureBoot)
	}
	if s.K3s.Present || s.K3s.Role != nil {
		t.Fatalf("k3s = %+v", s.K3s)
	}
}

func TestDropletServerReady(t *testing.T) {
	c := fixture(t, "droplet", "amd64")
	fakeTools(c, map[string]string{"k3s kubectl get --raw /readyz": "ok"}, "k3s")
	s := c.Collect(context.Background())
	if s.Board != heartbeat.BoardVMDO || s.SecureBoot != heartbeat.SecureBootUnsupported {
		t.Fatalf("droplet = %q %q", s.Board, s.SecureBoot)
	}
	if !s.K3s.Present || *s.K3s.Role != "server" || !s.K3s.Ready {
		t.Fatalf("k3s = %+v", s.K3s)
	}
	// readyz failing -> not ready
	fakeTools(c, map[string]string{}, "k3s")
	if c.K3s(context.Background()).Ready {
		t.Fatal("ready with failing readyz")
	}
}

func TestAgentReadyViaSystemctl(t *testing.T) {
	c := fixture(t, "rpi5", "arm64")
	fakeTools(c, map[string]string{"systemctl is-active --quiet k3s-agent": ""}, "systemctl")
	if k := c.K3s(context.Background()); !k.Ready {
		t.Fatalf("k3s agent should be ready: %+v", k)
	}
}

func TestX86EFITrustGPUAndRAUC(t *testing.T) {
	c := fixture(t, "x86efi", "amd64")
	raucJSON, err := os.ReadFile("testdata/cmd/rauc-status.json")
	if err != nil {
		t.Fatal(err)
	}
	fakeTools(c, map[string]string{"rauc status --output-format=json": string(raucJSON)}, "rauc")
	s := c.Collect(context.Background())
	if !s.TPM2 || s.SecureBoot != heartbeat.SecureBootEnabled {
		t.Fatalf("trust = %v %q", s.TPM2, s.SecureBoot)
	}
	if !s.GPU.NVIDIA || s.GPU.Model == nil || *s.GPU.Model != "NVIDIA GeForce RTX 4060" {
		t.Fatalf("gpu = %+v", s.GPU)
	}
	if s.CPUModel != "Intel(R) N100" || s.CPUs != 4 {
		t.Fatalf("cpu = %q x%d", s.CPUModel, s.CPUs)
	}
	if !s.RAUC.Present || s.RAUC.BootedSlot == nil || *s.RAUC.BootedSlot != "A" || len(s.RAUC.Slots) != 2 {
		t.Fatalf("rauc = %+v", s.RAUC)
	}
	if s.RAUC.Slots[1].Name != "rootfs.0" || s.RAUC.Slots[1].State != "booted" || s.RAUC.Slots[1].BundleVersion != "0.1.0" {
		t.Fatalf("slot = %+v", s.RAUC.Slots[1])
	}
	// rauc present but service down
	fakeTools(c, map[string]string{}, "rauc")
	if r := c.RAUC(context.Background()); !r.Present || r.BootedSlot != nil || r.Slots == nil {
		t.Fatalf("rauc down = %+v", r)
	}
}

func TestSecureBootUnknownWhenVarMissing(t *testing.T) {
	if got := fixture(t, "x86vm", "amd64").SecureBoot(); got != heartbeat.SecureBootUnknown {
		t.Fatalf("secure_boot = %q", got)
	}
}

func TestNvidiaSmiFallback(t *testing.T) {
	c := fixture(t, "x86vm", "amd64")
	fakeTools(c, map[string]string{"nvidia-smi --query-gpu=name --format=csv,noheader": "NVIDIA L4\n"}, "nvidia-smi")
	g := c.GPU(context.Background(), heartbeat.BoardVM)
	if !g.NVIDIA || g.Model == nil || *g.Model != "NVIDIA L4" {
		t.Fatalf("gpu = %+v", g)
	}
}

// TestJSONShapeAndPrivacy checks every contract §2 key is present, the null
// fields serialise as null, and nothing that looks like a serial, MAC, IP or
// raw machine-id leaks into the JSON.
func TestJSONShapeAndPrivacy(t *testing.T) {
	for _, dir := range []string{"rpi5", "jetson", "droplet", "x86vm", "x86efi"} {
		t.Run(dir, func(t *testing.T) {
			c := fixture(t, dir, "amd64")
			raucJSON, _ := os.ReadFile("testdata/cmd/rauc-status.json")
			fakeTools(c, map[string]string{"rauc status --output-format=json": string(raucJSON)}, "rauc")
			b, err := json.Marshal(c.Collect(context.Background()))
			if err != nil {
				t.Fatal(err)
			}
			var m map[string]any
			if err := json.Unmarshal(b, &m); err != nil {
				t.Fatal(err)
			}
			for _, k := range []string{"schema", "node_id", "hostname", "role", "board", "arch", "os", "kernel",
				"cpu_model", "cpus", "mem_total_mb", "mem_available_mb", "disk_total_gb", "disk_free_gb",
				"tpm2", "secure_boot", "k3s", "rauc", "gpu", "uptime_s", "agent_version", "observed_at"} {
				if _, ok := m[k]; !ok {
					t.Errorf("missing key %q", k)
				}
			}
			s := string(b)
			for _, bad := range []*regexp.Regexp{
				regexp.MustCompile(`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa0`),        // raw machine-id
				regexp.MustCompile(`(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}`),       // MAC
				regexp.MustCompile(`\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`), // IPv4
				regexp.MustCompile(`(?i)serial|by-id|GPU-0000`),              // serials / GPU UUID
			} {
				if bad.MatchString(s) {
					t.Errorf("privacy leak %v in %s", bad, s)
				}
			}
		})
	}
}
