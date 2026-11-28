// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPluginsAndHostGrants(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/plugins": ok([]any{map[string]any{"id": "meshcore", "name": "MeshCore", "installed_version": "1.2.0", "status": "installed", "slots": []any{
			map[string]any{"slot": "home_tile", "declared": false, "names": []any{}, "approval": "none"},
			map[string]any{"slot": "commands", "declared": true, "names": []any{"send"}, "approval": "each_time"}}}}),
		"GET /v1/instance": ok(map[string]any{"name": "box"}),
		"POST /v1/actions": waitingAction,
		"GET /v1/plugins/meshcore": ok(map[string]any{"id": "meshcore", "name": "MeshCore", "installed_version": nil, "status": "stopped", "slots": []any{
			map[string]any{"slot": "home_tile", "declared": false, "names": []any{}, "approval": "none"}}}),
		"GET /v1/plugins/meshcore/tools":     ok([]any{map[string]any{"name": "send", "title": "Send a message", "effect": "write"}}),
		"GET /v1/plugins/meshcore/settings":  ok(map[string]any{"bundle_sha256": "sha256:" + strings.Repeat("a", 64), "settings": map[string]any{"channel": "1"}, "schema": map[string]any{}}),
		"POST /v1/plugins/meshcore/settings": waitingAction,
		"GET /v1/host-grants": ok(map[string]any{"grants": []any{
			map[string]any{"id": "hg_1", "app_id": "meshcore", "kind": "device", "device_class": "usb-serial", "path": nil, "reason": "radio", "active": true},
			map[string]any{"id": "hg_2", "app_id": "meshcore", "kind": "gpu", "reason": "speed", "active": false}}}),
		"POST /v1/host-grants/requests":           waitingAction,
		"POST /v1/host-grants/hg_1/revoke":        ok(map[string]any{"id": "hg_1", "active": false}),
		"GET /v1/plugin-trust/keys":               ok(map[string]any{"keys": []any{map[string]any{"id": "key_1", "name": "ours", "active": true, "enrolled_at": "2026-11-01T00:00:00Z"}}}),
		"POST /v1/plugin-trust/keys/requests":     waitingAction,
		"POST /v1/plugin-trust/keys/key_1/revoke": waitingAction,
	})
	outHas(t, run(t, "", false, "plugins", "list").out, "meshcore", "1.2.0", "installed")
	outHas(t, run(t, "", false, "plugins", "list").out, "PLACES", "commands")
	outHas(t, run(t, "", false, "plugins", "show", "meshcore").out, "stopped")
	outHas(t, run(t, "", false, "plugins", "show", "meshcore").out, "place home_tile", "not declared")
	for verb, typ := range map[string]string{"restart": "app.restart", "disable": "app.stop", "enable": "app.start", "update": "app.update"} {
		outHas(t, run(t, "", false, "plugins", verb, "meshcore").out, "plugin meshcore requested", "act_7")
		var found bool
		for _, c := range g.sent("POST", "/v1/actions") {
			if c.body["type"] == typ && c.body["params"].(map[string]any)["app_id"] == "meshcore" {
				found = true
			}
		}
		if !found {
			t.Fatalf("plugins %s filed no %s request", verb, typ)
		}
	}
	outHas(t, run(t, "", false, "plugins", "tools", "meshcore").out, "send", "write", "Send a message")
	outHas(t, run(t, "", false, "plugins", "settings", "show", "meshcore").out, "sha256:", `"channel": "1"`)

	f := filepath.Join(t.TempDir(), "s.json")
	_ = os.WriteFile(f, []byte(`{"channel": "2"}`), 0o600)
	r := run(t, "", false, "plugins", "settings", "set", "meshcore", "--file", f)
	outHas(t, r.out, "Requested", "act_7")
	sent := g.sent("POST", "/v1/plugins/meshcore/settings")[0]
	if sent.body["bundle_sha256"] != "sha256:"+strings.Repeat("a", 64) || sent.body["idempotency_key"] == nil || sent.body["expires_at"] == nil || sent.idem == "" {
		t.Fatalf("settings request %+v", sent)
	}

	out := run(t, "", false, "plugins", "host-grants", "list").out
	outHas(t, out, "hg_1", "device usb-serial", "active", "revoked", "gpu")
	run(t, "", false, "plugins", "host-grants", "list", "--app", "meshcore")
	if g.sent("GET", "/v1/host-grants")[1].query != "app_id=meshcore" {
		t.Fatal("app filter")
	}
	r = run(t, "", false, "plugins", "host-grants", "request", "--app", "meshcore", "--kind", "device", "--class", "usb-serial", "--reason", "radio")
	outHas(t, r.out, "Requested", "act_7")
	if b := g.sent("POST", "/v1/host-grants/requests")[0].body; b["app_id"] != "meshcore" || b["device_class"] != "usb-serial" || b["reason"] != "radio" {
		t.Fatalf("grant body %+v", b)
	}
	if r := run(t, "", false, "plugins", "host-grants", "request", "--app", "meshcore"); r.code != ExitUsage {
		t.Fatalf("needs kind and reason %+v", r)
	}
	if r := run(t, "", false, "plugins", "host-grants", "revoke", "hg_1"); r.code != ExitUsage || len(g.sent("POST", "/v1/host-grants/hg_1/revoke")) != 0 {
		t.Fatalf("revoke needs --yes %+v", r)
	}
	if r := run(t, "", false, "plugins", "host-grants", "revoke", "hg_1", "--yes"); r.code != 0 {
		t.Fatalf("revoke %+v", r)
	}

	outHas(t, run(t, "", false, "plugins", "keys", "list").out, "key_1", "ours", "active")
	kf := filepath.Join(t.TempDir(), "k.pem")
	_ = os.WriteFile(kf, []byte("PUBKEY\n"), 0o600)
	outHas(t, run(t, "", false, "plugins", "keys", "enroll", "--name", "new", "--key-file", kf).out, "Requested")
	if g.sent("POST", "/v1/plugin-trust/keys/requests")[0].body["public_key"] != "PUBKEY" {
		t.Fatal("key body")
	}
	outHas(t, run(t, "", false, "plugins", "keys", "revoke", "key_1").out, "Requested")
	g.neverApproved(t)
}

