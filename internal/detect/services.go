package detect

import (
	"context"
	"encoding/json"
	"path/filepath"
	"sort"
	"strings"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// ---- k3s ---------------------------------------------------------------------

// K3s reports whether k3s is installed, its role and readiness.
//   - present: the k3s binary or /etc/rancher/k3s exists.
//   - role: "server" if the server data dir or the admin kubeconfig exists,
//     otherwise "agent".
//   - ready (live only): a server runs `k3s kubectl get --raw /readyz` and
//     expects "ok"; an agent has no kubeconfig, so it uses
//     `systemctl is-active k3s-agent` (a weaker signal; see README).
func (c *Collector) K3s(ctx context.Context) heartbeat.K3s {
	present := c.exists("usr/local/bin/k3s") || c.exists("usr/bin/k3s") || c.exists("etc/rancher/k3s")
	if !present {
		return heartbeat.K3s{}
	}
	role := "agent"
	if c.exists("var/lib/rancher/k3s/server") || c.exists("etc/rancher/k3s/k3s.yaml") {
		role = "server"
	}
	out := heartbeat.K3s{Present: true, Role: &role}
	if role == "server" && c.has("k3s") {
		b, err := c.run(ctx, "k3s", "kubectl", "get", "--raw", "/readyz")
		out.Ready = err == nil && strings.TrimSpace(string(b)) == "ok"
	} else if role == "agent" && c.has("systemctl") {
		_, err := c.run(ctx, "systemctl", "is-active", "--quiet", "k3s-agent")
		out.Ready = err == nil
	}
	return out
}

// ---- RAUC ----------------------------------------------------------------------

// raucStatus is the subset of `rauc status --output-format=json` we read.
// Slots is a list of single-key objects: [{"rootfs.0": {...}}, ...].
type raucStatus struct {
	Booted string                     `json:"booted"`
	Slots  []map[string]raucSlotEntry `json:"slots"`
}

type raucSlotEntry struct {
	Class      string `json:"class"`
	Bootname   string `json:"bootname"`
	State      string `json:"state"`
	BootStatus string `json:"boot_status"`
	SlotStatus struct {
		Bundle struct {
			Version string `json:"version"`
		} `json:"bundle"`
	} `json:"slot_status"`
}

// RAUC reports A/B slots via `rauc status --output-format=json` (live only).
// The device path of each slot is dropped on purpose (it can embed a disk serial).
func (c *Collector) RAUC(ctx context.Context) heartbeat.RAUC {
	empty := heartbeat.RAUC{Slots: []heartbeat.Slot{}}
	if !c.has("rauc") {
		return empty
	}
	b, err := c.run(ctx, "rauc", "status", "--output-format=json")
	if err != nil {
		// The binary is there but the service is not answering.
		empty.Present = true
		return empty
	}
	return ParseRAUC(b)
}

// ParseRAUC turns rauc's JSON status into the heartbeat's rauc object.
func ParseRAUC(b []byte) heartbeat.RAUC {
	out := heartbeat.RAUC{Present: true, Slots: []heartbeat.Slot{}}
	var rs raucStatus
	if err := json.Unmarshal(b, &rs); err != nil {
		return out
	}
	if rs.Booted != "" {
		booted := rs.Booted
		out.BootedSlot = &booted
	}
	for _, m := range rs.Slots {
		names := make([]string, 0, len(m))
		for n := range m {
			names = append(names, n)
		}
		sort.Strings(names)
		for _, n := range names {
			e := m[n]
			out.Slots = append(out.Slots, heartbeat.Slot{
				Name: n, Class: e.Class, Bootname: e.Bootname, State: e.State,
				BootStatus: e.BootStatus, BundleVersion: e.SlotStatus.Bundle.Version,
			})
		}
	}
	return out
}

// ---- GPU -----------------------------------------------------------------------

// GPU reports an NVIDIA GPU.
//   - Discrete GPU: /proc/driver/nvidia exists; the model is read from
//     /proc/driver/nvidia/gpus/*/information ("Model:" line only; the same
//     file has a GPU UUID, which we never read out), or from nvidia-smi.
//   - Jetson: the GPU is integrated (nvgpu driver, no /proc/driver/nvidia);
//     the board model from the device tree names it.
func (c *Collector) GPU(ctx context.Context, board string) heartbeat.GPU {
	if c.exists("proc/driver/nvidia") {
		g := heartbeat.GPU{NVIDIA: true}
		if m := c.nvidiaProcModel(); m != "" {
			g.Model = &m
		} else if c.has("nvidia-smi") {
			if b, err := c.run(ctx, "nvidia-smi", "--query-gpu=name", "--format=csv,noheader"); err == nil {
				if m := firstLine(string(b)); m != "" {
					g.Model = &m
				}
			}
		}
		return g
	}
	if board == heartbeat.BoardJetsonOrin {
		g := heartbeat.GPU{NVIDIA: true}
		if m := c.readTrim("proc/device-tree/model"); m != "" {
			g.Model = &m
		}
		return g
	}
	if c.has("nvidia-smi") {
		if b, err := c.run(ctx, "nvidia-smi", "--query-gpu=name", "--format=csv,noheader"); err == nil {
			if m := firstLine(string(b)); m != "" {
				return heartbeat.GPU{NVIDIA: true, Model: &m}
			}
		}
	}
	return heartbeat.GPU{}
}

func (c *Collector) nvidiaProcModel() string {
	matches, _ := filepath.Glob(c.path("proc/driver/nvidia/gpus/*/information"))
	sort.Strings(matches)
	for _, p := range matches {
		b, err := readFile(p)
		if err != nil {
			continue
		}
		if m := parseKV(b, ":")["Model"]; m != "" {
			return m
		}
	}
	return ""
}

func firstLine(s string) string {
	l, _, _ := strings.Cut(strings.TrimSpace(s), "\n")
	return strings.TrimSpace(l)
}
