// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"github.com/onemindos/onemindos/internal/heartbeat"
)

// cpuCounter keeps the previous /proc/stat totals so CPU use can be measured
// between two heartbeats.
type cpuCounter struct {
	mu          sync.Mutex
	idle, total uint64
	ok          bool
}

// Metrics reads live load figures for the heartbeat's optional "metrics"
// object (contract §12.10): CPU busy % since the previous call, the 1-minute
// load average and the hottest thermal zone. It returns nil when none of
// them can be read (fixtures, non-Linux hosts), so the field is omitted.
func (c *Collector) Metrics() *heartbeat.Metrics {
	m := &heartbeat.Metrics{CPUPct: c.cpuPct(), Load1: c.load1(), TempC: c.tempC()}
	if m.CPUPct == nil && m.Load1 == nil && m.TempC == nil {
		return nil
	}
	return m
}

func (c *Collector) cpuPct() *float64 {
	b, err := c.read("proc/stat")
	if err != nil {
		return nil
	}
	line, _, _ := strings.Cut(string(b), "\n")
	f := strings.Fields(line)
	if len(f) < 5 || f[0] != "cpu" {
		return nil
	}
	var vals []uint64
	for _, s := range f[1:] {
		v, err := strconv.ParseUint(s, 10, 64)
		if err != nil {
			return nil
		}
		vals = append(vals, v)
	}
	// user nice system idle iowait irq softirq steal; guest time is already in user.
	var total uint64
	for i, v := range vals {
		if i < 8 {
			total += v
		}
	}
	idle := vals[3]
	if len(vals) > 4 {
		idle += vals[4]
	}
	c.cpu.mu.Lock()
	defer c.cpu.mu.Unlock()
	prevIdle, prevTotal, had := c.cpu.idle, c.cpu.total, c.cpu.ok
	c.cpu.idle, c.cpu.total, c.cpu.ok = idle, total, true
	if !had || total <= prevTotal || idle < prevIdle {
		return nil
	}
	busy := 1 - float64(idle-prevIdle)/float64(total-prevTotal)
	if busy < 0 {
		busy = 0
	}
	v := round1(busy * 100)
	return &v
}

func (c *Collector) load1() *float64 {
	f := strings.Fields(c.readTrim("proc/loadavg"))
	if len(f) == 0 {
		return nil
	}
	v, err := strconv.ParseFloat(f[0], 64)
	if err != nil || v < 0 {
		return nil
	}
	return &v
}

// tempC is the hottest sensor in /sys/class/thermal (millidegrees Celsius).
// Readings outside 1..150 °C are treated as absent or bogus sensors.
func (c *Collector) tempC() *float64 {
	paths, _ := filepath.Glob(c.path("sys/class/thermal/thermal_zone*/temp"))
	var best *float64
	for _, p := range paths {
		rel, err := filepath.Rel(c.path(""), p)
		if err != nil {
			continue
		}
		milli, err := strconv.ParseInt(c.readTrim(rel), 10, 64)
		if err != nil || milli < 1000 || milli > 150000 {
			continue
		}
		v := round1(float64(milli) / 1000)
		if best == nil || v > *best {
			best = &v
		}
	}
	return best
}
