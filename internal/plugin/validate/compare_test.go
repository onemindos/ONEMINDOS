// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"reflect"
	"testing"

	"gopkg.in/yaml.v3"
)

func comparisonFixture(t *testing.T) map[string]any {
	t.Helper()
	data, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	var value map[string]any
	if err := yaml.Unmarshal(data, &value); err != nil {
		t.Fatal(err)
	}
	return value
}
func manifestBytes(t *testing.T, value map[string]any) []byte {
	t.Helper()
	data, err := yaml.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}
func secret(name, key string) map[string]any {
	return map[string]any{"name": name, "keys": []any{map[string]any{"key": key}}}
}
func toolsOf(spec map[string]any) []any { return spec["extensions"].(map[string]any)["tools"].([]any) }

func TestCompareGrants(t *testing.T) {
	tests := []struct {
		name    string
		change  func(map[string]any, map[string]any)
		reasons []string
	}{
		{"unchanged", func(_, _ map[string]any) {}, []string{}},
		{"new permission", func(_, next map[string]any) { next["permissions"] = append(next["permissions"].([]any), "apps:read") }, []string{"permissions added: apps:read"}},
		{"removed permission", func(_, next map[string]any) { next["permissions"] = []any{} }, []string{}},
		{"reordered permission", func(_, next map[string]any) { p := next["permissions"].([]any); p[0], p[1] = p[1], p[0] }, []string{}},
		{"conservative narrowing", func(old, next map[string]any) {
			old["permissions"] = []any{"events:subscribe:onemind.>"}
			next["permissions"] = []any{"events:subscribe:onemind.status"}
		}, []string{"permissions added: events:subscribe:onemind.status"}},
		{"new secret", func(_, next map[string]any) { next["secrets"] = []any{secret("service-auth", "TOKEN")} }, []string{"secret grant added: service-auth/TOKEN"}},
		{"new key", func(old, next map[string]any) {
			old["secrets"] = []any{secret("service-auth", "TOKEN")}
			s := secret("service-auth", "TOKEN")
			s["keys"] = append(s["keys"].([]any), map[string]any{"key": "PASSWORD"})
			next["secrets"] = []any{s}
		}, []string{"secret grant added: service-auth/PASSWORD"}},
		{"removed secret", func(old, _ map[string]any) { old["secrets"] = []any{secret("service-auth", "TOKEN")} }, []string{}},
		{"changed secret semantics", func(old, next map[string]any) {
			old["secrets"] = []any{secret("service-auth", "TOKEN")}
			s := secret("service-auth", "TOKEN")
			s["keys"].([]any)[0].(map[string]any)["generate"] = true
			next["secrets"] = []any{s}
		}, []string{"secret grant changed: service-auth/TOKEN"}},
		{"secret display text", func(old, next map[string]any) {
			old["secrets"] = []any{secret("service-auth", "TOKEN")}
			s := secret("service-auth", "TOKEN")
			s["description"] = "new display text"
			s["keys"].([]any)[0].(map[string]any)["description"] = "new help"
			next["secrets"] = []any{s}
		}, []string{}},
		{"normalized secret defaults", func(old, next map[string]any) {
			old["secrets"] = []any{secret("service-auth", "TOKEN")}
			s := secret("service-auth", "TOKEN")
			key := s["keys"].([]any)[0].(map[string]any)
			key["kind"] = "password"
			key["required"] = false
			key["generate"] = false
			next["secrets"] = []any{s}
		}, []string{}},
		{"read becomes write", func(_, next map[string]any) { toolsOf(next)[0].(map[string]any)["effect"] = "write" }, []string{"tool effect widened: status (read -> write)"}},
		{"write becomes destructive", func(old, next map[string]any) {
			toolsOf(old)[0].(map[string]any)["effect"] = "write"
			toolsOf(next)[0].(map[string]any)["effect"] = "destructive"
		}, []string{"tool effect widened: status (write -> destructive)"}},
		{"destructive becomes read", func(old, _ map[string]any) { toolsOf(old)[0].(map[string]any)["effect"] = "destructive" }, []string{}},
		{"new write tool", func(_, next map[string]any) {
			tool := toolsOf(next)[0].(map[string]any)
			clone := map[string]any{}
			for k, v := range tool {
				clone[k] = v
			}
			clone["name"] = "reset"
			clone["effect"] = "write"
			next["extensions"].(map[string]any)["tools"] = append(toolsOf(next), clone)
		}, []string{"tool effect widened: reset (absent -> write)"}},
		{"new read tool", func(_, next map[string]any) {
			tool := toolsOf(next)[0].(map[string]any)
			clone := map[string]any{}
			for k, v := range tool {
				clone[k] = v
			}
			clone["name"] = "read_more"
			next["extensions"].(map[string]any)["tools"] = append(toolsOf(next), clone)
		}, []string{}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			old, next := comparisonFixture(t), comparisonFixture(t)
			next["metadata"].(map[string]any)["version"] = "3.0.0"
			tt.change(old["spec"].(map[string]any), next["spec"].(map[string]any))
			got, err := Compare(manifestBytes(t, old), manifestBytes(t, next))
			if err != nil {
				t.Fatal(err)
			}
			if got.WidensGrants != (len(tt.reasons) > 0) || !reflect.DeepEqual(got.Reasons, tt.reasons) {
				t.Fatalf("got %+v, want %v", got, tt.reasons)
			}
		})
	}
}

