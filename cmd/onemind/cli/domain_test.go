// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

// A gateway with the two routes `onemind domain` uses (core/onemind_core/routers/domains.py): the answers have
// the real shape, and the test records each call so it can say what the CLI sent.
type domainHub struct {
	mu      sync.Mutex
	enabled bool
	added   []string
}

func startDomainHub(t *testing.T, enabled bool) *domainHub {
	t.Helper()
	isolate(t)
	h := &domainHub{enabled: enabled}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.mu.Lock()
		defer h.mu.Unlock()
		if r.URL.Path != "/v1/domains" || r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch r.Method {
		case http.MethodGet:
			jsonOut(w, 200, map[string]any{
				"enabled": h.enabled, "acme": map[string]any{"account_thumbprint": nil, "issuance": "not_available_yet"},
				"domains": []any{
					map[string]any{"domain": "example.org", "verified": true, "verified_at": "2026-11-25T01:00:00Z",
						"proof": map[string]string{"type": "TXT", "name": "_onemind-challenge.example.org", "value": "tok1"},
						"hosts": []any{map[string]any{"hostname": "ntfy.example.org", "app_id": "ntfy", "state": "approved", "public": false}}},
					map[string]any{"domain": "home.example.net", "verified": false, "verified_at": nil,
						"proof": map[string]string{"type": "TXT", "name": "_onemind-challenge.home.example.net", "value": "tok2"}, "hosts": []any{}},
				},
			})
		case http.MethodPost:
			if !h.enabled {
				jsonOut(w, 409, map[string]string{"error": "conflict", "reason": "domains_disabled", "message": "bring-your-own-domain is off; set ONEMIND_DOMAINS_ENABLED=1 to turn it on"})
				return
			}
			b, _ := io.ReadAll(r.Body)
			var in struct{ Domain string }
			_ = json.Unmarshal(b, &in)
			h.added = append(h.added, in.Domain)
			jsonOut(w, 201, map[string]any{"domain": strings.ToLower(in.Domain), "verified": false, "verified_at": nil,
				"proof": map[string]string{"type": "TXT", "name": "_onemind-challenge." + strings.ToLower(in.Domain), "value": "proof-abc"}, "hosts": []any{}})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return h
}

func TestDomainList(t *testing.T) {
	startDomainHub(t, true)
	r := run(t, "", false, "domain", "list")
	if r.code != 0 {
		t.Fatalf("domain list %+v", r)
	}
	for _, want := range []string{"example.org", "verified", "ntfy.example.org (approved)", "home.example.net", "not verified"} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
	if r.errOut != "" {
		t.Fatalf("an enabled box prints no warning: %q", r.errOut)
	}
}

func TestDomainListJSONAndWhenOff(t *testing.T) {
	startDomainHub(t, false)
	r := run(t, "", false, "--json", "domain", "list")
	var got struct {
		Enabled bool
		Domains []struct{ Domain string }
	}
	if r.code != 0 || json.Unmarshal([]byte(r.out), &got) != nil || got.Enabled || len(got.Domains) != 2 {
		t.Fatalf("domain list --json %+v", r)
	}
	r = run(t, "", false, "domain", "list")
	if r.code != 0 || !strings.Contains(r.errOut, "your own domain is off on this box") {
		t.Fatalf("a box with the feature off must say so: %+v", r)
	}
}

func TestDomainAddPrintsTheProofRecord(t *testing.T) {
	h := startDomainHub(t, true)
	r := run(t, "", false, "domain", "add", "Home.Example.org")
	if r.code != 0 || len(h.added) != 1 || h.added[0] != "Home.Example.org" {
		t.Fatalf("domain add %+v sent %v", r, h.added)
	}
	for _, want := range []string{"home.example.org added, not verified yet", "_onemind-challenge.home.example.org", "proof-abc"} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
	if j := run(t, "", false, "--json", "domain", "add", "b.example.org"); j.code != 0 || !strings.Contains(j.out, `"value": "proof-abc"`) {
		t.Fatalf("domain add --json %+v", j)
	}
}

func TestDomainAddRefusedWhileTheFeatureIsOff(t *testing.T) {
	startDomainHub(t, false)
	r := run(t, "", false, "domain", "add", "example.org")
	if r.code == 0 || !strings.Contains(r.errOut, "ONEMIND_DOMAINS_ENABLED") {
		t.Fatalf("a refusal must reach the person with the reason: %+v", r)
	}
	if r := run(t, "", false, "domain", "add"); r.code == 0 || !strings.Contains(r.errOut, "accepts 1 arg") {
		t.Fatalf("add without a domain is refused: %+v", r)
	}
}

// A gateway for `onemind domain host`: it records each call and answers like routers/domains.py.
func startDomainHostHub(t *testing.T) *[]string {
	t.Helper()
	isolate(t)
	var calls []string
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		b, _ := io.ReadAll(r.Body)
		calls = append(calls, r.Method+" "+r.URL.Path+" "+string(b))
		host := map[string]any{"hostname": "ntfy.example.org", "app_id": "ntfy", "state": "requested", "requested_by": "owner", "approved_by": nil, "updated_at": nil, "public": false}
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/v1/domains/example.org/hosts":
			jsonOut(w, 201, host)
		case r.Method == http.MethodPost && r.URL.Path == "/v1/domains/hosts/ntfy.example.org/approve":
			host["state"], host["approved_by"] = "approved", "owner"
			jsonOut(w, 200, host)
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/domains/hosts/ntfy.example.org":
			w.WriteHeader(204)
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return &calls
}

func TestDomainHostRequestApproveRemove(t *testing.T) {
	calls := startDomainHostHub(t)
	r := run(t, "", false, "domain", "host", "request", "example.org", "ntfy")
	if r.code != 0 || !strings.Contains(r.out, "Asked for ntfy.example.org") || !strings.Contains(r.out, "--confirm ntfy.example.org") {
		t.Fatalf("request %+v", r)
	}
	r = run(t, "", false, "domain", "host", "approve", "ntfy.example.org", "--confirm", "NTFY.example.org")
	if r.code != 0 || !strings.Contains(r.out, "Approved ntfy.example.org") || !strings.Contains(r.out, "nothing is served") {
		t.Fatalf("approve %+v", r)
	}
	if r = run(t, "", false, "domain", "host", "remove", "ntfy.example.org"); r.code == 0 || !strings.Contains(r.errOut, "--yes") {
		t.Fatalf("remove without --yes must be refused before any call: %+v", r)
	}
	r = run(t, "", false, "domain", "host", "remove", "ntfy.example.org", "--yes")
	if r.code != 0 || !strings.Contains(r.out, "Removed ntfy.example.org") {
		t.Fatalf("remove %+v", r)
	}
	want := []string{
		`POST /v1/domains/example.org/hosts {"app_id":"ntfy"}`,
		`POST /v1/domains/hosts/ntfy.example.org/approve {"confirm":"NTFY.example.org"}`,
		`DELETE /v1/domains/hosts/ntfy.example.org `,
	}
	if strings.Join(*calls, "\n") != strings.Join(want, "\n") {
		t.Fatalf("calls %q", *calls)
	}
}

func TestDomainHostApproveNeedsTheNameTypedInFull(t *testing.T) {
	calls := startDomainHostHub(t)
	for _, args := range [][]string{
		{"domain", "host", "approve", "ntfy.example.org"},
		{"domain", "host", "approve", "ntfy.example.org", "--confirm", "ntfy"},
	} {
		if r := run(t, "", false, args...); r.code == 0 {
			t.Fatalf("%v must be refused: %+v", args, r)
		}
	}
	if len(*calls) != 0 {
		t.Fatalf("nothing may reach the gateway without the confirmation: %q", *calls)
	}
}
