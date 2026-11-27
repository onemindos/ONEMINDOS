// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestFitAppReadsMachineVerdict(t *testing.T) {
	isolate(t)
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/v1/apps/simulator/placement" {
			t.Errorf("unexpected gateway call: %s %s", r.Method, r.URL.Path)
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"app_id":"simulator","nodes":[],"fit":{"nodes":[{"node_id":"hub","verdict":"not-checked","reasons":["VRAM missing"]},{"node_id":"gpu","verdict":"yes","reasons":[]}],"passing_nodes":["gpu"]}}`)
	}))
	defer hub.Close()
	t.Setenv("ONEMIND_HUB", hub.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	res := run(t, "", false, "fit", "app", "simulator", "--node", "hub")
	if res.code != 0 || !strings.Contains(res.out, "not-checked") || !strings.Contains(res.out, "VRAM missing") {
		t.Fatalf("fit result: %+v", res)
	}
	res = run(t, "", false, "fit", "app", "simulator", "--node", "missing")
	if res.code != ExitNotFound {
		t.Fatalf("missing machine: %+v", res)
	}
}
