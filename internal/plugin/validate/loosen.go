// SPDX-License-Identifier: Apache-2.0

package validate

import "fmt"

// loosenedBlocks lists what a new version opens up in the manifest v1 blocks (#604): new hosts,
// providers, keys, redistribution, storage, display, NATS subjects, data classes, services, jobs
// and recording. Any reason sets widens_grants, so the owner approves the update again.
func loosenedBlocks(previous, current map[string]any) []string {
	var reasons []string
	added := func(what string, old, next any) {
		seen := map[string]bool{}
		for _, v := range asList(old) {
			seen[fmt.Sprint(v)] = true
		}
		for _, v := range asList(next) {
			if !seen[fmt.Sprint(v)] {
				reasons = append(reasons, what+" added: "+fmt.Sprint(v))
			}
		}
	}
	oldExt, newExt := asMap(previous["extensions"]), asMap(current["extensions"])
	for _, name := range []string{"bridge", "connector", "videoSource"} {
		oldBlock, newBlock := asMap(oldExt[name]), asMap(newExt[name])
		if newBlock == nil {
			continue
		}
		if oldBlock == nil {
			reasons = append(reasons, name+" added")
			continue
		}
		added(name+" host", oldBlock["hosts"], newBlock["hosts"])
		added(name+" scope", oldBlock["scopes"], newBlock["scopes"])
		if oldBlock["provider"] != newBlock["provider"] {
			reasons = append(reasons, name+" provider changed")
		}
		if name == "connector" && oldBlock["auth"] != newBlock["auth"] {
			reasons = append(reasons, "connector auth changed")
		}
		if name == "videoSource" && newBlock["record"] == true && oldBlock["record"] != true {
			reasons = append(reasons, "videoSource record switched on")
		}
	}
	oldNats, newNats := asMap(oldExt["nats"]), asMap(newExt["nats"])
	for _, field := range []string{"publish", "subscribe", "imports"} {
		added("nats "+field, oldNats[field], newNats[field])
	}
	oldData, newData := asMap(previous["data"]), asMap(current["data"])
	added("data owns", oldData["owns"], newData["owns"])
	added("data reads", oldData["reads"], newData["reads"])
	added("service", previous["services"], current["services"])
	jobs := func(spec map[string]any) []any {
		var ids []any
		for _, job := range asList(spec["jobs"]) {
			ids = append(ids, asMap(job)["id"])
		}
		return ids
	}
	added("job", jobs(previous), jobs(current))
	oldProviders := map[string]map[string]any{}
	for _, raw := range asList(asMap(previous["terms"])["providers"]) {
		oldProviders[fmt.Sprint(asMap(raw)["id"])] = asMap(raw)
	}
	for _, raw := range asList(asMap(current["terms"])["providers"]) {
		next := asMap(raw)
		id := fmt.Sprint(next["id"])
		old, ok := oldProviders[id]
		if !ok {
			reasons = append(reasons, "terms provider added: "+id)
			continue
		}
		for _, field := range []string{"mesh", "tak", "publicShare"} {
			if asMap(next["redistribute"])[field] == true && asMap(old["redistribute"])[field] != true {
				reasons = append(reasons, "terms redistribution widened: "+id+"/"+field)
			}
		}
		if next["keyNeeded"] == true && old["keyNeeded"] != true {
			reasons = append(reasons, "terms key added: "+id)
		}
		if old["personScoped"] == true && next["personScoped"] != true {
			reasons = append(reasons, "terms no longer person-scoped: "+id)
		}
		ranks := map[string][]string{
			"store":   {"none", "cache", "keep"},
			"display": {"link-only", "embed-only", "full"},
			"use":     {"personal", "non-commercial", "commercial"},
		}
		for field, order := range ranks {
			if position(order, next[field]) > position(order, old[field]) {
				reasons = append(reasons, fmt.Sprintf("terms %s widened: %s (%v -> %v)", field, id, old[field], next[field]))
			}
		}
		oldCache, _ := old["maxCacheSeconds"].(int)
		newCache, _ := next["maxCacheSeconds"].(int)
		if newCache > oldCache && old["store"] == next["store"] {
			reasons = append(reasons, "terms cache lengthened: "+id)
		}
	}
	return reasons
}

func position(order []string, value any) int {
	for i, v := range order {
		if v == value {
			return i
		}
	}
	return -1
}
