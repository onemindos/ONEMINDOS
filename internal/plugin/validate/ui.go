// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"path"
	"regexp"
	"strings"
	"time"
)

// validateUI checks declarations only. Filesystem containment and static UI
// scanning run on the unpacked bundle; no plugin JavaScript runs here.
var uiName = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,39}$`)

func validateUI(spec, extensions map[string]any) error {
	tools := map[string]string{}
	declarations, _ := extensions["tools"].([]any)
	for _, raw := range declarations {
		tool := raw.(map[string]any)
		tools[tool["name"].(string)] = tool["effect"].(string)
	}
	widgets, _ := extensions["widgets"].([]any)
	ids := map[string]bool{}
	for _, raw := range widgets {
		widget := raw.(map[string]any)
		id := widget["id"].(string)
		if !uiName.MatchString(id) {
			return fmt.Errorf("invalid UI id %q", id)
		}
		if ids[id] {
			return fmt.Errorf("duplicate widget %q", id)
		}
		ids[id] = true
		if widget["render"] == "template" {
			source := widget["source"].(map[string]any)
			if tools[source["tool"].(string)] != "read" {
				return fmt.Errorf("widget %s source must name a declared read tool", id)
			}
			if refresh, ok := widget["refresh"].(string); ok {
				d, err := time.ParseDuration(refresh)
				if err != nil || d <= 0 {
					return fmt.Errorf("widget %s refresh must be a positive duration", id)
				}
			}
		} else {
			entry := widget["entry"].(string)
			if err := uiPath(entry); err != nil {
				return fmt.Errorf("widget %s entry: %w", id, err)
			}
			if !strings.HasPrefix(entry, "ui/") {
				return fmt.Errorf("widget %s entry must be below ui/", id)
			}
			for _, surface := range widget["surfaces"].([]any) {
				if surface == "mobile" {
					return fmt.Errorf("iframe widget %s cannot target mobile", id)
				}
			}
		}
	}
	if settings, ok := extensions["settings"].(map[string]any); ok {
		if err := uiPath(settings["schema"].(string)); err != nil {
			return fmt.Errorf("settings.schema: %w", err)
		}
	}
	if alerts, ok := extensions["alerts"].(map[string]any); ok {
		ids = map[string]bool{}
		for _, raw := range alerts["actions"].([]any) {
			action := raw.(map[string]any)
			id := action["id"].(string)
			if !uiName.MatchString(id) {
				return fmt.Errorf("invalid UI id %q", id)
			}
			if ids[id] {
				return fmt.Errorf("duplicate alert action %q", id)
			}
			ids[id] = true
			if tools[action["tool"].(string)] == "" {
				return fmt.Errorf("alert action %s must name a declared tool", id)
			}
		}
	}
	tiles, _ := extensions["tiles"].([]any)
	ids = map[string]bool{}
	for _, raw := range tiles {
		tile := raw.(map[string]any)
		id := tile["id"].(string)
		if !uiName.MatchString(id) {
			return fmt.Errorf("invalid UI id %q", id)
		}
		if ids[id] {
			return fmt.Errorf("duplicate tile %q", id)
		}
		ids[id] = true
		if _, ok := spec["web"]; !ok {
			return fmt.Errorf("tile %s opens web but spec.web is missing", id)
		}
		if icon, ok := tile["icon"].(string); ok {
			if err := uiPath(icon); err != nil {
				return fmt.Errorf("tile %s icon: %w", id, err)
			}
		}
	}
	return nil
}

func uiPath(value string) error {
	if value == "" || path.IsAbs(value) || strings.ContainsAny(value, `\:`) {
		return fmt.Errorf("path must be relative")
	}
	for _, c := range value {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || strings.ContainsRune("._-/", c)) {
			return fmt.Errorf("path contains an unsafe character")
		}
	}
	for _, segment := range strings.Split(value, "/") {
		if segment == ".." || segment == "." || segment == "" {
			return fmt.Errorf("path contains an unsafe component")
		}
	}
	return nil
}
