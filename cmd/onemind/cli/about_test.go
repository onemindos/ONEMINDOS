// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The hub answer here has the shape of GET /v1/os/about. Even if a hostile or buggy hub put a serial
// or an address in an extra field, the support text prints only the allow-listed facts.
const aboutBody = `{"hub_node_id":"box0123456789","node_count":1,"nodes":[{"node_id":"box0123456789","hostname":"beelink",
"board":"x86_64-efi","status":"online","os_pretty":"Debian GNU/Linux 13 (trixie)","onemind_version":"0.1.1","booted_slot":"A",
"kernel":"6.12.48-amd64","cpu_model":"Intel(R) N100","cpus":4,"mem_total_mb":15800,"disk_total_gb":476.9,"disk_free_gb":400.0,
"uptime_s":93784,"serial":"SN-777","ip":"203.0.113.9"}]}`

func aboutHub(t *testing.T) string {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/os/about" || r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(aboutBody))
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return srv.URL
}

func TestAboutTable(t *testing.T) {
	aboutHub(t)
	r := run(t, "", false, "about")
	if r.code != 0 || !strings.Contains(r.out, "beelink") || !strings.Contains(r.out, "0.1.1") || !strings.Contains(r.out, "1d 2h") {
		t.Fatalf("about %+v", r)
	}
}

func TestAboutSupportLeavesOutSerialsAddressesAndIDs(t *testing.T) {
	aboutHub(t)
	r := run(t, "", false, "about", "--support")
	if r.code != 0 {
		t.Fatalf("about --support %+v", r)
	}
	for _, want := range []string{"Hostname: beelink", "OneMind: 0.1.1", "A/B slot: A", "Kernel: 6.12.48-amd64", "Memory: 15.4 GB", "Uptime: 1d 2h"} {
		if !strings.Contains(r.out, want) {
			t.Fatalf("missing %q in\n%s", want, r.out)
		}
	}
	for _, secret := range []string{"SN-777", "203.0.113.9", "box0123456789"} {
		if strings.Contains(r.out, secret) {
			t.Fatalf("%q leaked:\n%s", secret, r.out)
		}
	}
	if r := run(t, "", false, "about", "--support", "--include-node-id"); !strings.Contains(r.out, "Node ID: box0123456789") {
		t.Fatalf("node id not printed on request: %+v", r)
	}
}

func TestAboutNeedsALogin(t *testing.T) {
	aboutHub(t)
	t.Setenv("ONEMIND_TOKEN", "wrong")
	if r := run(t, "", false, "about"); r.code == 0 {
		t.Fatalf("about without a valid token succeeded: %+v", r)
	}
}