func TestDataGrantsAndRadios(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/data/grants": ok([]any{map[string]any{"id": "dg_1", "grantee": map[string]any{"kind": "agent", "id": "agent:hermes"},
			"data_class": "photos", "read": true, "write": false, "aggregate": true, "active": true, "expires_at": "2027-01-01T00:00:00Z"}}),
		"DELETE /v1/data/grants/dg_1": ok(map[string]any{"id": "dg_1", "active": false}),
		"GET /v1/radios": ok([]any{
			map[string]any{"id": "n1.lora0", "hostname": "hub", "kind": "lora", "model": "T-Beam", "node_status": "online", "confirm": map[string]any{"profile": "meshcore-companion-usb", "confirmed": false}},
			map[string]any{"id": "n1.zigbee0", "hostname": "hub", "kind": "zigbee", "model": nil, "node_status": "online", "confirm": nil}}),
		"POST /v1/radios/n1.lora0/confirm": func(b map[string]any) (int, any) { return 200, map[string]any{"id": "n1.lora0", "confirm": b} },
	})
	outHas(t, run(t, "", false, "data", "grants", "list").out, "dg_1", "agent:hermes", "photos", "read, aggregate", "active")
	if r := run(t, "", false, "data", "grants", "revoke", "dg_1"); r.code != ExitUsage {
		t.Fatalf("needs --yes %+v", r)
	}
	if r := run(t, "", false, "data", "grants", "revoke", "dg_1", "--yes"); r.code != 0 || len(g.sent("DELETE", "/v1/data/grants/dg_1")) != 1 {
		t.Fatalf("revoke %+v", r)
	}
	out := run(t, "", false, "radios", "list").out
	outHas(t, out, "n1.lora0", "not confirmed", "n1.zigbee0")
	// Without --profile, confirm uses the profile the radio's own card asks for (radios.go).
	if r := run(t, "", false, "radios", "confirm", "n1.lora0"); r.code != 0 || !strings.Contains(r.out, "Nothing was opened") {
		t.Fatalf("confirm from card %+v", r)
	}
	if r := run(t, "", false, "radios", "confirm", "n1.zigbee0"); r.code != ExitNotFound || !strings.Contains(r.out+r.errOut, "no radio n1.zigbee0 asks to be confirmed") {
		t.Fatalf("a radio with no confirm card %+v", r)
	}
	if n := len(g.sent("POST", "/v1/radios/n1.zigbee0/confirm")); n != 0 {
		t.Fatalf("a radio with no confirm card must send nothing, sent %d", n)
	}
	// An explicit --profile must win over the card's profile.
	if r := run(t, "", false, "radios", "confirm", "n1.lora0", "--profile", "meshcore-repeater-usb"); r.code != 0 || !strings.Contains(r.out, "Nothing was opened") {
		t.Fatalf("confirm %+v", r)
	}
	posts := g.sent("POST", "/v1/radios/n1.lora0/confirm")
	if len(posts) != 2 || posts[0].body["profile"] != "meshcore-companion-usb" || posts[1].body["profile"] != "meshcore-repeater-usb" {
		t.Fatalf("profile not sent: %+v", posts)
	}
}

func TestRadiosListSaysSoWhenThereAreNone(t *testing.T) {
	newRouteGW(t, map[string]func(map[string]any) (int, any){"GET /v1/radios": ok([]any{})})
	outHas(t, run(t, "", false, "radios", "list").out, "No radios found.")
}
