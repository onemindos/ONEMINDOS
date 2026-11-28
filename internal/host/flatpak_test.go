// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/flatpak"
)

type fakeFlatpak struct {
	why   string
	calls []string
	err   error
}

func (f *fakeFlatpak) Unavailable() string { return f.why }
func (f *fakeFlatpak) Search(_ context.Context, q string) ([]flatpak.App, error) {
	f.calls = append(f.calls, "search:"+q)
	return []flatpak.App{{ID: "md.obsidian.Obsidian", Name: "Obsidian"}}, f.err
}
func (f *fakeFlatpak) Installed(context.Context) ([]flatpak.App, error) { return nil, nil }
func (f *fakeFlatpak) Install(_ context.Context, id string) error {
	f.calls = append(f.calls, "install:"+id)
	return f.err
}
func (f *fakeFlatpak) Update(_ context.Context, id string) error {
	f.calls = append(f.calls, "update:"+id)
	return f.err
}
func (f *fakeFlatpak) Remove(_ context.Context, id string) error {
	f.calls = append(f.calls, "remove:"+id)
	return f.err
}
func (f *fakeFlatpak) Launch(_ context.Context, id string) error {
	f.calls = append(f.calls, "launch:"+id)
	return f.err
}

func fpCall(h http.Handler, method, path string) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(method, path, nil))
	return rec
}

func TestFlatpakSaysWhyNotAndRefusesEverything(t *testing.T) {
	for _, tc := range []struct {
		m    FlatpakManager
		want string
	}{{nil, "no desktop apps"}, {&fakeFlatpak{why: "Flatpak is not installed"}, "Flatpak is not installed"}} {
		h := (&Server{S: &Service{Flatpak: tc.m}, AllowUID: -1, AllowGID: -1}).Handler()
		if r := fpCall(h, "GET", "/v1/flatpak"); r.Code != 200 || !strings.Contains(r.Body.String(), `"available":false`) || !strings.Contains(r.Body.String(), tc.want) {
			t.Errorf("status: %d %s", r.Code, r.Body)
		}
		for _, c := range [][2]string{{"POST", "/v1/flatpak/apps/md.obsidian.Obsidian/install"}, {"DELETE", "/v1/flatpak/apps/md.obsidian.Obsidian"}, {"GET", "/v1/flatpak/search?q=ob"}} {
			if r := fpCall(h, c[0], c[1]); r.Code != 409 || !strings.Contains(r.Body.String(), "flatpak_unavailable") {
				t.Errorf("%v while unavailable: %d %s", c, r.Code, r.Body)
			}
		}
	}
}

func TestFlatpakRoutesReachTheManager(t *testing.T) {
	f := &fakeFlatpak{}
	h := (&Server{S: &Service{Flatpak: f}, AllowUID: -1, AllowGID: -1}).Handler()
	for _, c := range [][2]string{{"POST", "/v1/flatpak/apps/md.obsidian.Obsidian/install"}, {"POST", "/v1/flatpak/apps/md.obsidian.Obsidian/update"},
		{"POST", "/v1/flatpak/apps/md.obsidian.Obsidian/launch"}, {"DELETE", "/v1/flatpak/apps/md.obsidian.Obsidian"}, {"GET", "/v1/flatpak/search?q=obsidian"}} {
		if r := fpCall(h, c[0], c[1]); r.Code != 200 {
			t.Fatalf("%v: %d %s", c, r.Code, r.Body)
		}
	}
	want := "install:md.obsidian.Obsidian update:md.obsidian.Obsidian launch:md.obsidian.Obsidian remove:md.obsidian.Obsidian search:obsidian"
	if got := strings.Join(f.calls, " "); got != want {
		t.Fatalf("calls %q", got)
	}
}

func TestFlatpakRefusalsAreConflictsAndOtherErrorsNeverEchoOutput(t *testing.T) {
	f := &fakeFlatpak{err: &flatpak.Refusal{Reason: "not_installed", Message: "x is not installed"}}
	h := (&Server{S: &Service{Flatpak: f}, AllowUID: -1, AllowGID: -1}).Handler()
	if r := fpCall(h, "DELETE", "/v1/flatpak/apps/a.b.C"); r.Code != 409 || !strings.Contains(r.Body.String(), "not_installed") {
		t.Errorf("refusal: %d %s", r.Code, r.Body)
	}
	f.err = errors.New("flatpak install: exit status 1: secret-token-in-output")
	if r := fpCall(h, "POST", "/v1/flatpak/apps/a.b.C/install"); r.Code != 500 || strings.Contains(r.Body.String(), "secret-token") {
		t.Errorf("error: %d %s", r.Code, r.Body)
	}
}
