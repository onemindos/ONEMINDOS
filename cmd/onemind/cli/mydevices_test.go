// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// devicesHub answers like routers/devices_me.py. "pat-token" is an API token (session_required); dev_owner_pk
// holds the last owner passkey; with stepUp set the box has passkeys and the CLI's session is not fresh.
func devicesHub(t *testing.T, got *[]string, stepUp bool) {
	t.Helper()
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*got = append(*got, r.Method+" "+r.URL.Path)
		switch r.Header.Get("Authorization") {
		case "Bearer " + ownerTok:
		case "Bearer pat-token":
			// The real body (DeviceService._session_person -> deny(..., tell=True)), checked by core test_my_devices.
			msg := map[string]string{http.MethodGet: "not allowed to list your devices", http.MethodDelete: "not allowed to remove a device"}[r.Method]
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": msg, "reason": "session_required"})
			return
		default:
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/me/devices":
			jsonOut(w, 200, map[string]any{"devices": []map[string]any{
				{"id": "dev_phone", "label": "Pixel 9", "kind": "phone", "current": false, "last_seen_at": nil, "first_seen_at": nil,
					"credentials": []map[string]any{{"source": "sessions", "id": "s2"}, {"source": "sessions", "id": "s3"}, {"source": "passkeys", "id": "pk1"}}},
				{"id": "dev_cli", "label": "onemind-cli", "kind": "app", "current": true, "last_seen_at": nil, "first_seen_at": nil,
					"credentials": []map[string]any{{"source": "sessions", "id": "s1"}}},
			}, "sources": map[string]bool{"sessions": true}})
		case r.Method == http.MethodDelete && stepUp:
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "sign in again with your passkey to do this", "reason": "step_up_required"})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/me/devices/dev_phone":
			jsonOut(w, 200, map[string]any{"id": "dev_phone", "removed": true, "revoked": map[string]int{"sessions": 2, "passkeys": 1, "approver_keys": 0, "push": 0}})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/me/devices/dev_cli":
			jsonOut(w, 409, map[string]string{"error": "conflict", "message": "this is the device you are using; sign out here instead", "reason": "current_device"})
		case r.Method == http.MethodDelete:
			jsonOut(w, 200, map[string]any{"id": "gone", "removed": false, "revoked": map[string]int{"sessions": 0}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
}

func TestMyDevicesList(t *testing.T) {
	var got []string
	devicesHub(t, &got, false)
	r := run(t, "", false, "my-devices", "list")
	if r.code != 0 || !strings.Contains(r.out, "Pixel 9") || !strings.Contains(r.out, "2 sign-ins, 1 passkey") || !strings.Contains(r.out, "this one") {
		t.Fatalf("%+v", r)
	}
	if strings.Index(r.out, "onemind-cli") > strings.Index(r.out, "Pixel 9") {
		t.Fatalf("the device in use comes first: %q", r.out)
	}
	r = run(t, "", false, "--json", "my-devices", "list")
	var v myDevicesView
	if r.code != 0 || json.Unmarshal([]byte(r.out), &v) != nil || len(v.Devices) != 2 {
		t.Fatalf("%+v", r)
	}
}

func TestMyDevicesRemove(t *testing.T) {
	var got []string
	devicesHub(t, &got, false)
	r := run(t, "", false, "my-devices", "remove", "dev_phone")
	if r.code != 0 || !strings.Contains(r.out, "3 credentials revoked") || got[len(got)-1] != "DELETE /v1/me/devices/dev_phone" {
		t.Fatalf("%+v %v", r, got)
	}
	if r = run(t, "", false, "my-devices", "remove", "dev_gone"); r.code != 0 || !strings.Contains(r.out, "already removed") {
		t.Fatalf("removing twice is safe: %+v", r)
	}
	if r = run(t, "", false, "my-devices", "remove", "dev_cli"); r.code != ExitConflict || !strings.Contains(r.errOut, "sign it out instead") {
		t.Fatalf("the device in use is refused: %+v", r)
	}
	if r = run(t, "", false, "--json", "my-devices", "remove", "dev_phone"); r.code != 0 || !strings.Contains(r.out, `"removed": true`) {
		t.Fatalf("%+v", r)
	}
}

func TestMyDevicesNeedsSessionAndPasskey(t *testing.T) {
	var got []string
	devicesHub(t, &got, true)
	r := run(t, "", false, "my-devices", "remove", "dev_phone")
	if r.code != ExitUnauthenticated || !strings.Contains(r.errOut, "Confirm this change in the dashboard") {
		t.Fatalf("%+v", r)
	}
	t.Setenv("ONEMIND_TOKEN", "pat-token")
	if r = run(t, "", false, "my-devices", "list"); r.code != ExitPermissionDenied || !strings.Contains(r.errOut, "not an API token") {
		t.Fatalf("%+v", r)
	}
}

// A gateway from before reason=session_required was sent answers a bare 403; the CLI still says what to do.
func TestMyDevicesExplainsABare403FromAnOlderGateway(t *testing.T) {
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "not allowed to remove a device"})
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", "pat-token")
	if r := run(t, "", false, "my-devices", "remove", "dev_phone"); r.code != ExitPermissionDenied || !strings.Contains(r.errOut, "not an API token") {
		t.Fatalf("%+v", r)
	}
}
