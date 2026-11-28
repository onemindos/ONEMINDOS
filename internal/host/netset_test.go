// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/netset"
)

type fakeNet struct {
	why       string
	status    netset.Status
	applied   []string
	confirmed []string
	err       error
}

func (f *fakeNet) Unavailable() string                  { return f.why }
func (f *fakeNet) Status(context.Context) netset.Status { return f.status }
func (f *fakeNet) Apply(_ context.Context, iface string, c netset.Config) (netset.Status, error) {
	f.applied = append(f.applied, iface+" "+c.Mode+" "+c.Address+" "+c.ActionID)
	return f.status, f.err
}
func (f *fakeNet) Confirm(_ context.Context, iface, actionID string) (netset.Status, error) {
	f.confirmed = append(f.confirmed, iface+" "+actionID)
	return f.status, f.err
}

func netCall(srv *Server, method, path, body string) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, httptest.NewRequest(method, path, strings.NewReader(body)))
	return rec
}

func TestNetworkChangeRoutes(t *testing.T) {
	f := &fakeNet{status: netset.Status{Available: true}}
	srv := &Server{S: &Service{Net: f}}
	body := `{"mode":"static","address":"192.0.2.50/24","gateway":"192.0.2.1","action_id":"act-1"}`
	confirm := `{"action_id":"act-1"}`

	if rec := netCall(srv, "PUT", "/v1/network/eth0", body); rec.Code != 200 || len(f.applied) != 1 || f.applied[0] != "eth0 static 192.0.2.50/24 act-1" {
		t.Fatalf("%d %s %v", rec.Code, rec.Body, f.applied)
	}
	if rec := netCall(srv, "GET", "/v1/network/changes", ""); rec.Code != 200 || !strings.Contains(rec.Body.String(), `"available":true`) {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
	if rec := netCall(srv, "POST", "/v1/network/eth0/confirm", confirm); rec.Code != 200 || len(f.confirmed) != 1 || f.confirmed[0] != "eth0 act-1" {
		t.Fatalf("%d %s %v", rec.Code, rec.Body, f.confirmed)
	}
	if rec := netCall(srv, "PUT", "/v1/network/eth0", `{"mode":"static","bogus":1}`); rec.Code != 400 || len(f.applied) != 1 {
		t.Fatalf("unknown fields are refused before anything runs: %d", rec.Code)
	}

	f.err = &netset.Refusal{Reason: "no_pending_change", Message: "nothing waiting"}
	if rec := netCall(srv, "POST", "/v1/network/eth0/confirm", confirm); rec.Code != 409 || !strings.Contains(rec.Body.String(), `"reason":"no_pending_change"`) {
		t.Fatalf("a refusal is 409 with its reason: %d %s", rec.Code, rec.Body)
	}
	f.err = context.DeadlineExceeded
	if rec := netCall(srv, "PUT", "/v1/network/eth0", body); rec.Code != 500 || strings.Contains(rec.Body.String(), "deadline") {
		t.Fatalf("an unexpected error is 500 and not echoed: %d %s", rec.Code, rec.Body)
	}

	f.err, f.why = nil, "NetworkManager is not running on this box"
	if rec := netCall(srv, "PUT", "/v1/network/eth0", body); rec.Code != 409 || !strings.Contains(rec.Body.String(), `"reason":"network_unavailable"`) {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
}

func TestNetworkChangeWithoutManager(t *testing.T) {
	srv := &Server{S: &Service{}}
	if rec := netCall(srv, "GET", "/v1/network/changes", ""); rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), `"available":false`) {
		t.Fatalf("%d %s", rec.Code, rec.Body)
	}
	if rec := netCall(srv, "PUT", "/v1/network/eth0", `{"mode":"dhcp"}`); rec.Code != 409 {
		t.Fatalf("%d", rec.Code)
	}
	if rec := netCall(srv, "POST", "/v1/network/eth0/confirm", `{"action_id":"act-1"}`); rec.Code != 409 {
		t.Fatalf("%d", rec.Code)
	}
}
