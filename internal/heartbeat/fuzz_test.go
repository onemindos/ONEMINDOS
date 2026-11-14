// SPDX-License-Identifier: Apache-2.0

package heartbeat

// Native Go fuzz targets (docs/testing/PROPERTY-AND-FUZZ.md). `go test ./...` runs each
// target on its seed corpus only; `go test -fuzz=<Target> -fuzztime=30s ./internal/heartbeat`
// explores. The hub side of the same subject and object has Hypothesis properties in
// core/tests/test_properties_heartbeat.py.

import (
	"bytes"
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

// natsSubject splits s by the NATS subject rules (docs.nats.io, "Subject-Based Messaging"):
// tokens separated by '.', none empty, no whitespace. literal reports that no token is a
// wildcard ('*' or '>'), i.e. the subject names one stream of messages and nothing wider.
func natsSubject(s string) (tokens []string, valid, literal bool) {
	if s == "" {
		return nil, false, false
	}
	tokens = strings.Split(s, ".")
	literal = true
	for _, t := range tokens {
		if t == "" || strings.ContainsAny(t, " \t\r\n\f\v") {
			return tokens, false, false
		}
		if t == "*" || t == ">" {
			literal = false
		}
	}
	return tokens, true, literal
}

// FuzzNodeIDSubject: a node id ValidateNodeID accepts always yields a literal four-token subject
// whose third token is that id, so an id can never widen or redirect the subject a node
// publishes on (onemind.node.*.status, onemind.>, another node's subject). And an id is accepted
// exactly when it is 1-64 ASCII letters, digits, '_' or '-' (contract §2), the same rule the
// hub's SUBJECT_RE applies.
func FuzzNodeIDSubject(f *testing.F) {
	for _, s := range []string{"3f9c2a1b7d4e", "beelink", "Node_01-a", "", "*", ">", "a.b", "a b", "a\nb",
		"node.*", "nodé", strings.Repeat("a", 64), strings.Repeat("a", 65), "a\x00b", "-", "_"} {
		f.Add(s)
	}
	f.Fuzz(func(t *testing.T, id string) {
		charset := len(id) >= 1 && len(id) <= 64
		for i := 0; i < len(id); i++ {
			c := id[i]
			if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_' || c == '-') {
				charset = false
			}
		}
		err := ValidateNodeID(id)
		if (err == nil) != charset {
			t.Fatalf("ValidateNodeID(%q) = %v, contract charset says accepted=%v", id, err, charset)
		}
		if err != nil {
			return
		}
		tokens, valid, literal := natsSubject(Subject(id))
		if !valid || !literal || len(tokens) != 4 || tokens[0] != "onemind" || tokens[1] != "node" ||
			tokens[2] != id || tokens[3] != "status" {
			t.Fatalf("Subject(%q) = %q: tokens %q valid=%v literal=%v", id, Subject(id), tokens, valid, literal)
		}
	})
}

// forbiddenKeys are the privacy rule's fields (contract §2; the hub drops the same set,
// core/onemind_core/nodes.py FORBIDDEN_KEYS).
var forbiddenKeys = []string{"serial", "serial_number", "mac", "mac_address", "macs", "ip", "ips",
	"ip_address", "user", "users", "username", "device", "path"}

// FuzzStatusJSON: any JSON a Status decodes from encodes to a stable contract shape. Re-encoding
// is a fixed point (encode, decode, encode gives the same bytes and an equal value), every §2 key
// is always present, "update" appears only when set, and no key outside the struct survives: a
// heartbeat that went through Status cannot carry a serial number, MAC, IP or user name even if
// the input had one.
func FuzzStatusJSON(f *testing.F) {
	full, _ := json.Marshal(Status{Schema: Schema, NodeID: "3f9c2a1b7d4e", Role: "hub", Board: BoardVM,
		RAUC: RAUC{Slots: []Slot{{Name: "rootfs.0", State: "booted"}}}, Update: &Update{Channel: "security", State: UpdateIdle}})
	f.Add(full)
	f.Add([]byte(`{}`))
	f.Add([]byte(`{"schema":"onemind.node.status/v1","node_id":"a","serial":"X1","mac":"00:11","ip":"203.0.113.9","user":"root","rauc":{"slots":null,"device":"/dev/disk/by-id/ata-SERIAL"}}`))
	f.Add([]byte(`{"k3s":{"role":null},"gpu":{"model":null},"update":null,"cpus":-1,"disk_free_gb":1e308}`))
	f.Add([]byte(`{"rauc":{"slots":[{"name":"rootfs.1","device":"/dev/sda2"}]},"node_id":"é\ud800"}`))
	f.Fuzz(func(t *testing.T, data []byte) {
		var s Status
		if json.Unmarshal(data, &s) != nil {
			return
		}
		b1, err := json.Marshal(s)
		if err != nil {
			t.Fatalf("decoded but cannot encode: %v", err)
		}
		var s2 Status
		if err := json.Unmarshal(b1, &s2); err != nil {
			t.Fatalf("own encoding does not decode: %v\n%s", err, b1)
		}
		b2, _ := json.Marshal(s2)
		if !bytes.Equal(b1, b2) || !reflect.DeepEqual(s, s2) {
			t.Fatalf("not a fixed point:\n%s\n%s", b1, b2)
		}
		var top map[string]json.RawMessage
		if err := json.Unmarshal(b1, &top); err != nil {
			t.Fatal(err)
		}
		for _, k := range []string{"schema", "node_id", "hostname", "role", "board", "arch", "os", "kernel",
			"cpu_model", "cpus", "mem_total_mb", "mem_available_mb", "disk_total_gb", "disk_free_gb", "tpm2",
			"secure_boot", "k3s", "rauc", "gpu", "uptime_s", "agent_version", "observed_at"} {
			if _, ok := top[k]; !ok {
				t.Fatalf("encoding lacks %q: %s", k, b1)
			}
		}
		if _, ok := top["update"]; ok != (s.Update != nil) {
			t.Fatalf("update present=%v but set=%v", ok, s.Update != nil)
		}
		var anyKeys func(v any)
		anyKeys = func(v any) {
			switch x := v.(type) {
			case map[string]any:
				for k, child := range x {
					for _, bad := range forbiddenKeys {
						if strings.EqualFold(k, bad) {
							t.Fatalf("encoding carries forbidden key %q: %s", k, b1)
						}
					}
					anyKeys(child)
				}
			case []any:
				for _, child := range x {
					anyKeys(child)
				}
			}
		}
		var tree any
		_ = json.Unmarshal(b1, &tree)
		anyKeys(tree)
	})
}
