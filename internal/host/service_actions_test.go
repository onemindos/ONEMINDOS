// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/onemindos/onemindos/internal/svcregistry"
)

// fakeUnits stands in for svcregistry.Reader: only onemind-gateway.service is restartable.
type fakeUnits struct {
	mu        sync.Mutex
	restarted []string
	err       error
}

func (f *fakeUnits) CheckRestart(unit string) error {
	switch unit {
	case "onemind-gateway.service":
		return nil
	case "onemind-rescue.service":
		return svcregistry.ErrNotRestartable
	}
	return svcregistry.ErrUnknownUnit
}

func (f *fakeUnits) Restart(_ context.Context, unit string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.restarted = append(f.restarted, unit)
	return f.err
}

func TestServiceRestartRunsOnlyARestartableUnit(t *testing.T) {
	s, p := newService(t, t.TempDir(), "boot-1")
	if why := s.Unavailable(KindServiceRestart); why == "" {
		t.Fatal("no Units: service-restart must be unavailable")
	}
	u := &fakeUnits{}
	s.Units = u
	for _, bad := range []Request{
		{ActionID: "a", Kind: KindServiceRestart},                                                // no unit
		{ActionID: "a", Kind: KindRestart, Unit: "onemind-gateway.service"},                      // unit on another kind
		{ActionID: "a", Kind: KindServiceRestart, Unit: "../../etc/passwd"},                      // not a unit
		{ActionID: "a", Kind: KindServiceRestart, Unit: "onemind-gateway.service", Version: "1"}, // extra field
	} {
		if err := bad.Validate(); err == nil {
			t.Errorf("%+v was valid", bad)
		}
	}
	var ref *Refusal
	for _, unit := range []string{"onemind-rescue.service", "onemind-mystery.service"} {
		if _, _, err := s.Submit(context.Background(), Request{ActionID: "no-" + unit[:12], Kind: KindServiceRestart, Unit: unit}); !errors.As(err, &ref) || ref.Reason != "not_restartable" {
			t.Fatalf("%s: %v", unit, err)
		}
	}
	op, created, err := s.Submit(context.Background(), Request{ActionID: "act-svc", Kind: KindServiceRestart, Unit: "onemind-gateway.service"})
	if err != nil || !created || op.Unit != "onemind-gateway.service" {
		t.Fatalf("%+v %v %v", op, created, err)
	}
	s.Wait()
	got, _ := s.Store.Get("act-svc")
	if got.State != StateSucceeded || len(u.restarted) != 1 || p.reboots != 0 {
		t.Fatalf("journal %+v, restarted %v, reboots %d", got, u.restarted, p.reboots)
	}
	// The same action id for another unit is a different request: refused, nothing runs.
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-svc", Kind: KindServiceRestart, Unit: "onemind-nats.service"}); !errors.As(err, &ref) || ref.Reason != "action_id_reused" {
		t.Fatalf("reused id: %v", err)
	}
	u.err = errors.New("exit status 1")
	if _, _, err := s.Submit(context.Background(), Request{ActionID: "act-fail", Kind: KindServiceRestart, Unit: "onemind-gateway.service"}); err != nil {
		t.Fatal(err)
	}
	s.Wait()
	if got, _ := s.Store.Get("act-fail"); got.State != StateFailed || got.Reason != "host_error" {
		t.Fatalf("a failed restart is reported failed: %+v", got)
	}
}

func TestServiceLogsRoute(t *testing.T) {
	get := func(srv *Server, path string) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest("GET", path, nil))
		return rec
	}
	if rec := get(&Server{}, "/v1/services/onemind-gateway.service/logs"); rec.Code != http.StatusNotFound {
		t.Fatalf("no ServiceLogs: the route is off, got %d", rec.Code)
	}
	var asked []string
	srv := &Server{ServiceLogs: func(_ context.Context, unit string, lines int, follow bool, w io.Writer) error {
		if unit != "onemind-gateway.service" {
			return svcregistry.ErrUnknownUnit
		}
		asked = append(asked, unit)
		if follow && lines == 5 {
			_, err := io.WriteString(w, "line one\nline two\n")
			return err
		}
		return nil
	}}
	rec := get(srv, "/v1/services/onemind-gateway.service/logs?lines=5&follow=1")
	if rec.Code != http.StatusOK || rec.Body.String() != "line one\nline two\n" || !strings.HasPrefix(rec.Header().Get("Content-Type"), "text/plain") {
		t.Fatalf("%d %q", rec.Code, rec.Body)
	}
	if rec := get(srv, "/v1/services/onemind-gateway.service/logs"); rec.Code != http.StatusOK || rec.Body.Len() != 0 {
		t.Fatalf("an empty journal is 200 with no lines: %d %q", rec.Code, rec.Body)
	}
	if rec := get(srv, "/v1/services/onemind-mystery.service/logs"); rec.Code != http.StatusNotFound || !strings.Contains(rec.Body.String(), "unknown_unit") {
		t.Fatalf("an unlisted unit: %d %s", rec.Code, rec.Body)
	}
	for _, q := range []string{"lines=0", "lines=2001", "lines=x"} {
		if rec := get(srv, "/v1/services/onemind-gateway.service/logs?"+q); rec.Code != http.StatusBadRequest {
			t.Fatalf("%s: %d", q, rec.Code)
		}
	}
	if len(asked) != 2 {
		t.Fatalf("the journal was read for a refused request: %v", asked)
	}
}

func TestSystemJournalRoute(t *testing.T) {
	get := func(srv *Server, path string) *httptest.ResponseRecorder {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest("GET", path, nil))
		return rec
	}
	if rec := get(&Server{}, "/v1/journal"); rec.Code != http.StatusNotFound {
		t.Fatalf("no SystemJournal: the route is off, got %d", rec.Code)
	}
	var asked []svcregistry.JournalQuery
	srv := &Server{SystemJournal: func(_ context.Context, q svcregistry.JournalQuery, w io.Writer) error {
		asked = append(asked, q)
		_, err := io.WriteString(w, "kernel: hello\n")
		return err
	}}
	rec := get(srv, "/v1/journal?unit=sshd.service&priority=err&boot=-1&lines=10")
	if rec.Code != http.StatusOK || rec.Body.String() != "kernel: hello\n" || len(asked) != 1 ||
		asked[0] != (svcregistry.JournalQuery{Unit: "sshd.service", Priority: "err", Boot: -1, Lines: 10}) {
		t.Fatalf("%d %q %+v", rec.Code, rec.Body, asked)
	}
	if rec := get(srv, "/v1/journal"); rec.Code != http.StatusOK || asked[1].Lines != 200 || asked[1].Boot != 0 {
		t.Fatalf("defaults: %d %+v", rec.Code, asked[1])
	}
	for _, q := range []string{"lines=0", "lines=2001", "lines=x", "boot=1", "boot=-99", "boot=x", "priority=9", "unit=--rotate",
		"unit=x.service%20--vacuum-size%3D1", "boot=-1&follow=1"} {
		if rec := get(srv, "/v1/journal?"+q); rec.Code != http.StatusBadRequest {
			t.Fatalf("%s: %d", q, rec.Code)
		}
	}
	if len(asked) != 2 {
		t.Fatalf("journalctl was asked for a refused request: %+v", asked)
	}
}
