// SPDX-License-Identifier: Apache-2.0

package schema

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"regexp"
	"sort"
	"strings"
	"sync"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// DeviceCard is the device capability card contract (issue #727): a closed subset of a W3C WoT
// Thing Description 1.1 with an om:safety block per property and action.
//
//go:embed onemind.device-card.schema.json
var DeviceCard string

// DeviceCardContext is the JSON-LD context of the om: vocabulary a card uses.
//
//go:embed onemind.device-card.context.jsonld
var DeviceCardContext string

// MaxDeviceCardBytes is the largest card either validator reads.
const MaxDeviceCardBytes = 64 * 1024

// deviceCardRules are the rules this validator and sdk/tools/applib/devicecard.py share, by name.
var deviceCardRules = map[string]string{
	"credential-field":    "a card never carries a credential",
	"unitless-number":     "a number needs a unit",
	"physical-limits":     "a physical action needs limits",
	"physical-safe-state": "a physical action needs a safe state",
	"physical-owner-only": "a physical action is asked for by a person or agent and approved only by an owner",
	"hold-required":       "this class is approved with a hold: needsHold must be true",
	"agent-approver":      "an agent never approves",
	"schema":              "the card does not match onemind.device-card.schema.json",
}

var (
	credentialKey = regexp.MustCompile(`password|passwd|passphrase|secret|token|apikey|privatekey|credential|accesskey`)
	keySeparators = regexp.MustCompile(`[-_. ]`)
	urlUserinfo   = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*@`)
)

// CardProblem is one refused rule. It names the path, never the value, so no secret reaches a log.
type CardProblem struct{ Rule, Path, Message string }

// CardError lists every problem of a refused card.
type CardError struct{ Problems []CardProblem }

func (e *CardError) Error() string {
	parts := make([]string, len(e.Problems))
	for i, p := range e.Problems {
		parts[i] = fmt.Sprintf("%s at %s: %s", p.Rule, p.Path, p.Message)
	}
	return "device card: " + strings.Join(parts, "; ")
}

// ClassRisk is the action ledger's risk class and physical flag (#723) of a card class.
type ClassRisk struct {
	Risk     string `json:"risk"`
	Physical bool   `json:"physical"`
}

type noRemoteSchemas struct{}

func (noRemoteSchemas) Load(url string) (any, error) {
	return nil, fmt.Errorf("external schema reference forbidden: %s", url)
}

var deviceCardSchema = sync.OnceValues(func() (*jsonschema.Schema, error) {
	doc, err := jsonschema.UnmarshalJSON(strings.NewReader(DeviceCard))
	if err != nil {
		return nil, err
	}
	c := jsonschema.NewCompiler()
	c.UseLoader(noRemoteSchemas{})
	const url = "https://onemind.invalid/device-card"
	if err := c.AddResource(url, doc); err != nil {
		return nil, err
	}
	return c.Compile(url)
})

// DeviceCardClassRisk is the class-to-risk table, read from the schema (x-om-class-risk) so the Go
// and Python validators cannot disagree.
func DeviceCardClassRisk() (map[string]ClassRisk, error) {
	var doc struct {
		Table map[string]json.RawMessage `json:"x-om-class-risk"`
	}
	if err := json.Unmarshal([]byte(DeviceCard), &doc); err != nil {
		return nil, err
	}
	out := map[string]ClassRisk{}
	for k, raw := range doc.Table {
		if strings.HasPrefix(k, "$") {
			continue
		}
		var cr ClassRisk
		if err := json.Unmarshal(raw, &cr); err != nil {
			return nil, err
		}
		out[k] = cr
	}
	return out, nil
}

// HoldRequired is core/onemind_core/approvalcard.hold_required: physical, or cannot be undone.
func HoldRequired(cr ClassRisk) bool { return cr.Physical || cr.Risk == "destructive" }

func fail(rule, path, msg string) error {
	return &CardError{Problems: []CardProblem{{Rule: rule, Path: path, Message: msg}}}
}

// ValidateDeviceCard checks one JSON card: the shared rules first, then the JSON Schema.
// It returns nil or a *CardError.
func ValidateDeviceCard(data []byte) error {
	if len(data) > MaxDeviceCardBytes {
		return fail("size", "/", fmt.Sprintf("a card is at most %d bytes", MaxDeviceCardBytes))
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	var card any
	if err := dec.Decode(&card); err != nil {
		return fail("json", "/", "not one JSON document")
	}
	if _, err := dec.Token(); err != io.EOF {
		return fail("json", "/", "not one JSON document")
	}
	obj, ok := card.(map[string]any)
	if !ok {
		return fail("schema", "/", deviceCardRules["schema"])
	}
	table, err := DeviceCardClassRisk()
	if err != nil {
		return err
	}
	w := cardWalk{table: table}
	w.credentials(obj, "")
	for _, kind := range []string{"properties", "actions", "events"} {
		group, _ := obj[kind].(map[string]any)
		for _, name := range sortedKeys(group) {
			aff, ok := group[name].(map[string]any)
			if !ok {
				continue
			}
			path := "/" + kind + "/" + name
			switch kind {
			case "properties":
				w.units(aff, path)
			case "actions":
				w.units(aff["input"], path+"/input")
				w.units(aff["output"], path+"/output")
			case "events":
				w.units(aff["data"], path+"/data")
			}
			w.safety(aff["om:safety"], path+"/om:safety")
		}
	}
	if len(w.found) > 0 {
		return &CardError{Problems: w.found}
	}
	sch, err := deviceCardSchema()
	if err != nil {
		return err
	}
	var ve *jsonschema.ValidationError
	if err := sch.Validate(card); errors.As(err, &ve) {
		for len(ve.Causes) > 0 {
			ve = ve.Causes[0]
		}
		kw := "?"
		if ve.ErrorKind != nil {
			kw = strings.Join(ve.ErrorKind.KeywordPath(), "/")
		}
		return fail("schema", "/"+strings.Join(ve.InstanceLocation, "/"), fmt.Sprintf("%s (keyword %s)", deviceCardRules["schema"], kw))
	} else if err != nil {
		return err
	}
	return nil
}

type cardWalk struct {
	table map[string]ClassRisk
	found []CardProblem
}

func (w *cardWalk) add(path, rule string) {
	if path == "" {
		path = "/"
	}
	w.found = append(w.found, CardProblem{Rule: rule, Path: path, Message: deviceCardRules[rule]})
}

func sortedKeys(m map[string]any) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func hasUnit(m map[string]any) bool {
	u, ok := m["unit"].(string)
	return ok && strings.TrimSpace(u) != ""
}

func (w *cardWalk) credentials(node any, path string) {
	switch n := node.(type) {
	case map[string]any:
		for _, k := range sortedKeys(n) {
			if credentialKey.MatchString(keySeparators.ReplaceAllString(strings.ToLower(k), "")) {
				w.add(path+"/"+k, "credential-field")
			}
			w.credentials(n[k], path+"/"+k)
		}
	case []any:
		for i, v := range n {
			w.credentials(v, fmt.Sprintf("%s/%d", path, i))
		}
	case string:
		if urlUserinfo.MatchString(n) {
			w.add(path, "credential-field")
		}
	}
}

func (w *cardWalk) units(node any, path string) {
	ds, ok := node.(map[string]any)
	if !ok {
		return
	}
	if t, _ := ds["type"].(string); (t == "number" || t == "integer") && !hasUnit(ds) {
		w.add(path, "unitless-number")
	}
	props, _ := ds["properties"].(map[string]any)
	for _, k := range sortedKeys(props) {
		w.units(props[k], path+"/properties/"+k)
	}
	w.units(ds["items"], path+"/items")
}

func (w *cardWalk) safety(node any, path string) {
	s, ok := node.(map[string]any)
	if !ok {
		return
	}
	limits, _ := s["limits"].([]any)
	askers, _ := s["askers"].([]any)
	approvers, _ := s["approvers"].([]any)
	for i, l := range limits {
		if lim, ok := l.(map[string]any); ok && !hasUnit(lim) {
			w.add(fmt.Sprintf("%s/limits/%d", path, i), "unitless-number")
		}
	}
	state, hasState := s["safeState"].(map[string]any)
	if q, ok := state["quantity"].(map[string]any); ok && !hasUnit(q) {
		w.add(path+"/safeState/quantity", "unitless-number")
	}
	if contains(approvers, "agent") {
		w.add(path+"/approvers", "agent-approver")
	}
	class, _ := s["class"].(string)
	cr, known := w.table[class]
	if !known {
		return
	}
	if hold, _ := s["needsHold"].(bool); HoldRequired(cr) && !hold {
		w.add(path+"/needsHold", "hold-required")
	}
	if cr.Physical {
		if len(limits) == 0 {
			w.add(path+"/limits", "physical-limits")
		}
		if !hasState {
			w.add(path+"/safeState", "physical-safe-state")
		}
		if contains(askers, "automation") || len(approvers) != 1 || approvers[0] != "owner" {
			w.add(path, "physical-owner-only")
		}
	}
}

func contains(list []any, want string) bool {
	for _, v := range list {
		if s, ok := v.(string); ok && s == want {
			return true
		}
	}
	return false
}
