// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The hub answer has the shape of GET /v1/network/firewall (core/onemind_core/hostfw.py).
const firewallBody = `{"available":true,"at":"2026-11-25T12:00:00Z","exposure":"lan_and_mesh_only","default_action":"drop",
"headline":"Blocked by default. Only your home network (LAN), your mesh and this box itself can reach anything. Nothing is open to the internet.",
"open_to_anywhere":[],"editable":false,"dropped":1,"truncated":2,"sets":[],"other_tables":[],"chains":[],
"rules":[
{"chain":"input","position":1,"action":"accept","kind":"state","audience":"any_network","ports":[],"understood":true,"summary":"Replies to connections this box started are always allowed in."},
{"chain":"lan","position":1,"action":"accept","kind":"open_port","audience":"lan","proto":"tcp","ports":["443"],"understood":true,"summary":"Devices on your home network (LAN) can reach TCP 443 (the OneMind dashboard and gateway, HTTPS).\u001b[31m"}]}`

func firewallHub(t *testing.T, body string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/network/firewall" || r.Method != http.MethodGet || r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestFirewallShowPrintsTheAnswerFirstThenEachRule(t *testing.T) {
	firewallHub(t, firewallBody)
	r := run(t, "", false, "firewall", "show")
	if r.code != 0 {
		t.Fatalf("firewall show %+v", r)
	}
	if !strings.HasPrefix(r.out, "Blocked by default.") || !strings.Contains(r.out, "Nothing is open to the internet.") {
		t.Fatalf("the headline comes first:\n%s", r.out)
	}
	for _, want := range []string{"CHAIN", "WHAT IT DOES", "ACCEPT", "LAN", "ANY ADDRESS", "TCP 443 (the OneMind dashboard and gateway, HTTPS)"} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
	if strings.Contains(r.out, "\x1b") {
		t.Fatalf("control characters reached the terminal:\n%q", r.out)
	}
	if !strings.Contains(r.errOut, "1 entry was left out") {
		t.Fatalf("a dropped entry is said: %q", r.errOut)
	}
	if !strings.Contains(r.errOut, "2 parts of the rules left out for size") {
		t.Fatalf("a truncated view is said: %q", r.errOut)
	}
}

func TestFirewallShowJSON(t *testing.T) {
	firewallHub(t, firewallBody)
	if r := run(t, "", false, "--json", "firewall", "show"); r.code != 0 || !strings.Contains(r.out, `"exposure": "lan_and_mesh_only"`) {
		t.Fatalf("firewall show --json %+v", r)
	}
}

func TestFirewallShowAnUnreachableHostIsNotAnEmptyFirewall(t *testing.T) {
	firewallHub(t, `{"available":false,"reason":"host_service_unreachable","message":"the host service is not reachable"}`)
	if r := run(t, "", false, "firewall", "show"); r.code != ExitUnreachable || !strings.Contains(r.errOut, "not reachable") || strings.Contains(r.out, "Blocked") {
		t.Fatalf("an unknown firewall must not look safe: %+v", r)
	}
}

func TestFirewallShowNeedsALogin(t *testing.T) {
	firewallHub(t, firewallBody)
	t.Setenv("ONEMIND_TOKEN", "wrong")
	if r := run(t, "", false, "firewall", "show"); r.code == 0 {
		t.Fatalf("firewall show without a valid token succeeded: %+v", r)
	}
}

func TestFirewallNeverGrowsACommandThatOpensWithoutAnApproval(t *testing.T) {
	firewallHub(t, firewallBody)
	for _, sub := range []string{"open", "close", "add", "delete", "approve"} {
		if r := run(t, "", false, "firewall", sub); r.code == 0 {
			t.Fatalf("firewall %s must not exist: %+v", sub, r)
		}
	}
}

