// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"reflect"
	"sort"

	"gopkg.in/yaml.v3"
)

// GrantDiff is informational. A widened grant needs a new owner approval;
// a false result never authorizes installation or bypasses another trust gate.
type GrantDiff struct {
	WidensGrants bool     `json:"widens_grants"`
	Reasons      []string `json:"reasons"`
}

// Compare validates both plugin manifests and compares grants for the same ID.
// Added strings are conservatively new grants even if another old grant may
// subsume them. Unknown or ambiguous declarations fail validation/comparison.
func Compare(previous, current []byte) (*GrantDiff, error) {
	manifests := make([]map[string]any, 2)
	for i, data := range [][]byte{previous, current} {
		if err := Manifest(data); err != nil {
			return nil, fmt.Errorf("manifest %d (previous=0, current=1): %w", i, err)
		}
		if err := yaml.Unmarshal(data, &manifests[i]); err != nil {
			return nil, err
		}
	}
	oldID := manifests[0]["metadata"].(map[string]any)["id"]
	newID := manifests[1]["metadata"].(map[string]any)["id"]
	if oldID != newID {
		return nil, fmt.Errorf("cannot compare different plugin IDs")
	}
	if err := checkToolVersion(manifests[0], manifests[1]); err != nil {
		return nil, err
	}
	return compareSpecs(manifests[0]["spec"].(map[string]any), manifests[1]["spec"].(map[string]any))
}

func compareSpecs(previous, current map[string]any) (*GrantDiff, error) {
	result := &GrantDiff{Reasons: []string{}}
	for _, field := range []string{"permissions", "egress"} {
		old, err := stringSet(previous[field])
		if err != nil {
			return nil, fmt.Errorf("previous %s: %w", field, err)
		}
		next, err := stringSet(current[field])
		if err != nil {
			return nil, fmt.Errorf("current %s: %w", field, err)
		}
		for value := range next {
			if !old[value] {
				result.Reasons = append(result.Reasons, field+" added: "+value)
			}
		}
	}
	oldSecrets, err := secretGrants(previous)
	if err != nil {
		return nil, err
	}
	newSecrets, err := secretGrants(current)
	if err != nil {
		return nil, err
	}
	for key, value := range newSecrets {
		old, exists := oldSecrets[key]
		if !exists {
			result.Reasons = append(result.Reasons, "secret grant added: "+key)
		} else if !reflect.DeepEqual(old, value) {
			result.Reasons = append(result.Reasons, "secret grant changed: "+key)
		}
	}
	oldEffects := effects(previous)
	for name, effect := range effects(current) {
		old := oldEffects[name]
		if rank(effect) > rank(old) {
			result.Reasons = append(result.Reasons, fmt.Sprintf("tool effect widened: %s (%s -> %s)", name, effectName(old), effect))
		}
	}
	oldExt, _ := previous["extensions"].(map[string]any)
	newExt, _ := current["extensions"].(map[string]any)
	oldEvents, _ := oldExt["events"].(map[string]any)
	newEvents, _ := newExt["events"].(map[string]any)
	oldSubscriptions, _ := stringSet(oldEvents["subscribe"])
	newSubscriptions, _ := stringSet(newEvents["subscribe"])
	for subject := range newSubscriptions {
		if !oldSubscriptions[subject] {
			result.Reasons = append(result.Reasons, "event subscription added: "+subject)
		}
	}
	oldAlerts := alertGrants(oldExt)
	for id, grant := range alertGrants(newExt) {
		if !reflect.DeepEqual(oldAlerts[id], grant) {
			result.Reasons = append(result.Reasons, "alert action added or changed: "+id)
		}
	}
	// Workload bytes are outside this manifest-only API. The lifecycle plan
	// fingerprint must bind those bytes and image pins before owner approval.
	for _, field := range []string{"manifests", "plugin"} {
		if !reflect.DeepEqual(previous[field], current[field]) {
			result.Reasons = append(result.Reasons, "workload declaration changed: "+field)
		}
	}
	sort.Strings(result.Reasons)
	result.WidensGrants = len(result.Reasons) > 0
	return result, nil
}

func alertGrants(ext map[string]any) map[string]any {
	result := map[string]any{}
	alerts, _ := ext["alerts"].(map[string]any)
	actions, _ := alerts["actions"].([]any)
	for _, value := range actions {
		action, _ := value.(map[string]any)
		id, _ := action["id"].(string)
		result[id] = map[string]any{"tool": action["tool"], "args": action["args"]}
	}
	return result
}

func stringSet(value any) (map[string]bool, error) {
	result := map[string]bool{}
	if value == nil {
		return result, nil
	}
	list, ok := value.([]any)
	if !ok {
		return nil, fmt.Errorf("expected string array")
	}
	for _, item := range list {
		s, ok := item.(string)
		if !ok {
			return nil, fmt.Errorf("expected string entry")
		}
		result[s] = true
	}
	return result, nil
}

func secretGrants(spec map[string]any) (map[string]map[string]any, error) {
	result := map[string]map[string]any{}
	names := map[string]bool{}
	secrets, _ := spec["secrets"].([]any)
	for _, raw := range secrets {
		secret := raw.(map[string]any)
		name := secret["name"].(string)
		if names[name] {
			return nil, fmt.Errorf("ambiguous duplicate secret %q", name)
		}
		names[name] = true
		for _, raw := range secret["keys"].([]any) {
			key := raw.(map[string]any)
			id := name + "/" + key["key"].(string)
			if _, exists := result[id]; exists {
				return nil, fmt.Errorf("ambiguous duplicate secret key %q", id)
			}
			// Match core/onemind_core/appsecrets/spec.py defaults; ignore display text.
			grant := map[string]any{"kind": "password", "required": false, "generate": false}
			for field, value := range key {
				if field != "key" && field != "description" {
					grant[field] = value
				}
			}
			result[id] = grant
		}
	}
	return result, nil
}

func effects(spec map[string]any) map[string]string {
	result := map[string]string{}
	ext := spec["extensions"].(map[string]any)
	tools, _ := ext["tools"].([]any)
	for _, raw := range tools {
		tool := raw.(map[string]any)
		result[tool["name"].(string)] = tool["effect"].(string)
	}
	return result
}
func rank(effect string) int {
	switch effect {
	case "write":
		return 1
	case "destructive":
		return 2
	}
	return 0
}
func effectName(effect string) string {
	if effect == "" {
		return "absent"
	}
	return effect
}
