// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The hub answer has the shape of GET /v1/network/firewall (core/onemind_core/hostfw.py).
const firewallBody = `{"available":true,"at":"2026-11-25T12:00:00Z","exposure":"lan_and_mesh_only","default_action":"drop",
"headline":"Blocked by default. Only your home network (LAN), your mesh and this box itself can reach anything. Nothing is open to the internet.",
"open_to_anywhere":[],"editable":false,"dropped":1,"sets":[],"other_tables":[],"chains":[],
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

func TestFirewallHasNoWriteCommandYet(t *testing.T) {
	firewallHub(t, firewallBody)
	for _, sub := range []string{"allow", "open", "close", "add", "delete"} {
		if r := run(t, "", false, "firewall", sub); r.code == 0 {
			t.Fatalf("firewall %s must not exist until part 2: %+v", sub, r)
		}
	}
}
