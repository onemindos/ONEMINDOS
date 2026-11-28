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

// serviceActionsHub answers like core/onemind_core/routers/services.py: redacted logs (plain or SSE), a
// restart request filed as an action awaiting approval, 403 not_restartable for the rescue console.
func serviceActionsHub(t *testing.T, got *[]string) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		body, _ := io.ReadAll(r.Body)
		*got = append(*got, r.Method+" "+r.URL.RequestURI()+" "+string(body))
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/system/services/onemind-gateway.service/logs":
			if r.URL.Query().Get("follow") == "true" {
				w.Header().Set("Content-Type", "text/event-stream")
				_, _ = io.WriteString(w, "data: one Authorization: Bearer [redacted]\n\ndata: two \x1b[31mred\n\nevent: end\ndata: stream closed\n\n")
				return
			}
			w.Header().Set("Content-Type", "text/plain")
			_, _ = io.WriteString(w, "one Authorization: Bearer [redacted]\ntwo\n")
		case r.Method == http.MethodPost && r.URL.Path == "/v1/system/services/onemind-gateway.service/restart":
			jsonOut(w, 202, map[string]any{"id": "act-7", "type": "service.restart", "state": "awaiting_approval",
				"params": map[string]string{"unit": "onemind-gateway.service"}})
		case r.URL.Path == "/v1/system/services/onemind-rescue.service/restart":
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "reason": "not_restartable", "message": "onemind-rescue.service is not restartable"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no service with that unit name"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestServicesLogs(t *testing.T) {
	var got []string
	serviceActionsHub(t, &got)
	r := run(t, "", false, "services", "logs", "onemind-gateway.service", "-n", "50")
	if r.code != 0 || r.out != "one Authorization: Bearer [redacted]\ntwo\n" {
		t.Fatalf("services logs %+v", r)
	}
	if !strings.Contains(got[0], "?tail=50 ") || strings.Contains(got[0], "follow") {
		t.Fatalf("asked %v", got)
	}
	r = run(t, "", false, "services", "logs", "-f", "onemind-gateway.service")
	if r.code != 0 || r.out != "one Authorization: Bearer [redacted]\ntwo red\n" || strings.Contains(r.out, "\x1b") {
		t.Fatalf("services logs -f prints the data lines, no control characters, and stops at the end event: %q", r.out)
	}
	if r := run(t, "", false, "services", "logs", "onemind-mystery.service"); r.code != ExitNotFound {
		t.Fatalf("an unknown unit: %+v", r)
	}
	if r := run(t, "", false, "services", "logs", "-n", "0", "onemind-gateway.service"); r.code != ExitUsage {
		t.Fatalf("--tail 0: %+v", r)
	}
}

func TestServicesRestartPrintsTheApprovalID(t *testing.T) {
	var got []string
	serviceActionsHub(t, &got)
	r := run(t, "", false, "services", "restart", "onemind-gateway.service", "--reason", "stuck")
	if r.code != 0 || !strings.Contains(r.out, "Approval id: act-7") || !strings.Contains(r.out, "passkey") {
		t.Fatalf("services restart %+v", r)
	}
	var body map[string]string
	if err := json.Unmarshal([]byte(got[0][strings.Index(got[0], "{"):]), &body); err != nil || body["reason"] != "stuck" || body["idempotency_key"] == "" {
		t.Fatalf("request %v: %v", got, err)
	}
	if r := run(t, "", false, "-q", "services", "restart", "onemind-gateway.service"); r.code != 0 || r.out != "act-7\n" {
		t.Fatalf("-q prints the id alone: %+v", r)
	}
	if r := run(t, "", false, "services", "restart", "onemind-rescue.service"); r.code != ExitPermissionDenied || !strings.Contains(r.errOut, "not restartable") {
		t.Fatalf("the rescue console is refused: %+v", r)
	}
	for _, g := range got {
		if strings.Contains(g, "/approve") {
			t.Fatalf("the CLI approved something: %s", g)
		}
	}
}

// TestLogsReadsTheSystemJournal: `onemind logs` sends the filters to GET /v1/system/journal, prints the hub's
// redacted lines without control characters, follows the SSE stream, and maps the hub's refusals to exit codes.
func TestLogsReadsTheSystemJournal(t *testing.T) {
	isolate(t)
	var got []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = append(got, r.URL.RequestURI())
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch {
		case r.URL.Path != "/v1/system/journal":
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		case r.URL.Query().Get("unit") == "nope.service":
			jsonOut(w, 422, map[string]string{"error": "conflict", "reason": "invalid_query", "message": "the host refused that unit"})
		case r.URL.Query().Get("follow") == "true":
			w.Header().Set("Content-Type", "text/event-stream")
			_, _ = io.WriteString(w, "data: kernel: up \x1b[31mred\n\ndata: sshd: [redacted]\n\nevent: end\ndata: stream closed\n\n")
		default:
			w.Header().Set("Content-Type", "text/plain")
			_, _ = io.WriteString(w, "kernel: hello\nsshd: Accepted from [ip]\n")
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	r := run(t, "", false, "logs", "--unit", "sshd.service", "--priority", "err", "--boot", "-1", "-n", "50")
	if r.code != 0 || r.out != "kernel: hello\nsshd: Accepted from [ip]\n" {
		t.Fatalf("logs %+v", r)
	}
	if got[0] != "/v1/system/journal?boot=-1&priority=err&tail=50&unit=sshd.service" {
		t.Fatalf("asked %v", got)
	}
	r = run(t, "", false, "logs", "-f")
	if r.code != 0 || r.out != "kernel: up red\nsshd: [redacted]\n" || strings.Contains(r.out, "\x1b") {
		t.Fatalf("logs -f: %q", r.out)
	}
	if !strings.Contains(got[len(got)-1], "follow=true") || !strings.Contains(got[len(got)-1], "boot=0") {
		t.Fatalf("follow asked %v", got)
	}
	if r := run(t, "", false, "logs", "--unit", "nope.service"); r.code == 0 || !strings.Contains(r.errOut, "logs: the host refused that unit") {
		t.Fatalf("a refused unit: %+v", r)
	}
	n := len(got)
	for _, args := range [][]string{{"logs", "-n", "0"}, {"logs", "-n", "2001"}, {"logs", "--boot", "1"}, {"logs", "--boot", "-51"}, {"logs", "-f", "--boot", "-1"}} {
		if r := run(t, "", false, args...); r.code != ExitUsage {
			t.Fatalf("%v: %+v", args, r)
		}
	}
	if len(got) != n {
		t.Fatalf("a usage error must not reach the hub: %v", got[n:])
	}
}
