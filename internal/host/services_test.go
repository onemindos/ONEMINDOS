// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestServicesRoute(t *testing.T) {
	get := func(srv *Server, method string) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest(method, "/v1/services", nil))
		return rec
	}
	if rec := get(&Server{}, "GET"); rec.Code != http.StatusNotFound {
		t.Fatalf("no Services source: the route is off, got %d", rec.Code)
	}
	ok := &Server{Services: func(context.Context) (any, error) {
		return map[string]any{"schema": "onemind.host.services/v1"}, nil
	}}
	if rec := get(ok, "GET"); rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), `"schema":"onemind.host.services/v1"`) {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
	if rec := get(ok, "POST"); rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("the services route only reads, POST got %d", rec.Code)
	}
	bad := &Server{Services: func(context.Context) (any, error) { return nil, errors.New("dbus: secret detail") }}
	if rec := get(bad, "GET"); rec.Code != http.StatusInternalServerError || strings.Contains(rec.Body.String(), "secret") {
		t.Fatalf("a systemd error is 500 and does not leak its text: %d %s", rec.Code, rec.Body)
	}
}
