// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"testing"

	"gopkg.in/yaml.v3"
)

func eventManifest(t *testing.T, publish, subscribe, permissions []string) []byte {
	t.Helper()
	data, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	var value map[string]any
	if err := yaml.Unmarshal(data, &value); err != nil {
		t.Fatal(err)
	}
	spec := value["spec"].(map[string]any)
	spec["permissions"] = permissions
	spec["extensions"].(map[string]any)["events"] = map[string]any{"publish": publish, "subscribe": subscribe}
	data, err = yaml.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestEventManifest(t *testing.T) {
	tests := []struct {
		name                            string
		publish, subscribe, permissions []string
		valid                           bool
	}{
		{"namespaced by gateway", []string{"greeted", "backup-failed_2"}, []string{"onemind.node.*.status"}, []string{"events:subscribe:onemind.node.*.status"}, true},
		{"read grants retained", []string{"1"}, []string{"evt.app.hello.greeted"}, []string{"nodes:read", "events:subscribe:evt.app.hello.>"}, true},
		{"no subscriptions", []string{"greeted"}, []string{}, []string{}, true},
		{"full publish subject", []string{"evt.app.hello.greeted"}, []string{}, []string{}, false},
		{"command publish wildcard", []string{"cmd.>"}, []string{}, []string{}, false},
		{"publish wildcard", []string{"*"}, []string{}, []string{}, false},
		{"uppercase publish", []string{"Greeted"}, []string{}, []string{}, false},
		{"long publish", []string{"abcdefghijklmnopqrstuvwxyz0123456789abcde"}, []string{}, []string{}, false},
		{"duplicate publish", []string{"greeted", "greeted"}, []string{}, []string{}, false},
		{"missing permission", []string{}, []string{"onemind.node.*.status"}, []string{}, false},
		{"narrow permission", []string{}, []string{"onemind.node.*.status"}, []string{"events:subscribe:onemind.node.mine.status"}, false},
		{"different namespace", []string{}, []string{"onemind.node.*.status"}, []string{"events:subscribe:evt.app.hello.>"}, false},
		{"bare subscription", []string{}, []string{">"}, []string{"events:subscribe:onemind.>"}, false},
		{"bare grant", []string{}, []string{}, []string{"events:subscribe:>"}, false},
		{"invalid grant without subscription", []string{}, []string{}, []string{"events:subscribe:onemind.>.status"}, false},
		{"empty token", []string{}, []string{"onemind..status"}, []string{"events:subscribe:onemind.>"}, false},
		{"embedded wildcard", []string{}, []string{"onemind.node*.status"}, []string{"events:subscribe:onemind.>"}, false},
		{"space", []string{}, []string{"onemind.node .status"}, []string{"events:subscribe:onemind.>"}, false},
		{"control", []string{}, []string{"onemind.node\x00.status"}, []string{"events:subscribe:onemind.>"}, false},
		{"duplicate subscribe", []string{}, []string{"onemind.status", "onemind.status"}, []string{"events:subscribe:onemind.>"}, false},
		{"empty permission", []string{}, []string{}, []string{"events:subscribe:"}, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := Manifest(eventManifest(t, tt.publish, tt.subscribe, tt.permissions))
			if (err == nil) != tt.valid {
				t.Fatalf("valid=%v: %v", tt.valid, err)
			}
		})
	}
}

func TestEventPatternContainment(t *testing.T) {
	tests := []struct {
		grant, requested string
		covered          bool
	}{
		{"onemind.node.*.status", "onemind.node.a.status", true},
		{"onemind.node.*.status", "onemind.node.*.status", true},
		{"onemind.>", "onemind.node.*.status", true},
		{"onemind.>", "onemind.>", true},
		{"onemind.*.>", "onemind.node.*.status", true},
		{"onemind.*.>", "onemind.node.>", true},
		{"onemind.node.a.status", "onemind.node.*.status", false},
		{"onemind.node.*.status", "onemind.node.>", false},
		{"onemind.node.*", "onemind.node", false},
		{"onemind.>", "onemind", false},
		{"onemind.*.>", "onemind.node", false},
		{"onemind.*.>", "onemind.>", false},
		{"onemind.node.*.status", "onemind.node.a.status.extra", false},
		{"onemind.node.a.status", "onemind.node.a.status", true},
	}
	for _, tt := range tests {
		t.Run(tt.grant+"/"+tt.requested, func(t *testing.T) {
			grant, err := eventPattern(tt.grant)
			if err != nil {
				t.Fatal(err)
			}
			requested, err := eventPattern(tt.requested)
			if err != nil {
				t.Fatal(err)
			}
			if got := coversPattern(grant, requested); got != tt.covered {
				t.Fatalf("got %v, want %v", got, tt.covered)
			}
		})
	}
}

func TestInvalidEventPatterns(t *testing.T) {
	for _, pattern := range []string{"", ">", ".evt", "evt.", "evt..ready", "evt.>.ready", "evt.ready*", "evt.pre>fix", "evt.\t", "evt.\n", "evt.\x00", "evt.\u00a0", "evt.\xff"} {
		t.Run(pattern, func(t *testing.T) {
			if _, err := eventPattern(pattern); err == nil {
				t.Fatal("accepted malformed pattern")
			}
		})
	}
}
