// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strings"
	"sync"

	"github.com/onemindos/onemindos/sdk/schema"
)

// Manifest v1 (#604): the rules JSON Schema cannot say. core/onemind_core/manifest_rules.py runs
// the same rules with the same messages for Catalog.validate, and both read the golden cases in
// sdk/testdata/manifest-v1, so CI and the box refuse the same manifests.

// generated is the one word a field with a credential name may hold (spec.credentials.password).
const generated = "generated"

type credentialPatterns struct{ value, name *regexp.Regexp }

// credentials compiles the patterns kept once in the app schema's $defs (credentialValue, credentialName).
var credentials = sync.OnceValues(func() (credentialPatterns, error) {
	var doc struct {
		Defs map[string]struct {
			Pattern string `json:"pattern"`
		} `json:"$defs"`
	}
	if err := json.Unmarshal([]byte(schema.App), &doc); err != nil {
		return credentialPatterns{}, err
	}
	value, err := regexp.Compile(doc.Defs["credentialValue"].Pattern)
	if err != nil {
		return credentialPatterns{}, fmt.Errorf("credentialValue: %w", err)
	}
	name, err := regexp.Compile(doc.Defs["credentialName"].Pattern)
	if err != nil {
		return credentialPatterns{}, fmt.Errorf("credentialName: %w", err)
	}
	if value.String() == "" || name.String() == "" {
		return credentialPatterns{}, fmt.Errorf("app schema lacks the credential patterns")
	}
	return credentialPatterns{value, name}, nil
})

const credentialMessage = "holds a credential value; name a spec.secrets entry instead"

// validateCredentials refuses any field that holds a credential. It runs before the schema, so no
// later message can repeat the value; its own messages name the field only.
func validateCredentials(value any) error {
	p, err := credentials()
	if err != nil {
		return fmt.Errorf("app schema: %w", err)
	}
	return walkCredentials(p, value, "")
}

func walkCredentials(p credentialPatterns, value any, path string) error {
	switch v := value.(type) {
	case map[string]any:
		keys := make([]string, 0, len(v))
		for k := range v {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for _, k := range keys {
			where := k
			if path != "" {
				where = path + "/" + k
			}
			if s, ok := v[k].(string); ok && s != "" && s != generated && p.name.MatchString(k) {
				return fmt.Errorf("%s: %s", where, credentialMessage)
			}
			if err := walkCredentials(p, v[k], where); err != nil {
				return err
			}
		}
	case []any:
		for i, item := range v {
			if err := walkCredentials(p, item, fmt.Sprintf("%s/%d", path, i)); err != nil {
				return err
			}
		}
	case string:
		if p.value.MatchString(v) {
			if path == "" {
				path = "<root>"
			}
			return fmt.Errorf("%s: %s", path, credentialMessage)
		}
	}
	return nil
}

// hide keeps only the field of a message that would repeat a credential.
func hide(err error) error {
	if err == nil {
		return nil
	}
	p, perr := credentials()
	if perr != nil || !p.value.MatchString(err.Error()) {
		return err
	}
	field, _, _ := strings.Cut(err.Error(), ":")
	return fmt.Errorf("%s: value refused (hidden: it looks like a credential)", field)
}

func asMap(v any) map[string]any {
	m, _ := v.(map[string]any)
	return m
}

func asList(v any) []any {
	l, _ := v.([]any)
	return l
}

// validateBlocks runs the cross-field rules on a schema-valid spec: hosts, providers, interval
// floors, the app's own layers, declared tools and recording. The first broken rule is returned.
func validateBlocks(spec map[string]any) error {
	if spec["runtime"] == "module" {
		return fmt.Errorf("spec.runtime: module is only for apps on the signed system apps list; a plugin never runs in-process")
	}
	ext := asMap(spec["extensions"])
	egress := map[string]bool{}
	for _, e := range asList(spec["egress"]) {
		if s, ok := e.(string); ok {
			egress[s] = true
		}
	}
	providers := map[string]map[string]any{}
	for _, raw := range asList(asMap(spec["terms"])["providers"]) {
		if p := asMap(raw); p != nil {
			id, _ := p["id"].(string)
			providers[id] = p
		}
	}
	for _, name := range []string{"bridge", "connector", "videoSource"} {
		block := asMap(ext[name])
		if block == nil {
			continue
		}
		where := "spec/extensions/" + name
		for _, host := range asList(block["hosts"]) {
			if s, _ := host.(string); !egress[s] {
				return hide(fmt.Errorf("%s/hosts: %v is not in spec.egress", where, host))
			}
		}
		provider, ok := providers[fmt.Sprint(block["provider"])]
		if !ok {
			return hide(fmt.Errorf("%s/provider: %v has no terms record in spec.terms.providers", where, block["provider"]))
		}
		every, hasEvery := block["everySeconds"].(int)
		floor, hasFloor := provider["minIntervalSeconds"].(int)
		if hasEvery && hasFloor && every < floor {
			return fmt.Errorf("%s/everySeconds: %d is below the provider's minIntervalSeconds (%d)", where, every, floor)
		}
		if name == "videoSource" && block["record"] == true && (provider["display"] != "full" || provider["store"] == "none") {
			return fmt.Errorf("%s/record: record needs a provider with display full and a store", where)
		}
	}
	layers := map[string]bool{}
	for _, raw := range asList(spec["mapLayers"]) {
		if layer := asMap(raw); layer != nil && layer["source"] == "emits" {
			layers[fmt.Sprint(layer["id"])] = true
		}
	}
	for i, raw := range asList(asMap(ext["bridge"])["emits"]) {
		if emit := asMap(raw); emit != nil && emit["kind"] == "layer" && !layers[fmt.Sprint(emit["name"])] {
			return fmt.Errorf("spec/extensions/bridge/emits/%d: layer %v is not one of this app's mapLayers with source emits", i, emit["name"])
		}
	}
	tools := map[string]string{}
	for _, raw := range asList(ext["tools"]) {
		if tool := asMap(raw); tool != nil {
			effect, _ := tool["effect"].(string)
			tools[fmt.Sprint(tool["name"])] = effect
		}
	}
	for i, raw := range asList(spec["jobs"]) {
		name := fmt.Sprint(asMap(raw)["tool"])
		effect, ok := tools[name]
		if !ok {
			return fmt.Errorf("spec/jobs/%d/tool: %s is not a declared tool", i, name)
		}
		if effect == "destructive" {
			return fmt.Errorf("spec/jobs/%d/tool: a job may not call a destructive tool (%s)", i, name)
		}
	}
	for t, rawTopic := range asList(asMap(spec["notifications"])["topics"]) {
		for a, rawAction := range asList(asMap(rawTopic)["actions"]) {
			name := fmt.Sprint(asMap(rawAction)["tool"])
			if _, ok := tools[name]; !ok {
				return fmt.Errorf("spec/notifications/topics/%d/actions/%d/tool: %s is not a declared tool", t, a, name)
			}
		}
	}
	return nil
}
