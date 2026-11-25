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

// keyboardHub answers like core/onemind_core/routers/keyboard.py: the view, a request filed as an action awaiting
// approval, 404 for a layout the image does not offer, 409 when the host cannot be reached.
func keyboardHub(t *testing.T, view map[string]any, got *[]string) {
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
		case r.Method == http.MethodGet && r.URL.Path == "/v1/system/keyboard":
			jsonOut(w, 200, view)
		case r.Method == http.MethodPost && r.URL.Path == "/v1/system/keyboard":
			var req map[string]string
			_ = json.Unmarshal(body, &req)
			if req["layout"] == "zz" {
				jsonOut(w, 404, map[string]string{"error": "not_found", "message": "this image does not offer that keyboard layout"})
				return
			}
			jsonOut(w, 202, map[string]any{"id": "act-9", "type": "system.set_keymap", "state": "awaiting_approval", "params": req})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

var keyboardView = map[string]any{
	"available": true, "seeded": false,
	"current": map[string]string{"model": "pc105", "layout": "de", "variant": "nodeadkeys", "options": ""},
	"layouts": []map[string]any{
		{"id": "us", "name": "English (US)", "variants": []map[string]string{{"id": "dvorak", "name": "English (Dvorak)"}}},
		{"id": "de", "name": "German", "variants": []map[string]string{{"id": "nodeadkeys", "name": "German (no dead keys)"}}},
	},
}

func TestKeyboardShowPrintsTheChoiceAndListsLayouts(t *testing.T) {
	var got []string
	keyboardHub(t, keyboardView, &got)
	r := run(t, "", false, "keyboard", "show")
	if r.code != 0 || !strings.Contains(r.out, "Keyboard layout: de (nodeadkeys) - German (no dead keys)") {
		t.Fatalf("show %+v", r)
	}
	if r := run(t, "", false, "keyboard", "show", "-q"); r.code != 0 || r.out != "de (nodeadkeys)\n" {
		t.Fatalf("show -q %+v", r)
	}
	r = run(t, "", false, "keyboard", "show", "--layouts")
	if r.code != 0 || !strings.Contains(r.out, "LAYOUT") || !strings.Contains(r.out, "German") || !strings.Contains(r.out, "dvorak") {
		t.Fatalf("show --layouts %+v", r)
	}
	r = run(t, "", false, "keyboard", "show", "--json")
	var v map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &v) != nil || v["available"] != true {
		t.Fatalf("show --json prints the gateway's object: %+v", r)
	}
}

func TestKeyboardShowSaysSoWhenNothingIsChosenOrTheHostIsAway(t *testing.T) {
	var got []string
	seeded := map[string]any{"available": true, "seeded": true, "current": map[string]string{"model": "pc105", "layout": "us", "variant": "", "options": ""}}
	keyboardHub(t, seeded, &got)
	if r := run(t, "", false, "keyboard", "show"); r.code != 0 || !strings.Contains(r.out, "Nothing is chosen yet") {
		t.Fatalf("seeded %+v", r)
	}
	keyboardHub(t, map[string]any{"available": false, "reason": "host_service_unreachable", "message": "the host service is not reachable"}, &got)
	if r := run(t, "", false, "keyboard", "show"); r.code != ExitUnreachable {
		t.Fatalf("host away %+v", r)
	}
}

func TestKeyboardSetPrintsTheApprovalIDAndNeverApproves(t *testing.T) {
	var got []string
	keyboardHub(t, keyboardView, &got)
	r := run(t, "", false, "keyboard", "set", "de", "nodeadkeys", "--reason", "I type German")
	if r.code != 0 || !strings.Contains(r.out, "Approval id: act-9") || !strings.Contains(r.out, "de (nodeadkeys)") || !strings.Contains(r.out, "owner approves") {
		t.Fatalf("set %+v", r)
	}
	var body map[string]string
	last := got[len(got)-1]
	if err := json.Unmarshal([]byte(last[strings.Index(last, "{"):]), &body); err != nil ||
		body["layout"] != "de" || body["variant"] != "nodeadkeys" || body["reason"] != "I type German" || body["idempotency_key"] == "" {
		t.Fatalf("request %v: %v", got, err)
	}
	for _, c := range got {
		if strings.Contains(c, "/approve") {
			t.Fatalf("the CLI must only ask, never approve: %v", got)
		}
	}
	if r := run(t, "", false, "keyboard", "set", "fr", "-q"); r.code != 0 || r.out != "act-9\n" {
		t.Fatalf("set -q %+v", r)
	}
	if r := run(t, "", false, "keyboard", "set", "fr", "--json"); r.code != 0 || !strings.Contains(r.out, `"awaiting_approval"`) {
		t.Fatalf("set --json %+v", r)
	}
}

func TestKeyboardSetRefusals(t *testing.T) {
	var got []string
	keyboardHub(t, keyboardView, &got)
	for _, args := range [][]string{{"keyboard", "set"}, {"keyboard", "set", "de", "a", "b"}} {
		if r := run(t, "", false, args...); r.code == 0 || !strings.Contains(r.errOut, "arg") || len(got) != 0 {
			t.Fatalf("%v: %+v (nothing may be asked: %v)", args, r, got)
		}
	}
	if r := run(t, "", false, "keyboard", "set", "zz"); r.code != ExitNotFound {
		t.Fatalf("a layout the image does not offer: %+v", r)
	}
}
