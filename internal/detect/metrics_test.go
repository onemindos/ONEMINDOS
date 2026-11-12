// SPDX-License-Identifier: Apache-2.0

package detect

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func write(t *testing.T, root, rel, body string) {
	t.Helper()
	p := filepath.Join(root, rel)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestMetrics(t *testing.T) {
	root := t.TempDir()
	write(t, root, "proc/stat", "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 2 3 4\n")
	write(t, root, "proc/loadavg", "0.52 0.40 0.30 1/200 1234\n")
	write(t, root, "sys/class/thermal/thermal_zone0/temp", "48500\n")
	write(t, root, "sys/class/thermal/thermal_zone1/temp", "61250\n")
	write(t, root, "sys/class/thermal/thermal_zone2/temp", "-273000\n") // broken sensor: ignored
	c := NewFixture(root, "arm64")

	m := c.Metrics()
	if m == nil || m.CPUPct != nil || *m.Load1 != 0.52 || *m.TempC != 61.3 {
		t.Fatalf("first sample: %+v", m)
	}
	// 1000 more jiffies, 250 of them idle or iowait: 75 % busy.
	write(t, root, "proc/stat", "cpu  500 0 450 900 150 0 0 0 0 0\n")
	m = c.Metrics()
	if m.CPUPct == nil || *m.CPUPct != 75 {
		t.Fatalf("cpu_pct = %v, want 75", m.CPUPct)
	}
	// A counter reset (e.g. a container restart) yields null, not a negative value.
	write(t, root, "proc/stat", "cpu  1 0 1 1 1 0 0 0\n")
	if m = c.Metrics(); m.CPUPct != nil {
		t.Fatalf("after reset cpu_pct = %v, want null", *m.CPUPct)
	}
}

func TestMetricsAbsentIsOmitted(t *testing.T) {
	c := NewFixture(t.TempDir(), "amd64")
	if c.Metrics() != nil {
		t.Fatal("no readable source must give nil")
	}
	b, _ := json.Marshal(c.Collect(context.Background()))
	var m map[string]any
	_ = json.Unmarshal(b, &m)
	if _, ok := m["metrics"]; ok {
		t.Fatal("metrics must be omitted when absent (contract §12.10)")
	}
}

func TestMetricsInHeartbeatJSON(t *testing.T) {
	root := t.TempDir()
	write(t, root, "proc/loadavg", "1.25 1 1 1/1 1\n")
	b, _ := json.Marshal(NewFixture(root, "amd64").Collect(context.Background()))
	var m struct {
		Metrics map[string]any `json:"metrics"`
	}
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatal(err)
	}
	if m.Metrics["load1"] != 1.25 || m.Metrics["cpu_pct"] != nil || m.Metrics["temp_c"] != nil {
		t.Fatalf("metrics = %v", m.Metrics)
	}
	if _, ok := m.Metrics["cpu_pct"]; !ok {
		t.Fatal("null fields must still be present")
	}
}
