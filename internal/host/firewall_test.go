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

func TestFirewallRoute(t *testing.T) {
	get := func(srv *Server) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/firewall", nil))
		return rec
	}
	if rec := get(&Server{}); rec.Code != http.StatusNotFound {
		t.Fatalf("no Firewall source: the route is off, got %d", rec.Code)
	}
	rec := get(&Server{Firewall: func(context.Context) (any, error) { return map[string]any{"schema": "onemind.firewall/v1"}, nil }})
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), `"schema":"onemind.firewall/v1"`) {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
	rec = get(&Server{Firewall: func(context.Context) (any, error) { return nil, errors.New("nft: secret detail") }})
	if rec.Code != http.StatusInternalServerError || strings.Contains(rec.Body.String(), "secret") {
		t.Fatalf("a read error is 500 and does not leak its text: %d %s", rec.Code, rec.Body)
	}
	if rec := get(&Server{Firewall: func(context.Context) (any, error) { return nil, nil }}); rec.Code != http.StatusOK {
		t.Fatal(rec.Code)
	}
	post := httptest.NewRecorder()
	(&Server{Firewall: func(context.Context) (any, error) { return nil, nil }}).Handler().ServeHTTP(post, httptest.NewRequest("POST", "/v1/firewall", nil))
	if post.Code == http.StatusOK || post.Code == http.StatusAccepted {
		t.Fatalf("the firewall route reads only: POST got %d", post.Code)
	}
}
