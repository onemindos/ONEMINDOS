// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/smb"
)

type fakeSMB struct {
	why      string
	applied  [][]smb.Share
	pw       []string
	applyErr error
	pwErr    error
}

func (f *fakeSMB) Unavailable() string { return f.why }
func (f *fakeSMB) Apply(_ context.Context, l []smb.Share) error {
	f.applied = append(f.applied, l)
	return f.applyErr
}
func (f *fakeSMB) SetPassword(_ context.Context, u, p string) error {
	f.pw = append(f.pw, u+":"+p)
	return f.pwErr
}
func (f *fakeSMB) Current() []smb.Share { return nil }

func put(h http.Handler, path, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPut, path, strings.NewReader(body))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

const oneShare = `{"shares":[{"id":"shr_1","kind":"home","name":"alex","user":"alex","path":"home/alex"}]}`

func TestSMBStatusSaysWhyNot(t *testing.T) {
	for _, tc := range []struct {
		smb  SMBManager
		want string
	}{{nil, "no file sharing"}, {&fakeSMB{why: "Samba is not installed"}, "Samba is not installed"}} {
		srv := &Server{S: &Service{SMB: tc.smb}, AllowUID: -1, AllowGID: -1}
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/v1/smb", nil))
		if rec.Code != 200 || !strings.Contains(rec.Body.String(), `"available":false`) || !strings.Contains(rec.Body.String(), tc.want) {
			t.Errorf("%d %s", rec.Code, rec.Body)
		}
		if r := put(srv.Handler(), "/v1/smb/shares", oneShare); r.Code != 409 || !strings.Contains(r.Body.String(), "smb_unavailable") {
			t.Errorf("apply while unavailable: %d %s", r.Code, r.Body)
		}
	}
}

func TestSMBApplyAndPassword(t *testing.T) {
	f := &fakeSMB{}
	h := (&Server{S: &Service{SMB: f}, AllowUID: -1, AllowGID: -1}).Handler()
	if r := put(h, "/v1/smb/shares", oneShare); r.Code != 200 || len(f.applied) != 1 || f.applied[0][0].Name != "alex" {
		t.Fatalf("apply: %d %s %+v", r.Code, r.Body, f.applied)
	}
	if r := put(h, "/v1/smb/users/alex/password", `{"password":"correct horse"}`); r.Code != 200 || f.pw[0] != "alex:correct horse" {
		t.Fatalf("password: %d %s", r.Code, r.Body)
	}
	if r := put(h, "/v1/smb/shares", `{"shares":[],"extra":1}`); r.Code != 400 {
		t.Errorf("unknown field: %d", r.Code)
	}
}

func TestSMBErrorsNeverEchoSecrets(t *testing.T) {
	f := &fakeSMB{pwErr: errors.New("smbpasswd said: correct horse")}
	h := (&Server{S: &Service{SMB: f}, AllowUID: -1, AllowGID: -1}).Handler()
	r := put(h, "/v1/smb/users/alex/password", `{"password":"correct horse"}`)
	if r.Code != 500 || strings.Contains(r.Body.String(), "correct horse") {
		t.Errorf("%d %s", r.Code, r.Body)
	}
	f.applyErr = &smb.Refusal{Reason: "config_rejected", Message: "Samba rejected the configuration"}
	if r := put(h, "/v1/smb/shares", oneShare); r.Code != 409 || !strings.Contains(r.Body.String(), "config_rejected") {
		t.Errorf("refusal: %d %s", r.Code, r.Body)
	}
}
