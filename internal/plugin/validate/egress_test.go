// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func egressManifest(t *testing.T, entries any) []byte {
	t.Helper()
	data, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	var value map[string]any
	if err := yaml.Unmarshal(data, &value); err != nil {
		t.Fatal(err)
	}
	value["spec"].(map[string]any)["egress"] = entries
	data, err = yaml.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestEgressManifest(t *testing.T) {
	tests := []struct {
		name    string
		entries []string
		valid   bool
	}{
		{"deny by default", []string{}, true},
		{"exact domain", []string{"api.example.com"}, true},
		{"registrable wildcard", []string{"*.example.com"}, true},
		{"deeper wildcard", []string{"*.api.example.co.uk"}, true},
		{"private registrable domain", []string{"*.my-plugin.github.io"}, true},
		{"uppercase", []string{"API.Example.COM"}, true},
		{"ordinary interior hyphens", []string{"ab--cd.example.com"}, true},
		{"valid punycode", []string{"xn--bcher-kva.de"}, true},
		{"subdomain and root", []string{"example.com", "*.example.com"}, true},
		{"public suffix wildcard", []string{"*.com"}, false},
		{"multi-label suffix wildcard", []string{"*.co.uk"}, false},
		{"private suffix wildcard", []string{"*.github.io"}, false},
		{"private suffix exact", []string{"github.io"}, true},
		{"single-label suffix", []string{"com"}, false},
		{"multi-label suffix exact", []string{"co.uk"}, true},
		{"bare wildcard", []string{"*"}, false},
		{"embedded wildcard", []string{"api.*.example.com"}, false},
		{"label prefix wildcard", []string{"api*.example.com"}, false},
		{"wildcard literal IPv4", []string{"*.203.0.113.1"}, false},
		{"IPv4", []string{"203.0.113.1"}, false},
		{"IPv6", []string{"2001:db8::1"}, false},
		{"bracketed IPv6", []string{"[2001:db8::1]"}, false},
		{"numeric shorthand", []string{"2130706433"}, false},
		{"HTTPS URL", []string{"https://api.example.com"}, false},
		{"userinfo", []string{"user" + "@" + "api.example.com"}, false},
		{"port", []string{"api.example.com:443"}, false},
		{"path", []string{"api.example.com/path"}, false},
		{"query", []string{"api.example.com?foo"}, false},
		{"fragment", []string{"api.example.com#foo"}, false},
		{"trailing dot", []string{"api.example.com."}, false},
		{"leading dot", []string{".example.com"}, false},
		{"empty label", []string{"api..example.com"}, false},
		{"underscore", []string{"api_name.example.com"}, false},
		{"leading hyphen", []string{"-api.example.com"}, false},
		{"trailing hyphen", []string{"api-.example.com"}, false},
		{"long label", []string{strings.Repeat("a", 64) + ".example.com"}, false},
		{"long hostname", []string{strings.Repeat("a.", 127) + "com"}, false},
		{"whitespace", []string{"api.example.com "}, false},
		{"newline", []string{"api.example.com\n"}, false},
		{"control", []string{"api.example.com\x00"}, false},
		{"unicode case folding", []string{"K.example.com"}, false},
		{"unicode", []string{"bücher.de"}, false},
		{"unicode dot", []string{"example。com"}, false},
		{"invalid punycode", []string{"xn--.com"}, false},
		{"localhost", []string{"localhost"}, false},
		{"localhost subdomain", []string{"api.localhost"}, false},
		{"local mDNS", []string{"api.local"}, false},
		{"internal", []string{"api.internal"}, false},
		{"onion", []string{"example.onion"}, false},
		{"reverse infrastructure", []string{"example.arpa"}, false},
		{"unknown suffix", []string{"api.corp"}, false},
		{"duplicate", []string{"api.example.com", "api.example.com"}, false},
		{"case duplicate", []string{"API.example.com", "api.example.com"}, false},
		{"non-host empty", []string{""}, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := Manifest(egressManifest(t, tt.entries))
			if (err == nil) != tt.valid {
				t.Fatalf("valid=%v, error=%v", tt.valid, err)
			}
		})
	}
	for name, entries := range map[string]any{"wrong type": "example.com", "non-string": []any{42}, "too many": make([]string, 65)} {
		t.Run(name, func(t *testing.T) {
			if err := Manifest(egressManifest(t, entries)); err == nil {
				t.Fatal("accepted malformed egress declaration")
			}
		})
	}
}
