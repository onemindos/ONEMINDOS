// SPDX-License-Identifier: Apache-2.0

package netmount

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestRoutesRefuseWithoutEchoingTheBody(t *testing.T) {
	m, _, _ := newManager(t)
	mux := http.NewServeMux()
	m.Routes(mux)
	do := func(method, path, body string) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, httptest.NewRequest(method, path, strings.NewReader(body)))
		return rec
	}
	if r := do("PUT", "/v1/netmounts/nas1", `{"protocol":"smb","host":"nas","share":"s","user":"guest","password":"`+secret+`"}`); r.Code != 409 ||
		!strings.Contains(r.Body.String(), "guest_refused") || strings.Contains(r.Body.String(), secret) {
		t.Errorf("guest: %d %s", r.Code, r.Body)
	}
	if r := do("PUT", "/v1/netmounts/nas1", `{"protocol":"smb","password":"`+secret+`","vers":"1.0"}`); r.Code != 400 || strings.Contains(r.Body.String(), secret) {
		t.Errorf("unknown field: %d %s", r.Code, r.Body)
	}
	if r := do("PUT", "/v1/netmounts/nas1", `{"protocol":"nfs","host":"nas","share":"/volume1/x"}`); r.Code != 200 || !strings.Contains(r.Body.String(), `"state":"mounted"`) {
		t.Errorf("nfs: %d %s", r.Code, r.Body)
	}
	if r := do("GET", "/v1/netmounts", ""); r.Code != 200 || !strings.Contains(r.Body.String(), `"available":true`) || !strings.Contains(r.Body.String(), `"id":"nas1"`) {
		t.Errorf("list: %d %s", r.Code, r.Body)
	}
	if r := do("GET", "/v1/netmounts/NAS!", ""); r.Code != 409 || !strings.Contains(r.Body.String(), "invalid_id") {
		t.Errorf("bad id: %d %s", r.Code, r.Body)
	}
	if r := do("DELETE", "/v1/netmounts/nas1", ""); r.Code != 200 {
		t.Errorf("delete: %d %s", r.Code, r.Body)
	}
}
