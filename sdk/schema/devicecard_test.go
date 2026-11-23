// SPDX-License-Identifier: Apache-2.0

package schema

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

func loadCard(t *testing.T, name string) map[string]any {
	t.Helper()
	data, err := os.ReadFile("examples/device-card/" + name + ".json")
	if err != nil {
		t.Fatal(err)
	}
	var v map[string]any
	if err := json.Unmarshal(data, &v); err != nil {
		t.Fatal(err)
	}
	return v
}

// applyOps runs the fixture ops (JSON Pointer set or del) shared with sdk/tools/tests/test_device_card.py.
func applyOps(t *testing.T, doc map[string]any, ops [][]any) {
	t.Helper()
	for _, op := range ops {
		parts := strings.Split(strings.TrimPrefix(op[1].(string), "/"), "/")
		var node any = doc
		for _, p := range parts[:len(parts)-1] {
			if list, ok := node.([]any); ok {
				i, _ := strconv.Atoi(p)
				node = list[i]
			} else {
				node = node.(map[string]any)[p]
			}
		}
		last := parts[len(parts)-1]
		switch n := node.(type) {
		case map[string]any:
			if op[0] == "del" {
				delete(n, last)
			} else {
				n[last] = op[2]
			}
		case []any:
			i, _ := strconv.Atoi(last)
			if op[0] == "del" {
				t.Fatalf("del on a list index is not a fixture op")
			}
			n[i] = op[2]
		}
	}
}

func cardRulesOf(err error) map[string]bool {
	got := map[string]bool{}
	var ce *CardError
	if errors.As(err, &ce) {
		for _, p := range ce.Problems {
			got[p.Rule] = true
		}
	}
	return got
}

func TestDeviceCardExamplesValidateFast(t *testing.T) {
	start := time.Now()
	for _, name := range []string{"temperature-sensor", "relay"} {
		data, err := os.ReadFile("examples/device-card/" + name + ".json")
		if err != nil {
			t.Fatal(err)
		}
		if err := ValidateDeviceCard(data); err != nil {
			t.Errorf("%s: %v", name, err)
		}
	}
	if d := time.Since(start); d > 5*time.Second {
		t.Fatalf("examples took %s", d)
	}
}

func TestDeviceCardFixturesFailWithTheirRule(t *testing.T) {
	raw, err := os.ReadFile("testdata/device-card/invalid.json")
	if err != nil {
		t.Fatal(err)
	}
	var file struct {
		Fixtures []struct {
			Name  string   `json:"name"`
			Base  string   `json:"base"`
			Rules []string `json:"rules"`
			Ops   [][]any  `json:"ops"`
		} `json:"fixtures"`
	}
	if err := json.Unmarshal(raw, &file); err != nil {
		t.Fatal(err)
	}
	seen := map[string]bool{}
	for _, fx := range file.Fixtures {
		doc := loadCard(t, fx.Base)
		applyOps(t, doc, fx.Ops)
		data, _ := json.Marshal(doc)
		got := cardRulesOf(ValidateDeviceCard(data))
		for _, r := range fx.Rules {
			seen[r] = true
			if !got[r] {
				t.Errorf("%s: want rule %s, got %v", fx.Name, r, got)
			}
		}
	}
	for r := range deviceCardRules {
		if !seen[r] {
			t.Errorf("rule %s has no failing fixture", r)
		}
	}
}

// The same checks as the Python twin's observe and URL tests (sdk/tools/tests/test_device_card.py).
func TestDeviceCardObserveOnAWritableAffordanceIsRefusedByTheSchemaAlone(t *testing.T) {
	raw, err := os.ReadFile("testdata/device-card/invalid.json")
	if err != nil {
		t.Fatal(err)
	}
	var file struct {
		Fixtures []struct {
			Name  string   `json:"name"`
			Base  string   `json:"base"`
			Rules []string `json:"rules"`
			Ops   [][]any  `json:"ops"`
		} `json:"fixtures"`
	}
	if err := json.Unmarshal(raw, &file); err != nil {
		t.Fatal(err)
	}
	sch, err := deviceCardSchema()
	if err != nil {
		t.Fatal(err)
	}
	n := 0
	for _, fx := range file.Fixtures {
		if len(fx.Rules) != 1 || fx.Rules[0] != "observe-read-only" {
			continue
		}
		n++
		doc := loadCard(t, fx.Base)
		applyOps(t, doc, fx.Ops)
		data, _ := json.Marshal(doc)
		inst, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
		if err != nil {
			t.Fatal(err)
		}
		if sch.Validate(inst) == nil {
			t.Errorf("%s: the schema alone accepts it", fx.Name)
		}
	}
	if n == 0 {
		t.Fatal("no observe-read-only fixture")
	}
}

func TestDeviceCardObserveStaysAllowedWhereNothingChanges(t *testing.T) {
	doc := loadCard(t, "relay")
	applyOps(t, doc, [][]any{{"set", "/actions/meter", map[string]any{
		"title": "Read the meter", "safe": true, "output": map[string]any{"type": "number", "unit": "W"},
		"om:safety": map[string]any{"class": "observe", "needsHold": false, "askers": []any{"owner", "automation"}},
	}}})
	data, _ := json.Marshal(doc)
	if err := ValidateDeviceCard(data); err != nil {
		t.Fatal(err)
	}
}

func TestDeviceCardHarmlessURLsAndProseAreNotCredentials(t *testing.T) {
	doc := loadCard(t, "relay")
	applyOps(t, doc, [][]any{
		{"set", "/actions/switch/forms", []any{map[string]any{"href": "https://relay.example/switch?on=1&unit=s#state"}}},
		{"set", "/description", "Is it on? It keeps no token or secret: the gateway holds those."},
	})
	data, _ := json.Marshal(doc)
	if err := ValidateDeviceCard(data); err != nil {
		t.Fatal(err)
	}
}

func TestUnquotePlusMatchesPython(t *testing.T) {
	for in, want := range map[string]string{"api%5Fkey": "api_key", "a+b": "a b", "100%": "100%", "%zz": "%zz", "%4": "%4", "%41%42": "AB"} {
		if got := unquotePlus(in); got != want {
			t.Errorf("%q: %q, want %q", in, got, want)
		}
	}
}

func TestDeviceCardProblemsNeverEchoAValue(t *testing.T) {
	doc := loadCard(t, "relay")
	applyOps(t, doc, [][]any{{"set", "/securityDefinitions/basic_sc", map[string]any{"scheme": "basic", "password": "do-not-print"}}})
	data, _ := json.Marshal(doc)
	err := ValidateDeviceCard(data)
	if err == nil || strings.Contains(err.Error(), "do-not-print") {
		t.Fatalf("%v", err)
	}
}

func TestDeviceCardClassRiskTable(t *testing.T) {
	table, err := DeviceCardClassRisk()
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]ClassRisk{
		"observe": {"read", false}, "reversible": {"write", false},
		"irreversible": {"destructive", false}, "physical": {"actuate", true},
	}
	if len(table) != len(want) {
		t.Fatalf("%v", table)
	}
	for k, v := range want {
		if table[k] != v {
			t.Errorf("%s: %v, want %v", k, table[k], v)
		}
	}
}

func TestDeviceCardRefusesBadInput(t *testing.T) {
	for in, rule := range map[string]string{"{": "json", `{"a":1} {}`: "json", strings.Repeat(" ", MaxDeviceCardBytes+1): "size"} {
		var ce *CardError
		if err := ValidateDeviceCard([]byte(in)); !errors.As(err, &ce) || ce.Problems[0].Rule != rule {
			t.Errorf("%.20q: %v", in, err)
		}
	}
}
