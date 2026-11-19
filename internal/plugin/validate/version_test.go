// SPDX-License-Identifier: Apache-2.0

package validate

import "testing"

func TestToolUpdateMajorVersion(t *testing.T) {
	for _, change := range []string{"effect", "narrow input", "wider input", "remove"} {
		for _, version := range []string{"2.5.12", "2.6.0", "1.0.0", "3.0.0"} {
			t.Run(change+"/"+version, func(t *testing.T) {
				old, next := comparisonFixture(t), comparisonFixture(t)
				next["metadata"].(map[string]any)["version"] = version
				oldSpec := old["spec"].(map[string]any)
				nextSpec := next["spec"].(map[string]any)
				switch change {
				case "effect":
					toolsOf(nextSpec)[0].(map[string]any)["effect"] = "write"
				case "narrow input":
					toolsOf(nextSpec)[0].(map[string]any)["input"] = map[string]any{"type": "object", "additionalProperties": false, "required": []any{"name"}, "properties": map[string]any{"name": map[string]any{"type": "string"}}}
				case "wider input":
					toolsOf(nextSpec)[0].(map[string]any)["input"] = map[string]any{"type": "object", "additionalProperties": false, "properties": map[string]any{"name": map[string]any{"type": "string"}}}
				case "remove":
					extra := map[string]any{}
					for k, v := range toolsOf(oldSpec)[0].(map[string]any) {
						extra[k] = v
					}
					extra["name"] = "removed"
					oldSpec["extensions"].(map[string]any)["tools"] = append(toolsOf(oldSpec), extra)
				}
				result, err := Compare(manifestBytes(t, old), manifestBytes(t, next))
				if version == "3.0.0" && err != nil {
					t.Fatal(err)
				}
				if version != "3.0.0" && (err == nil || result != nil) {
					t.Fatal("accepted breaking change without higher major")
				}
			})
		}
	}
	// Display-only changes do not alter the tool contract.
	old, next := comparisonFixture(t), comparisonFixture(t)
	toolsOf(next["spec"].(map[string]any))[0].(map[string]any)["description"] = "Updated display text"
	if _, err := Compare(manifestBytes(t, old), manifestBytes(t, next)); err != nil {
		t.Fatal(err)
	}
}
