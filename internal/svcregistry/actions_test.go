// SPDX-License-Identifier: Apache-2.0

package svcregistry

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"strings"
	"testing"
)

const withNever = good + `  - {unit: onemind-rescue.service, name: Rescue console, docs: docs/a.md, restartable: true, risk: high, depends_on: [],
     description: "A wrong registry edit marks the rescue console restartable."}
  - {unit: onemind-data-layout.service, name: Data folders, docs: docs/a.md, restartable: true, risk: high, depends_on: [],
     description: "A wrong registry edit marks the data layout restartable."}
`

func TestRestartOnlyForRestartableRegistryUnits(t *testing.T) {
	var restarted []string
	r := &Reader{Path: writeReg(t, withNever, 0o644), Restarter: func(_ context.Context, u string) error {
		restarted = append(restarted, u)
		return nil
	}}
	if err := r.Restart(context.Background(), "onemind-gateway.service"); err != nil {
		t.Fatal(err)
	}
	for unit, want := range map[string]error{
		"onemind-mystery.service":     ErrUnknownUnit,    // not in the registry
		"onemind-installer@.service":  ErrNotRestartable, // restartable: false (and a template)
		"onemind-rescue.service":      ErrNotRestartable, // registry says yes, the never list says no
		"onemind-data-layout.service": ErrNotRestartable,
		"onemind-gateway.service; rm": ErrUnknownUnit, // not a unit name at all
	} {
		if err := r.Restart(context.Background(), unit); !errors.Is(err, want) {
			t.Errorf("%s: got %v, want %v", unit, err, want)
		}
	}
	if len(restarted) != 1 || restarted[0] != "onemind-gateway.service" {
		t.Fatalf("restarted %v", restarted)
	}
	if err := (&Reader{Path: "/nonexistent/services.yaml"}).CheckRestart("onemind-gateway.service"); !errors.Is(err, ErrUnknownUnit) {
		t.Fatalf("no registry: nothing is restartable, got %v", err)
	}
}

func TestNeverRestartUnitsShowNoButton(t *testing.T) {
	f := &fakeSystemctl{show: map[string]string{}}
	v, err := (&Reader{Path: writeReg(t, withNever, 0o644), Run: f.run}).Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range v.Services {
		if NeverRestart(c.Unit) && c.Restartable {
			t.Errorf("%s shows a restart button", c.Unit)
		}
	}
	// The shipped registry agrees: every rescue, first-boot, host and data-layout unit is restartable: false.
	data, err := os.ReadFile(shipped)
	if err != nil {
		t.Fatal(err)
	}
	reg, err := Parse(data)
	if err != nil {
		t.Fatal(err)
	}
	seen := 0
	for _, e := range reg.Services {
		if NeverRestart(e.Unit) {
			seen++
			if e.Restartable {
				t.Errorf("services.yaml marks %s restartable", e.Unit)
			}
		}
	}
	if seen < 8 {
		t.Fatalf("only %d never-restart units in the shipped registry", seen)
	}
}

func TestLogsReadTheJournalOfRegistryUnitsOnly(t *testing.T) {
	var asked [][]string
	r := &Reader{Path: writeReg(t, good, 0o644), Journal: func(_ context.Context, args []string, w io.Writer) error {
		asked = append(asked, args)
		_, err := io.WriteString(w, "2026-11-22T10:00:00+0000 box gateway[1]: started\n")
		return err
	}}
	var out bytes.Buffer
	if err := r.Logs(context.Background(), "onemind-gateway.service", 50, true, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "started") || len(asked) != 1 {
		t.Fatalf("%q %v", out.String(), asked)
	}
	got := strings.Join(asked[0], " ")
	for _, want := range []string{"--unit=onemind-gateway.service", "--lines=50", "--follow", "--no-pager"} {
		if !strings.Contains(got, want) {
			t.Errorf("journalctl %s lacks %s", got, want)
		}
	}
	if err := r.Logs(context.Background(), "onemind-mystery.service", 50, false, &out); !errors.Is(err, ErrUnknownUnit) {
		t.Fatalf("an unlisted unit: %v", err)
	}
	if err := r.Logs(context.Background(), "onemind-gateway.service", MaxLogLines+1, false, &out); err == nil {
		t.Fatal("more than MaxLogLines was allowed")
	}
	if len(asked) != 1 {
		t.Fatalf("journalctl ran for a refused request: %v", asked)
	}
}
