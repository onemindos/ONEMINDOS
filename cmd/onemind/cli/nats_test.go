// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The hub answers below have the shape of GET /v1/engine (core/onemind_core/engine/feed.py).
const engineAll = `{"at":"2026-11-22T10:00:00Z","scope":"all",
"monitor":{"state":"up","checked_at":"2026-11-22T10:00:00Z","errors":{}},
"health":{"status":"ok","error":null},"links":{"up":1,"down":1},
"jetstream":{"state":"ready","reason":"","enabled":true,"used_bytes":67108864,"cap_bytes":268435456,
"planned_cap_bytes":268435456,"used_pct":25.0,"reserved_bytes":134217728,"streams":3,"consumers":2},
"server":{"version":"2.15.3","uptime":"1h2m3s","connections":4,"total_connections":9,"leafnodes":1,"in_msgs":1,"out_msgs":2},
"accounts":[{"account":"ONEMIND","node_id":null,"connections":2,"leafnodes":0,"jetstream_bytes":67108864},
{"account":"NODE_aaaa1111","node_id":"aaaa1111","connections":1,"leafnodes":1,"jetstream_bytes":null}],
"nodes":[{"node_id":"aaaa1111","link":"up","rtt":"1.2ms","heartbeat":"online",
"outbox":{"stream":"NODE_node_aaaa1111_OUTBOX","messages":47,"bytes":4700,"lag":40,"last_active_s":1.5,"error":null}},
{"node_id":"bbbb2222","link":"down","rtt":null,"heartbeat":"stale","outbox":null}],
"slow_consumers":{"total":1,"clients":1,"routes":0,"gateways":0,"leafs":0},"connections_truncated":false}`

const engineSummary = `{"at":"t","scope":"summary","monitor":{"state":"up","checked_at":"t","errors":{}},
"health":{"status":"ok","error":null},"links":{"up":2,"down":0},
"jetstream":{"state":"refused","reason":"NATS runs JetStream without a cap","enabled":true,"used_bytes":1,"cap_bytes":0,
"planned_cap_bytes":null,"used_pct":null,"reserved_bytes":null,"streams":0,"consumers":0},
"server":null,"accounts":[],"nodes":[],"slow_consumers":null,"connections_truncated":false}`

func engineHub(t *testing.T, body string) *int {
	t.Helper()
	isolate(t)
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/engine" || r.Method != http.MethodGet || r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		calls++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return &calls
}

func TestNatsStatusShowsLinksLagJetStreamAndAccounts(t *testing.T) {
	calls := engineHub(t, engineAll)
	r := run(t, "", false, "nats", "status")
	if r.code != 0 || *calls != 1 {
		t.Fatalf("nats status %+v (calls %d)", r, *calls)
	}
	for _, want := range []string{
		"NATS monitor: up (health ok)",
		"JetStream: ready, 64.0 MiB of 256.0 MiB used (25.0%)",
		"Leaf links: 1 up, 1 down",
		"aaaa1111", "1.2ms", "40", "47", "2s ago",
		"bbbb2222", "DOWN",
		"NODE_aaaa1111", "ONEMIND",
		"Slow consumers: 1 (clients 1, routes 0, gateways 0, leaf links 0)",
	} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
}

func TestNatsStatusJSONIsTheGatewayObject(t *testing.T) {
	engineHub(t, engineAll)
	r := run(t, "", false, "--json", "nats", "status")
	var got, want map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &got) != nil || json.Unmarshal([]byte(engineAll), &want) != nil {
		t.Fatalf("nats status --json %+v", r)
	}
	if g, _ := json.Marshal(got); string(g) != func() string { w, _ := json.Marshal(want); return string(w) }() {
		t.Fatalf("--json changed the object:\n%s", r.out)
	}
}

func TestNatsStatusSummaryAndRefusedJetStream(t *testing.T) {
	engineHub(t, engineSummary)
	r := run(t, "", false, "nats", "status")
	if r.code != 0 || !strings.Contains(r.out, "JetStream: refused") || !strings.Contains(r.out, "without a cap") ||
		!strings.Contains(r.out, "detail is for the owner") || strings.Contains(r.out, "NODE\t") {
		t.Fatalf("summary %+v", r)
	}
}

func TestNatsStatusNeedsALoginAndASubcommand(t *testing.T) {
	engineHub(t, engineAll)
	t.Setenv("ONEMIND_TOKEN", "wrong")
	if r := run(t, "", false, "nats", "status"); r.code == 0 {
		t.Fatalf("nats status without a valid token succeeded: %+v", r)
	}
	if r := run(t, "", false, "nats"); r.code != ExitUsage {
		t.Fatalf("bare nats: %+v", r)
	}
}
