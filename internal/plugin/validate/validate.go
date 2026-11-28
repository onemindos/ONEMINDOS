// SPDX-License-Identifier: Apache-2.0

// Package validate checks plugin tool manifests offline. It does not authorize
// installation or execution: signatures, scan gates and owner approval still apply.
package validate

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	"github.com/Masterminds/semver/v3"
	"github.com/dlclark/regexp2"
	"github.com/onemindos/onemindos/sdk/schema"
	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
)

const MaxManifestBytes = 256 * 1024

type offline struct{}

func (offline) Load(url string) (any, error) {
	return nil, fmt.Errorf("external schema reference forbidden: %s", url)
}

type expression struct{ *regexp2.Regexp }

func (r expression) MatchString(s string) bool {
	ok, err := r.Regexp.MatchString(s)
	return err == nil && ok
}
func compiler() *jsonschema.Compiler {
	c := jsonschema.NewCompiler()
	c.UseLoader(offline{})
	c.UseRegexpEngine(pattern)
	c.AssertFormat()
	return c
}

// pattern compiles a schema "pattern" the way JSON Schema expects (ECMAScript)
// with a match timeout, so a hostile manifest cannot stall validation.
func pattern(s string) (jsonschema.Regexp, error) {
	r, err := regexp2.Compile(s, regexp2.ECMAScript)
	if err != nil {
		return nil, err
	}
	r.MatchTimeout = patternTimeout
	return expression{r}, nil
}

const patternTimeout = 100 * time.Millisecond

var compiled = sync.OnceValues(func() (*jsonschema.Schema, error) {
	c := compiler()
	doc, err := jsonschema.UnmarshalJSON(strings.NewReader(schema.App))
	if err != nil {
		return nil, err
	}
	if err = c.AddResource("https://onemind.invalid/app", doc); err != nil {
		return nil, err
	}
	return c.Compile("https://onemind.invalid/app")
})

// Manifest validates a single YAML/JSON document, including the existing app
// contract. Unknown extension types fail closed until their validators ship.
func Manifest(data []byte) error {
	if len(data) > MaxManifestBytes {
		return fmt.Errorf("manifest exceeds %d bytes", MaxManifestBytes)
	}
	var value map[string]any
	d := yaml.NewDecoder(strings.NewReader(string(data)))
	if err := d.Decode(&value); err != nil {
		return fmt.Errorf("manifest: %w", err)
	}
	var extra any
	if err := d.Decode(&extra); err != io.EOF {
		return fmt.Errorf("expected exactly one manifest document")
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return fmt.Errorf("manifest must contain JSON-compatible values: %w", err)
	}
	if err := validateCredentials(value); err != nil {
		return err
	}
	if err := validateMachineNames(value); err != nil {
		return err
	}
	doc, err := jsonschema.UnmarshalJSON(strings.NewReader(string(encoded)))
	if err != nil {
		return err
	}
	s, err := compiled()
	if err != nil {
		return fmt.Errorf("app schema: %w", err)
	}
	if err = s.Validate(doc); err != nil {
		return hide(fmt.Errorf("manifest: %w", err))
	}
	spec := value["spec"].(map[string]any)
	ext, ok := spec["extensions"].(map[string]any)
	if !ok {
		return fmt.Errorf("plugin requires spec.extensions")
	}
	metadata := value["metadata"].(map[string]any)
	if _, err := semver.StrictNewVersion(metadata["version"].(string)); err != nil {
		return fmt.Errorf("plugin version: %w", err)
	}
	compat := spec["compat"].(map[string]any)
	if _, err := semver.NewConstraint(compat["onemind"].(string)); err != nil {
		return fmt.Errorf("compat.onemind: %w", err)
	}
	if err := validateEgress(spec); err != nil {
		return err
	}
	if err := validateEvents(spec, ext); err != nil {
		return err
	}
	if err := validateUI(spec, ext); err != nil {
		return err
	}
	if err := validateBlocks(spec); err != nil {
		return err
	}
	if err := validateMachine(spec); err != nil {
		return err
	}
	seen := map[string]bool{}
	tools, _ := ext["tools"].([]any)
	for _, raw := range tools {
		tool := raw.(map[string]any)
		name := tool["name"].(string)
		if seen[name] {
			return fmt.Errorf("duplicate tool %q", name)
		}
		seen[name] = true
		for _, field := range []string{"input", "output"} {
			v, present := tool[field]
			if !present {
				continue
			}
			js := v.(map[string]any)
			if dialect, present := js["$schema"]; present && dialect != "https://json-schema.org/draft/2020-12/schema" && dialect != "https://json-schema.org/draft/2020-12/schema#" {
				return fmt.Errorf("tool %s %s must use JSON Schema 2020-12", name, field)
			}
			if js["type"] != "object" || js["additionalProperties"] != false {
				return fmt.Errorf("tool %s %s must be a closed object schema", name, field)
			}
			c := compiler()
			b, _ := json.Marshal(js)
			schemaDoc, err := jsonschema.UnmarshalJSON(strings.NewReader(string(b)))
			if err != nil {
				return err
			}
			loc := "https://onemind.invalid/tool"
			if err = c.AddResource(loc, schemaDoc); err != nil {
				return err
			}
			if _, err = c.Compile(loc); err != nil {
				return fmt.Errorf("tool %s %s: %w", name, field, err)
			}
		}
	}
	return nil
}
