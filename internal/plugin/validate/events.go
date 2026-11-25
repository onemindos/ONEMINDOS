// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"strings"
	"unicode"
	"unicode/utf8"
)

const eventPermission = "events:subscribe:"

// validateEvents implements PLUGIN-SDK.md P4/P5. Publishing is namespaced by
// the gateway, never by a subject supplied in a manifest. This checks declarations
// only: it neither connects to NATS nor grants a plugin a NATS credential.
func validateEvents(spec, extensions map[string]any) error {
	var grants [][]string
	if permissions, ok := spec["permissions"].([]any); ok {
		for _, raw := range permissions {
			permission := raw.(string)
			if !strings.HasPrefix(permission, eventPermission) {
				continue
			}
			pattern := strings.TrimPrefix(permission, eventPermission)
			tokens, err := eventPattern(pattern)
			if err != nil {
				return fmt.Errorf("event permission %q: %w", permission, err)
			}
			grants = append(grants, tokens)
		}
	}
	events, ok := extensions["events"].(map[string]any)
	if !ok {
		return nil
	}
	if subscriptions, ok := events["subscribe"].([]any); ok {
		for _, raw := range subscriptions {
			pattern := raw.(string)
			tokens, err := eventPattern(pattern)
			if err != nil {
				return fmt.Errorf("events.subscribe %q: %w", pattern, err)
			}
			covered := false
			for _, grant := range grants {
				if coversPattern(grant, tokens) {
					covered = true
					break
				}
			}
			if !covered {
				return fmt.Errorf("events.subscribe %q lacks a covering events:subscribe permission", pattern)
			}
		}
	}
	return nil
}

// Only whole-token wildcards are supported: * is exactly one token, and a
// terminal > is one or more. Bare > is forbidden even as a permission grant.
func eventPattern(pattern string) ([]string, error) {
	if pattern == "" || pattern == ">" || !utf8.ValidString(pattern) {
		return nil, fmt.Errorf("empty or unrestricted event pattern")
	}
	for _, char := range pattern {
		if unicode.IsSpace(char) || unicode.IsControl(char) {
			return nil, fmt.Errorf("event pattern contains whitespace or control characters")
		}
	}
	tokens := strings.Split(pattern, ".")
	for i, token := range tokens {
		if token == "" {
			return nil, fmt.Errorf("event pattern contains an empty token")
		}
		if token == ">" {
			if i != len(tokens)-1 {
				return nil, fmt.Errorf("event wildcard > must be terminal")
			}
			continue
		}
		if token != "*" && strings.ContainsAny(token, "*>") {
			return nil, fmt.Errorf("event wildcards must occupy a whole token")
		}
	}
	return tokens, nil
}

// coversPattern is deliberately single-grant containment: it never combines
// several narrower permissions into a broader subscription. Both inputs have
// already passed eventPattern. A literal grant cannot authorize a wildcard.
func coversPattern(grant, requested []string) bool {
	for i, token := range grant {
		if token == ">" {
			return i < len(requested)
		}
		if i >= len(requested) || requested[i] == ">" {
			return false
		}
		if token != "*" && token != requested[i] {
			return false
		}
	}
	return len(grant) == len(requested)
}
