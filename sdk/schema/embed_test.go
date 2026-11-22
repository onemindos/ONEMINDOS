// SPDX-License-Identifier: Apache-2.0

package schema

import (
	"encoding/json"
	"strings"
	"testing"
)

// The subject tree Go embeds is the same file the gateway and the lint read (issue #600).
func TestSubjectsRegistryEmbedsEveryKind(t *testing.T) {
	var reg struct {
		Root     string                       `json:"root"`
		Kinds    map[string]json.RawMessage   `json:"kinds"`
		Reserved map[string]string            `json:"reserved_kinds"`
		Env      map[string]map[string]string `json:"envelopes"`
	}
	if err := json.Unmarshal([]byte(Subjects), &reg); err != nil {
		t.Fatalf("onemind.subjects.json: %v", err)
	}
	if reg.Root != "onemind" {
		t.Fatalf("root = %q", reg.Root)
	}
	for _, k := range []string{"node", "audit", "event", "alert", "asset", "intel", "metric", "plugin", "layer", "notification", "request"} {
		if _, ok := reg.Kinds[k]; !ok {
			t.Errorf("kind %q missing", k)
		}
	}
	if _, ok := reg.Reserved["app"]; !ok {
		t.Error("the retired onemind.app prefix must stay reserved")
	}
	for id, e := range reg.Env {
		if f := e["file"]; f != "" && !strings.HasSuffix(f, ".schema.json") {
			t.Errorf("envelope %s: file %q", id, f)
		}
	}
	for _, s := range []string{Datapoint, Event} {
		var v map[string]any
		if err := json.Unmarshal([]byte(s), &v); err != nil {
			t.Fatalf("envelope schema: %v", err)
		}
	}
}
