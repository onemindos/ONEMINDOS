// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestFabricPolicyPrintsTheSnapshot(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/fabric/policy" || r.Header.Get("Authorization") != "Bearer tok" {
			http.Error(w, "no", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"schema":"onemind.policy/v1","epoch":3,"stop":{"motion_lockout":true,"agents":false},` +
			`"revoked_kids":[],"allowed_kinds":null,"published":{"n2":2,"n1":3},"error":null}`))
	}))
	defer srv.Close()
	var out bytes.Buffer
	if err := fabricPolicy([]string{"--hub", srv.URL, "--token", "tok"}, &out); err != nil {
		t.Fatal(err)
	}
	want := "Epoch 3. Motion lockout: true. Agents stopped: false. Revoked job keys: 0.\n  node n1: current\n  node n2: has epoch 2\n"
	if out.String() != want {
		t.Fatalf("got:\n%s", out.String())
	}
	out.Reset()
	if err := fabricPolicy([]string{"--hub", srv.URL, "--token", "tok", "--json"}, &out); err != nil || !strings.Contains(out.String(), `"epoch": 3`) {
		t.Fatalf("json: %v %s", err, out.String())
	}
}
