// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The hub answer has the shape of GET /v1/system/services (core/onemind_core/hostservices.py).
const servicesBody = `{"available":true,"registry":"ok","at":"2026-11-21T12:00:00Z","unknown":1,"dropped":0,"services":[
{"unit":"onemind-gateway.service","known":true,"name":"Gateway","description":"The front door every client talks to.",
 "docs":"docs/leap/core/PLUMBING.md","restartable":true,"risk":"medium","depends_on":["onemind-nats.service"],"installed":true,
 "load_state":"loaded","active_state":"active","sub_state":"running","memory_bytes":104857600,"version":"0.2.0"},
{"unit":"onemind-jetson-data.service","known":true,"name":"Jetson data disk","description":"NVIDIA Jetson only: prepares the data partition.",
 "docs":"docs/HARDWARE.md","restartable":false,"risk":"high","depends_on":[],"installed":false,"load_state":"not-found",
 "active_state":"inactive","sub_state":"dead","memory_bytes":null,"version":null},
{"unit":"onemind-mystery.service","known":false,"name":"onemind-mystery.service","description":"","docs":null,"restartable":false,
 "risk":"unknown","depends_on":[],"installed":true,"load_state":"loaded","active_state":"active","sub_state":"running",
 "memory_bytes":4096,"version":null}]}`

func servicesHub(t *testing.T, body string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/system/services" || r.Method != http.MethodGet || r.Header.Get("Authorization") != "Bearer "+ownerTok {
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

func TestServicesList(t *testing.T) {
	servicesHub(t, servicesBody)
	r := run(t, "", false, "services", "list")
	if r.code != 0 {
		t.Fatalf("services list %+v", r)
	}
	for _, want := range []string{"onemind-gateway.service", "Gateway", "active (running)", "100.0 MB", "medium", "yes",
		"Jetson data disk", "not installed", "(unknown: no service card)", "unknown"} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
	if !strings.Contains(r.errOut, "1 unit(s) run without a service card") {
		t.Fatalf("an unknown unit is not flagged: %+v", r)
	}
}

func TestServicesListJSONAndAnUnreachableHost(t *testing.T) {
	servicesHub(t, servicesBody)
	if r := run(t, "", false, "--json", "services", "list"); r.code != 0 || !strings.Contains(r.out, `"unit": "onemind-mystery.service"`) {
		t.Fatalf("services list --json %+v", r)
	}
	servicesHub(t, `{"available":false,"reason":"host_service_unreachable","message":"the host service is not reachable","services":[]}`)
	if r := run(t, "", false, "services", "list"); r.code != ExitUnreachable || !strings.Contains(r.errOut, "not reachable") {
		t.Fatalf("an unreachable host service must not look like an empty list: %+v", r)
	}
}

func TestServicesListNeedsALogin(t *testing.T) {
	servicesHub(t, servicesBody)
	t.Setenv("ONEMIND_TOKEN", "wrong")
	if r := run(t, "", false, "services", "list"); r.code == 0 {
		t.Fatalf("services list without a valid token succeeded: %+v", r)
	}
}
