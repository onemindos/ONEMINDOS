// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"reflect"
	"sort"

	"github.com/Masterminds/semver/v3"
)

// checkToolVersion implements PLUGIN-SDK.md §13. General JSON Schema inclusion
// is not inferred: any changed input schema conservatively needs a major bump.
// Callers have already validated both manifests and matched their IDs.
func checkToolVersion(previous, current map[string]any) error {
	oldVersion, _ := semver.StrictNewVersion(previous["metadata"].(map[string]any)["version"].(string))
	newVersion, _ := semver.StrictNewVersion(current["metadata"].(map[string]any)["version"].(string))
	if newVersion.Major() > oldVersion.Major() {
		return nil
	}
	oldTools := toolDeclarations(previous["spec"].(map[string]any))
	newTools := toolDeclarations(current["spec"].(map[string]any))
	names := make([]string, 0, len(oldTools))
	for name := range oldTools {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		old := oldTools[name]
		next, exists := newTools[name]
		if !exists {
			return fmt.Errorf("tool %s removed: a higher plugin major version is required", name)
		}
		if old["effect"] != next["effect"] {
			return fmt.Errorf("tool %s effect changed: a higher plugin major version is required", name)
		}
		if !reflect.DeepEqual(old["input"], next["input"]) {
			return fmt.Errorf("tool %s input schema changed: a higher plugin major version is required", name)
		}
	}
	return nil
}
func toolDeclarations(spec map[string]any) map[string]map[string]any {
	result := map[string]map[string]any{}
	tools, _ := spec["extensions"].(map[string]any)["tools"].([]any)
	for _, raw := range tools {
		tool := raw.(map[string]any)
		result[tool["name"].(string)] = tool
	}
	return result
}
