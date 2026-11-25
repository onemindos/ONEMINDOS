// SPDX-License-Identifier: Apache-2.0

package svcregistry

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const shipped = "../../os/rootfs/layers/onemind/usr/lib/onemind/services.yaml"

func TestTheShippedRegistryKeepsTheContract(t *testing.T) {
	data, err := os.ReadFile(shipped)
	if err != nil {
		t.Fatal(err)
	}
	r, err := Parse(data)
	if err != nil {
		t.Fatalf("the image's services.yaml breaks sdk/schema/onemind.services.schema.json: %v", err)
	}
	if len(r.Services) < 30 {
		t.Fatalf("only %d entries", len(r.Services))
	}
}

const good = `schema: onemind.io/services/v1
services:
  - {unit: onemind-gateway.service, name: Gateway, docs: docs/a.md, restartable: true, risk: medium, depends_on: [onemind-nats.service],
     description: "The front door every client talks to."}
  - {unit: onemind-nats.service, name: Message bus, docs: docs/a.md, restartable: true, risk: medium, depends_on: [],
     description: "Carries events between services."}
  - {unit: onemind-installer@.service, name: Installer menu, docs: docs/a.md, restartable: false, risk: medium, depends_on: [],
     description: "Installer USB only: the text menu."}
`

func TestParseRefusesWhatTheContractRefuses(t *testing.T) {
	if _, err := Parse([]byte(good)); err != nil {
		t.Fatal(err)
	}
	for name, doc := range map[string]string{
		"unknown field":   strings.Replace(good, "risk: medium, depends_on: []", "risk: medium, depends_on: [], extra: 1", 1),
		"bad risk":        strings.Replace(good, "risk: medium", "risk: none", 1),
		"missing docs":    strings.Replace(good, "docs: docs/a.md, ", "", 1),
		"short text":      strings.Replace(good, "Carries events between services.", "x", 1),
		"bad unit name":   strings.Replace(good, "onemind-nats.service, name", "../etc/passwd, name", 1),
		"wrong schema":    strings.Replace(good, "services/v1", "services/v9", 1),
		"listed twice":    good + "  - {unit: onemind-nats.service, name: Again, docs: docs/a.md, restartable: true, risk: low, depends_on: [], description: \"A second entry for the bus.\"}\n",
		"not yaml":        "schema: [",
		"docs off-repo":   strings.Replace(good, "docs: docs/a.md, restartable: true, risk: medium, depends_on: [onemind", "docs: https://x.invalid/a.md, restartable: true, risk: medium, depends_on: [onemind", 1),
		"too large input": good + "# " + strings.Repeat("x", MaxBytes),
	} {
		if _, err := Parse([]byte(doc)); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
}

func writeReg(t *testing.T, body string, mode os.FileMode) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "services.yaml")
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(p, mode); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestLoadRefusesAFileOthersCanWrite(t *testing.T) {
	if _, err := Load(writeReg(t, good, 0o644)); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(writeReg(t, good, 0o666)); err == nil {
		t.Fatal("a world-writable registry was used")
	}
}

// fakeSystemctl answers like systemd: list-unit-files names the OneMind units installed, show prints
// one block per unit in the order asked.
type fakeSystemctl struct {
	files string
	show  map[string]string
	asked [][]string
	err   error
}

func (f *fakeSystemctl) run(_ context.Context, args ...string) ([]byte, error) {
	f.asked = append(f.asked, args)
	if f.err != nil {
		return []byte("Failed to connect to bus\n"), f.err
	}
	if args[0] == "list-unit-files" {
		return []byte(f.files), nil
	}
	var b strings.Builder
	for _, a := range args {
		if blk, ok := f.show[a]; ok {
			b.WriteString(blk + "\n\n")
		} else if strings.Contains(a, ".") && !strings.HasPrefix(a, "--") {
			b.WriteString("Id=" + a + "\nLoadState=not-found\nActiveState=inactive\nSubState=dead\nMemoryCurrent=[not set]\n\n")
		}
	}
	return []byte(b.String()), nil
}

