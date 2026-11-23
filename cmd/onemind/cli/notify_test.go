// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The phone number is from the +1 555 01xx range kept for fiction.
const (
	cliPhone  = "+15550100123"
	cliSecret = "sk_cli_test_0123456789"
)

// notifyHub answers the notifications routes the CLI calls, with the shapes of
// core/onemind_core/routers/notifications.py, and records the POST bodies.
func notifyHub(t *testing.T, channels string, testReply map[string]any) *[]map[string]any {
	t.Helper()
	isolate(t)
	posts := &[]map[string]any{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/notifications/channels":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(channels))
		case r.Method == http.MethodPost && r.URL.Path == "/v1/notifications/channels":
			var body map[string]any
			_ = json.NewDecoder(r.Body).Decode(&body)
			*posts = append(*posts, body)
			cfg := map[string]any{"daily_cap": 20} // the gateway's answer, not the recorded request
			for k, v := range body["config"].(map[string]any) {
				if k != "daily_cap" {
					cfg[k] = v
				}
			}
			jsonOut(w, 201, map[string]any{"id": "chn_01", "kind": "sms", "label": body["label"], "content_level": "title",
				"config": cfg, "verified": false, "state": "ok", "secret": "provided"})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/notifications/channels/chn_01/test":
			*posts = append(*posts, map[string]any{"test": "chn_01"})
			jsonOut(w, 200, testReply)
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such resource"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return posts
}

const oneSms = `[{"id":"chn_01","kind":"sms","label":"phone","content_level":"title","config":{"to":"` + cliPhone +
	`","daily_cap":20},"verified":true,"state":"ok","secret":"provided"},
{"id":"chn_02","kind":"webhook","label":"hook","content_level":"full","config":{"url":"https://hook.example/x"},"verified":false,"state":"ok","secret":null}]`

func TestNotifyChannelAddSmsSendsTheSecretOnceAndNeverPrintsIt(t *testing.T) {
	posts := notifyHub(t, oneSms, nil)
	r := run(t, cliSecret+"\n", false, "notify", "channel", "add", "sms", "--to", cliPhone,
		"--provider-url", "https://sms.example/v1/messages", "--secret-stdin", "--daily-cap", "10",
		"--format", "form", "--auth", "basic", "--username", "acct", "--field", "to=To,text=Body")
	if r.code != 0 {
		t.Fatalf("add sms %+v", r)
	}
	if strings.Contains(r.out+r.errOut, cliSecret) || !strings.Contains(r.out, "added chn_01") || !strings.Contains(r.out, "20/day") {
		t.Fatalf("output %+v", r)
	}
	if len(*posts) != 1 {
		t.Fatalf("posts %v", *posts)
	}
	body := (*posts)[0]
	cfg := body["config"].(map[string]any)
	if body["kind"] != "sms" || body["secret"] != cliSecret || cfg["to"] != cliPhone || cfg["daily_cap"] != float64(10) ||
		cfg["format"] != "form" || cfg["username"] != "acct" || cfg["fields"].(map[string]any)["text"] != "Body" {
		t.Fatalf("body %v", body)
	}
	if _, ok := cfg["secret"]; ok {
		t.Fatal("the secret went into config")
	}
}

func TestNotifyChannelAddSmsNeedsATerminalOrStdinForTheSecret(t *testing.T) {
	posts := notifyHub(t, oneSms, nil)
	r := run(t, "", false, "notify", "channel", "add", "sms", "--to", cliPhone, "--provider-url", "https://sms.example/")
	if r.code != ExitUsage || !strings.Contains(r.errOut, "--secret-stdin") || len(*posts) != 0 {
		t.Fatalf("no terminal %+v", r)
	}
	if r := run(t, "", false, "notify", "channel", "add", "sms", "--to", cliPhone, "--provider-url", "https://sms.example/",
		"--auth", "none"); r.code != 0 || len(*posts) != 1 || (*posts)[0]["secret"] != nil {
		t.Fatalf("auth none %+v %v", r, *posts)
	}
	if r := run(t, "", false, "notify", "channel", "add", "email"); r.code != ExitUsage {
		t.Fatalf("kind email %+v", r)
	}
}

func TestNotifyTestSmsShowsTheReceiptOrTheError(t *testing.T) {
	posts := notifyHub(t, oneSms, map[string]any{"delivered": true, "latency_ms": 42,
		"receipt": map[string]any{"status": 200, "provider_id": "msg_0001"}})
	r := run(t, "", false, "notify", "test", "sms")
	if r.code != 0 || !strings.Contains(r.out, "msg_0001") || !strings.Contains(r.out, "200") || len(*posts) != 1 {
		t.Fatalf("test sms %+v", r)
	}
	notifyHub(t, oneSms, map[string]any{"delivered": false, "latency_ms": 3, "error": "daily cap reached (20 per day)"})
	r = run(t, "", false, "notify", "test", "sms")
	if r.code != ExitError || !strings.Contains(r.errOut, "daily cap reached") {
		t.Fatalf("capped %+v", r)
	}
	notifyHub(t, `[]`, nil)
	if r := run(t, "", false, "notify", "test", "sms"); r.code != ExitNotFound {
		t.Fatalf("no channel %+v", r)
	}
}

func TestNotifyChannelListShowsTheCap(t *testing.T) {
	notifyHub(t, oneSms, nil)
	r := run(t, "", false, "notify", "channel", "list")
	if r.code != 0 || !strings.Contains(r.out, "chn_01") || !strings.Contains(r.out, "20/day") || !strings.Contains(r.out, "webhook") {
		t.Fatalf("list %+v", r)
	}
}
