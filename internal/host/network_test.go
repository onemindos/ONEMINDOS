// SPDX-License-Identifier: Apache-2.0

package host

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestNetworkRoute(t *testing.T) {
	get := func(srv *Server) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/network", nil))
		return rec
	}
	if rec := get(&Server{}); rec.Code != http.StatusNotFound {
		t.Fatalf("no Network source: the route is off, got %d", rec.Code)
	}
	rec := get(&Server{Network: func() (any, error) { return map[string]any{"schema": "onemind.netview/v1"}, nil }})
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), `"schema":"onemind.netview/v1"`) {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
	rec = get(&Server{Network: func() (any, error) { return nil, errors.New("netlink: secret detail") }})
	if rec.Code != http.StatusInternalServerError || strings.Contains(rec.Body.String(), "secret") {
		t.Fatalf("a read error is 500 and does not leak its text: %d %s", rec.Code, rec.Body)
	}
}
