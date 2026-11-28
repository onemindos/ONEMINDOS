// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/firewall"
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

type fakeAllow struct{ calls []string }

func (f *fakeAllow) Add(_ context.Context, id, proto string, port int, scope string) (firewall.Allow, error) {
	f.calls = append(f.calls, "add "+id+" "+proto+" "+scope)
	if scope == "wan" {
		return firewall.Allow{}, &firewall.Refusal{Reason: "invalid", Message: "no"}
	}
	return firewall.Allow{ID: id, Proto: proto, Port: port, Scope: scope, State: "pending"}, nil
}
func (f *fakeAllow) Confirm(_ context.Context, id string) (firewall.Allow, error) {
	f.calls = append(f.calls, "confirm "+id)
	if id == "gone" {
		return firewall.Allow{}, &firewall.Refusal{Reason: "unknown_rule", Message: "no such rule"}
	}
	return firewall.Allow{ID: id, State: "confirmed"}, nil
}
func (f *fakeAllow) Remove(_ context.Context, id string) error {
	f.calls = append(f.calls, "remove "+id)
	if id == "boom" {
		return errors.New("nft: secret detail")
	}
	return nil
}

func TestFirewallAllowRoutes(t *testing.T) {
	do := func(srv *Server, method, path, body string) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest(method, path, strings.NewReader(body)))
		return rec
	}
	if rec := do(&Server{}, "POST", "/v1/firewall/allow", "{}"); rec.Code == http.StatusOK || rec.Code == http.StatusAccepted {
		t.Fatalf("no manager: the routes are off, got %d", rec.Code)
	}
	f := &fakeAllow{}
	srv := &Server{S: &Service{}, FirewallAllow: f}
	if rec := do(srv, "POST", "/v1/firewall/allow", `{"id":"a1","proto":"tcp","port":8123,"scope":"lan"}`); rec.Code != 200 || !strings.Contains(rec.Body.String(), `"state":"pending"`) {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
	if rec := do(srv, "POST", "/v1/firewall/allow", `{"id":"a1","proto":"tcp","port":1,"scope":"wan"}`); rec.Code != http.StatusConflict {
		t.Fatalf("a refusal is 409: %d", rec.Code)
	}
	if rec := do(srv, "POST", "/v1/firewall/allow", `{"id":"a1","extra":1}`); rec.Code != http.StatusBadRequest {
		t.Fatalf("unknown fields are refused: %d", rec.Code)
	}
	if rec := do(srv, "POST", "/v1/firewall/allow/a1/confirm", ""); rec.Code != 200 {
		t.Fatal(rec.Code)
	}
	if rec := do(srv, "POST", "/v1/firewall/allow/gone/confirm", ""); rec.Code != http.StatusNotFound {
		t.Fatal(rec.Code)
	}
	if rec := do(srv, "DELETE", "/v1/firewall/allow/a1", ""); rec.Code != 200 {
		t.Fatal(rec.Code)
	}
	if rec := do(srv, "DELETE", "/v1/firewall/allow/boom", ""); rec.Code != http.StatusInternalServerError || strings.Contains(rec.Body.String(), "secret") {
		t.Fatalf("an internal error does not leak its text: %d %s", rec.Code, rec.Body)
	}
}
