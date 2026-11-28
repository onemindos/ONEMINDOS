// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// networkHub answers like core/onemind_core/routers/network.py: a change is filed as an action awaiting
// approval, confirm keeps a pending one, 422 for an address no network can use.
func networkHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.Path+" "+string(body))
		switch {
		case r.Method == http.MethodPut && r.URL.Path == "/v1/network/eth0":
			var b map[string]any
			_ = json.Unmarshal(body, &b)
			// NetworkConfigBody.dns is list[str] with a default: a missing key is fine, null is a 422 (pydantic).
			if v, ok := b["dns"]; ok && v == nil {
				jsonOut(w, 422, map[string]string{"error": "invalid_request", "message": "dns: Input should be a valid list"})
				return
			}
			if b["mode"] == "static" && b["gateway"] == "198.51.100.1" {
				jsonOut(w, 422, map[string]string{"error": "conflict", "reason": "invalid_gateway", "message": "The gateway must be another host inside 192.0.2.0/24."})
				return
			}
			jsonOut(w, 202, map[string]any{"id": "act-9", "type": "network.configure", "state": "awaiting_approval"})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/network/eth0/confirm":
			jsonOut(w, 200, map[string]any{"confirmed": true, "interface": "eth0"})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/network/eth1/confirm":
			jsonOut(w, 409, map[string]string{"error": "conflict", "reason": "no_pending_change", "message": "no change to eth1 is waiting for confirmation"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such interface"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func lastBody(t *testing.T, got []string) map[string]any {
	t.Helper()
	line := got[len(got)-1]
	var b map[string]any
	if err := json.Unmarshal([]byte(line[strings.Index(line, "{"):]), &b); err != nil {
		t.Fatalf("body of %q: %v", line, err)
	}
	return b
}

func TestNetworkSetFilesTheRequestAndNeverApproves(t *testing.T) {
	var got []string
	networkHub(t, &got)
	r := run(t, "", false, "network", "set", "eth0", "--address", "192.0.2.50/24", "--gateway", "192.0.2.1",
		"--dns", "192.0.2.53,192.0.2.54", "--rollback-seconds", "45", "--reason", "fixed address for the printer")
	if r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") || !strings.Contains(r.out, "passkey") ||
		!strings.Contains(r.out, "onemind network confirm eth0 act-9 --verified-reachable") || !strings.Contains(r.out, "192.0.2.50/24") || !strings.Contains(r.out, "45 seconds") {
		t.Fatalf("network set %+v", r)
	}
	b := lastBody(t, got)
	dns, _ := b["dns"].([]any)
	if b["mode"] != "static" || b["address"] != "192.0.2.50/24" || b["gateway"] != "192.0.2.1" || len(dns) != 2 || dns[1] != "192.0.2.54" ||
		b["rollback_seconds"] != float64(45) || b["reason"] != "fixed address for the printer" || b["idempotency_key"] == "" {
		t.Fatalf("request %v", b)
	}
	for _, g := range got {
		if strings.Contains(g, "/approve") {
			t.Fatalf("the CLI never approves: %v", got)
		}
	}
}

// Review of #1156: without --dns the body must not carry "dns": null, which the gateway refuses.
func TestNetworkSetWithoutDNSLeavesTheKeyOut(t *testing.T) {
	var got []string
	networkHub(t, &got)
	r := run(t, "", false, "network", "set", "eth0", "--address", "192.0.2.50/24", "--gateway", "192.0.2.1")
	if r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") {
		t.Fatalf("network set without --dns %+v", r)
	}
	line := got[len(got)-1]
	if strings.Contains(line, "null") {
		t.Fatalf("the body carries a null: %s", line)
	}
	if _, ok := lastBody(t, got)["dns"]; ok {
		t.Fatalf("no --dns, no dns key: %s", line)
	}
}

func TestNetworkDHCPSendsNoAddress(t *testing.T) {
	var got []string
	networkHub(t, &got)
	r := run(t, "", false, "network", "dhcp", "eth0")
	if r.code != 0 || !strings.Contains(r.out, "the address the router gives it") {
		t.Fatalf("network dhcp %+v", r)
	}
	b := lastBody(t, got)
	if b["mode"] != "dhcp" || b["address"] != nil || b["gateway"] != nil || b["rollback_seconds"] != float64(120) {
		t.Fatalf("request %v", b)
	}
	r = run(t, "", false, "--json", "network", "dhcp", "eth0")
	var act map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &act) != nil || act["id"] != "act-9" {
		t.Fatalf("--json prints the action: %+v", r)
	}
	if r := run(t, "", false, "-q", "network", "dhcp", "eth0"); r.code != 0 || strings.TrimSpace(r.out) != "act-9" {
		t.Fatalf("-q prints the id only: %+v", r)
	}
}

