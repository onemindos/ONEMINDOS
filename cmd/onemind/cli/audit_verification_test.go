// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

func TestAuditVerifyCrossCheckFailureOutput(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("..", "..", "..", "sdk", "testdata", "audit", "good.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	chain := onemind.VerifyChain(strings.NewReader(string(raw)))
	if !chain.OK || chain.Head == nil {
		t.Fatalf("invalid test chain: %+v", chain)
	}
	var records []json.RawMessage
	for _, line := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
		records = append(records, json.RawMessage(line))
	}
	for _, tc := range []struct {
		name   string
		server map[string]any
		reason string
	}{
		{"server-tamper", map[string]any{"ok": false, "reason": "hash mismatch", "first_bad_seq": 2}, "gateway's own check failed"},
		{"conflicting-head", map[string]any{"ok": true, "head": map[string]any{"seq": chain.Head.Seq, "hash": strings.Repeat("f", 64)}}, "head hash differs"},
	} {
		for _, asJSON := range []bool{false, true} {
			t.Run(tc.name+map[bool]string{false: "/text", true: "/json"}[asJSON], func(t *testing.T) {
				isolate(t)
				srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					switch r.URL.Path {
					case "/v1/audit/events":
						jsonOut(w, http.StatusOK, records)
					case "/v1/audit/verify":
						jsonOut(w, http.StatusOK, tc.server)
					default:
						http.NotFound(w, r)
					}
				}))
				t.Cleanup(srv.Close)
				t.Setenv("ONEMIND_HUB", srv.URL)
				t.Setenv("ONEMIND_TOKEN", ownerTok)
				args := []string{"audit", "verify"}
				if asJSON {
					args = append(args, "--json")
				}
				r := run(t, "", false, args...)
				if r.code != ExitVerifyFailed {
					t.Fatalf("expected exit 8: %+v", r)
				}
				if asJSON {
					var report struct {
						Result onemind.ChainResult `json:"result"`
					}
					if err := json.Unmarshal([]byte(r.out), &report); err != nil {
						t.Fatal(err)
					}
					if report.Result.OK || !strings.Contains(report.Result.Reason, tc.reason) || report.Result.FirstBadSeq != nil {
						t.Fatalf("cross-check failure must not claim success or invent a bad seq: %s", r.out)
					}
				} else if strings.Contains(r.out, "chain ok") || !strings.Contains(r.out, "FAIL:") || !strings.Contains(r.out, tc.reason) {
					t.Fatalf("cross-check failure must not print success: %+v", r)
				}
			})
		}
	}
}