func TestCollectJoinsRegistryAndSystemd(t *testing.T) {
	f := &fakeSystemctl{
		files: "onemind-gateway.service enabled enabled\nonemind-nats.service enabled enabled\nonemind-mystery.service enabled enabled\n",
		show: map[string]string{
			"onemind-gateway.service": "Id=onemind-gateway.service\nLoadState=loaded\nActiveState=active\nSubState=running\nMemoryCurrent=104857600",
			"onemind-nats.service":    "Id=onemind-nats.service\nLoadState=loaded\nActiveState=failed\nSubState=failed\nMemoryCurrent=[not set]",
			"onemind-mystery.service": "Id=onemind-mystery.service\nLoadState=loaded\nActiveState=active\nSubState=running\nMemoryCurrent=4096",
		},
	}
	at := time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)
	v, err := (&Reader{Path: writeReg(t, good, 0o644), Run: f.run, Version: "0.2.0", Now: func() time.Time { return at }}).Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if v.Schema != Schema || v.Registry != RegistryOK || !v.At.Equal(at) || len(v.Services) != 4 {
		t.Fatalf("%+v", v)
	}
	by := map[string]Card{}
	for _, c := range v.Services {
		by[c.Unit] = c
	}
	gw := by["onemind-gateway.service"]
	if !gw.Known || !gw.Installed || *gw.ActiveState != "active" || *gw.MemoryBytes != 104857600 || *gw.Version != "0.2.0" || gw.Name != "Gateway" {
		t.Fatalf("gateway card %+v", gw)
	}
	if nats := by["onemind-nats.service"]; *nats.ActiveState != "failed" || nats.MemoryBytes != nil {
		t.Fatalf("nats card %+v", nats)
	}
	// A template unit is not an instance: not asked about, not installed, no version.
	if inst := by["onemind-installer@.service"]; inst.Installed || inst.LoadState != nil || inst.Version != nil || !inst.Known {
		t.Fatalf("template card %+v", inst)
	}
	// A OneMind unit the registry does not list is shown, flagged unknown, with no description to trust.
	if m := by["onemind-mystery.service"]; m.Known || m.Risk != "unknown" || m.Description != "" || m.Version != nil || !m.Installed {
		t.Fatalf("unknown card %+v", m)
	}
	for _, a := range f.asked {
		if a[0] != "show" && a[0] != "list-unit-files" {
			t.Fatalf("systemctl %v is not a read", a)
		}
	}
	if _, err := json.Marshal(v); err != nil {
		t.Fatal(err)
	}
}

func TestCollectWithoutARegistryShowsEveryUnitAsUnknown(t *testing.T) {
	f := &fakeSystemctl{files: "onemind-gateway.service enabled enabled\n", show: map[string]string{}}
	v, err := (&Reader{Path: filepath.Join(t.TempDir(), "none.yaml"), Run: f.run}).Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if v.Registry != RegistryMissing || len(v.Services) != 1 || v.Services[0].Known {
		t.Fatalf("%+v", v)
	}
	v, err = (&Reader{Path: writeReg(t, "schema: nope\n", 0o644), Run: f.run}).Collect(context.Background())
	if err != nil || v.Registry != RegistryInvalid || v.RegistryError == nil || len(v.Services) != 1 || v.Services[0].Known {
		t.Fatalf("%+v %v", v, err)
	}
}

func TestCollectFailsWhenSystemdCannotBeAsked(t *testing.T) {
	f := &fakeSystemctl{err: errors.New("exit status 1")}
	if _, err := (&Reader{Path: writeReg(t, good, 0o644), Run: f.run}).Collect(context.Background()); err == nil {
		t.Fatal("a systemd failure was reported as an empty list")
	}
}

func TestSystemctlRunsOnlyReads(t *testing.T) {
	for _, verb := range []string{"restart", "stop", "start", "enable", "mask", ""} {
		if _, err := Systemctl(context.Background(), verb, "onemind-gateway.service"); err == nil || !strings.Contains(err.Error(), "not a read") {
			t.Fatalf("systemctl %s was allowed: %v", verb, err)
		}
	}
}