func TestNetworkSetNeedsAnAddressAndGateway(t *testing.T) {
	var got []string
	networkHub(t, &got)
	if r := run(t, "", false, "network", "set", "eth0"); r.code != ExitUsage || !strings.Contains(r.errOut, "network dhcp") {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "network", "set", "eth0", "--address", "192.0.2.50/24"); r.code != ExitUsage {
		t.Fatalf("%+v", r)
	}
	if len(got) != 0 {
		t.Fatalf("nothing is sent for a usage error: %v", got)
	}
}

func TestNetworkRefusalsReachThePersonWordForWord(t *testing.T) {
	var got []string
	networkHub(t, &got)
	r := run(t, "", false, "network", "set", "eth0", "--address", "192.0.2.50/24", "--gateway", "198.51.100.1")
	if r.code == 0 || !strings.Contains(r.errOut, "The gateway must be another host inside 192.0.2.0/24.") {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "network", "dhcp", "eth9"); r.code != ExitNotFound {
		t.Fatalf("an unknown interface: %+v", r)
	}
}

func TestNetworkConfirm(t *testing.T) {
	var got []string
	networkHub(t, &got)
	r := run(t, "", false, "network", "confirm", "eth0", "act-9", "--verified-reachable")
	if r.code != 0 || !strings.Contains(r.out, "Confirmed") || !strings.HasPrefix(got[0], "POST /v1/network/eth0/confirm ") {
		t.Fatalf("%+v %v", r, got)
	}
	if b := lastBody(t, got); b["action_id"] != "act-9" || b["verified_reachable"] != true {
		t.Fatalf("wrong action or reachability attestation: %v", got)
	}
	if r := run(t, "", false, "--json", "network", "confirm", "eth0", "act-9", "--verified-reachable"); r.code != 0 || !strings.Contains(r.out, `"confirmed": true`) && !strings.Contains(r.out, `"confirmed":true`) {
		t.Fatalf("--json: %+v", r)
	}
	if r := run(t, "", false, "network", "confirm", "eth1", "act-9", "--verified-reachable"); r.code != ExitConflict || !strings.Contains(r.errOut, "waiting for confirmation") {
		t.Fatalf("nothing pending: %+v", r)
	}
}

func TestNetworkConfirmRequiresReachabilityAttestation(t *testing.T) {
	var got []string
	networkHub(t, &got)
	r := run(t, "", false, "network", "confirm", "eth0", "act-9")
	if r.code != ExitUsage || !strings.Contains(r.errOut, "--verified-reachable") || len(got) != 0 {
		t.Fatalf("no confirmation may be sent without verifying reachability: %+v %v", r, got)
	}
}

// release/next added `network show` in another group; one "network" command must carry all four.
func TestNetworkGroupHasShowAndTheChanges(t *testing.T) {
	isolate(t)
	r := run(t, "", false, "network", "--help")
	for _, sub := range []string{"show", "set", "dhcp", "confirm"} {
		if !strings.Contains(r.out, "  "+sub+" ") {
			t.Fatalf("onemind network lacks %s:\n%s", sub, r.out)
		}
	}
}