// writeHub records what the CLI sends and answers like the gateway (core/onemind_core/routers/network.py).
func writeHub(t *testing.T, got *[]string, bodies *[]string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		*got, *bodies = append(*got, r.Method+" "+r.URL.Path), append(*bodies, string(raw))
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch {
		case r.Method == "POST" && r.URL.Path == "/v1/network/firewall/allow":
			jsonOut(w, 202, map[string]any{"id": "act-123", "type": "firewall.allow", "state": "awaiting_approval"})
		case strings.HasSuffix(r.URL.Path, "/gone/confirm"):
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "there is no such allow rule (a rule that was not confirmed in time is already gone)"})
		case r.Method == "POST":
			jsonOut(w, 200, map[string]any{"id": "act-123", "state": "confirmed"})
		default:
			jsonOut(w, 200, map[string]any{"id": "act-123", "removed": true})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestFirewallAllowFilesARequestAndSaysHowToKeepIt(t *testing.T) {
	var got, bodies []string
	writeHub(t, &got, &bodies)
	r := run(t, "", false, "firewall", "allow", "tcp/8123", "--scope", "mesh", "--reason", "printer app")
	if r.code != 0 || len(got) != 1 || got[0] != "POST /v1/network/firewall/allow" {
		t.Fatalf("%+v %v", r, got)
	}
	for _, want := range []string{`"proto":"tcp"`, `"port":8123`, `"scope":"mesh"`, `"reason":"printer app"`} {
		if !strings.Contains(bodies[0], want) {
			t.Fatalf("missing %s in %s", want, bodies[0])
		}
	}
	for _, want := range []string{"Approval id: act-123", "passkey", "onemind firewall confirm act-123", "closes again by itself"} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
	if j := run(t, "", false, "--json", "firewall", "allow", "udp/5353"); j.code != 0 || !strings.Contains(j.out, `"state": "awaiting_approval"`) || !strings.Contains(bodies[len(bodies)-1], `"scope":"lan"`) {
		t.Fatalf("the default scope is lan: %+v %s", j, bodies[len(bodies)-1])
	}
	if q := run(t, "", false, "--quiet", "firewall", "allow", "tcp/80"); q.code != 0 || strings.TrimSpace(q.out) != "act-123" {
		t.Fatalf("--quiet prints the id only: %+v", q)
	}
}

func TestFirewallAllowRefusesTheInternetAndOddValuesBeforeAnythingIsSent(t *testing.T) {
	var got, bodies []string
	writeHub(t, &got, &bodies)
	for _, args := range [][]string{
		{"firewall", "allow", "tcp/8123", "--scope", "wan"}, {"firewall", "allow", "tcp/8123", "--scope", "any"},
		{"firewall", "allow", "tcp/8123", "--scope", ""}, {"firewall", "allow", "8123"}, {"firewall", "allow", "icmp/8"},
		{"firewall", "allow", "tcp/0"}, {"firewall", "allow", "tcp/65536"}, {"firewall", "allow", "tcp/x"},
	} {
		if r := run(t, "", false, args...); r.code != ExitUsage {
			t.Fatalf("%v should be a usage error: %+v", args, r)
		}
	}
	if len(got) != 0 {
		t.Fatalf("a refused request reached the hub: %v", got)
	}
}

func TestFirewallConfirmAndRemove(t *testing.T) {
	var got, bodies []string
	writeHub(t, &got, &bodies)
	if r := run(t, "", false, "firewall", "confirm", "act-123"); r.code != 0 || !strings.Contains(r.out, "confirmed") {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "firewall", "remove", "act-123"); r.code != 0 || !strings.Contains(r.out, "removed") {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "--json", "firewall", "remove", "act-123"); r.code != 0 || !strings.Contains(r.out, `"removed": true`) {
		t.Fatalf("%+v", r)
	}
	if got[0] != "POST /v1/network/firewall/allow/act-123/confirm" || got[1] != "DELETE /v1/network/firewall/allow/act-123" {
		t.Fatalf("%v", got)
	}
	if r := run(t, "", false, "firewall", "confirm", "gone"); r.code != ExitNotFound || !strings.Contains(r.errOut, "already gone") {
		t.Fatalf("a reverted rule says so: %+v", r)
	}
}

func TestFirewallShowListsTheAllowRulesWithTheirDeadline(t *testing.T) {
	body := strings.Replace(firewallBody, `"editable":false`, `"editable":true,"allow":{"supported":true,"ttl_seconds":300,"rules":[
{"id":"act-123","proto":"tcp","port":8123,"scope":"lan","state":"pending","expires_at":"2026-11-25T12:05:00Z","summary":"x"},
{"id":"act-9","proto":"udp","port":5353,"scope":"mesh","state":"confirmed","summary":"y"}]}`, 1)
	firewallHub(t, body)
	r := run(t, "", false, "firewall", "show")
	if r.code != 0 {
		t.Fatalf("%+v", r)
	}
	for _, want := range []string{"ALLOW RULE ID", "act-123", "tcp/8123", "LAN", "unless confirmed", "act-9", "udp/5353", "mesh", "confirmed"} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
}