func TestCompareRejectsInvalidOrAmbiguousInputs(t *testing.T) {
	for _, mutate := range []func(map[string]any){
		func(v map[string]any) { v["metadata"].(map[string]any)["id"] = "another-plugin" },
		func(v map[string]any) { v["spec"].(map[string]any)["permissions"] = []any{"actions:approve"} },
		func(v map[string]any) {
			v["spec"].(map[string]any)["secrets"] = []any{secret("service-auth", "TOKEN"), secret("service-auth", "OTHER")}
		},
		func(v map[string]any) {
			s := secret("service-auth", "TOKEN")
			s["keys"] = append(s["keys"].([]any), map[string]any{"key": "TOKEN"})
			v["spec"].(map[string]any)["secrets"] = []any{s}
		},
	} {
		old, next := comparisonFixture(t), comparisonFixture(t)
		mutate(next)
		if _, err := Compare(manifestBytes(t, old), manifestBytes(t, next)); err == nil {
			t.Fatal("accepted invalid/ambiguous current input")
		}
	}
	valid := manifestBytes(t, comparisonFixture(t))
	if _, err := Compare([]byte("invalid"), valid); err == nil {
		t.Fatal("previous input was not validated")
	}
	if _, err := Compare(valid, []byte("invalid")); err == nil {
		t.Fatal("current input was not validated")
	}
}

func TestCompareEgressAndDeterministicOrder(t *testing.T) {
	// egress is currently absent from the schema. Exercise the pure comparison
	// seam so the same checks apply once the independent egress schema slice lands.
	old, next := comparisonFixture(t)["spec"].(map[string]any), comparisonFixture(t)["spec"].(map[string]any)
	old["egress"] = []any{"old.example"}
	next["egress"] = []any{"z.example", "a.example"}
	next["permissions"] = append(next["permissions"].([]any), "apps:read")
	want := []string{"egress added: a.example", "egress added: z.example", "permissions added: apps:read"}
	for range 10 {
		got, err := compareSpecs(old, next)
		if err != nil {
			t.Fatal(err)
		}
		if !got.WidensGrants || !reflect.DeepEqual(got.Reasons, want) {
			t.Fatalf("%+v", got)
		}
	}
	next["egress"] = map[string]any{"unexpected": "shape"}
	if _, err := compareSpecs(old, next); err == nil {
		t.Fatal("accepted unknown egress shape")
	}
}

func TestComparePublicEgress(t *testing.T) {
	old, next := comparisonFixture(t), comparisonFixture(t)
	old["spec"].(map[string]any)["egress"] = []any{"api.example.com"}
	next["spec"].(map[string]any)["egress"] = []any{"api.example.com", "new.example.com"}
	result, err := Compare(manifestBytes(t, old), manifestBytes(t, next))
	if err != nil {
		t.Fatal(err)
	}
	if !result.WidensGrants || !reflect.DeepEqual(result.Reasons, []string{"egress added: new.example.com"}) {
		t.Fatalf("%+v", result)
	}
	next["spec"].(map[string]any)["egress"] = []any{"*.com"}
	if _, err := Compare(manifestBytes(t, old), manifestBytes(t, next)); err == nil {
		t.Fatal("grant comparison bypassed egress validation")
	}
}
