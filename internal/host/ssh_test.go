// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/ownerssh"
)

type fakeSSH struct {
	why      string
	state    ownerssh.State
	stateErr error
	calls    []string
	err      error
}

func (f *fakeSSH) Unavailable() string { return f.why }
func (f *fakeSSH) State(context.Context) (ownerssh.State, error) {
	return f.state, f.stateErr
}
func (f *fakeSSH) AddKey(_ context.Context, l string) error {
	f.calls = append(f.calls, "add "+l)
	return f.err
}
func (f *fakeSSH) RemoveKey(_ context.Context, fp string) error {
	f.calls = append(f.calls, "rm "+fp)
	return f.err
}
func (f *fakeSSH) SetEnabled(_ context.Context, on bool) error {
	if on {
		f.calls = append(f.calls, "on")
	} else {
		f.calls = append(f.calls, "off")
	}
	return f.err
}

func sshServer(m SSHManager) http.Handler {
	return (&Server{S: &Service{SSH: m}, AllowUID: -1, AllowGID: -1}).Handler()
}

func send(h http.Handler, method, path, body string) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(method, path, strings.NewReader(body)))
	return rec
}

func TestSSHStatusSaysWhyNotAndRefusesChanges(t *testing.T) {
	for _, tc := range []struct {
		m    SSHManager
		want string
	}{{nil, "no SSH management"}, {&fakeSSH{why: "sshd is missing"}, "sshd is missing"}} {
		h := sshServer(tc.m)
		r := send(h, "GET", "/v1/ssh", "")
		if r.Code != 200 || !strings.Contains(r.Body.String(), `"available":false`) || !strings.Contains(r.Body.String(), tc.want) ||
			!strings.Contains(r.Body.String(), `"keys":[]`) {
			t.Errorf("%d %s", r.Code, r.Body)
		}
		for _, c := range [][3]string{{"POST", "/v1/ssh/keys", `{"public_key":"ssh-ed25519 AAAA"}`}, {"POST", "/v1/ssh/keys/remove", `{"fingerprint":"x"}`}, {"PUT", "/v1/ssh/enabled", `{"enabled":true}`}} {
			if r := send(h, c[0], c[1], c[2]); r.Code != 409 || !strings.Contains(r.Body.String(), "ssh_unavailable") {
				t.Errorf("%s while unavailable: %d %s", c[1], r.Code, r.Body)
			}
		}
	}
}

func TestSSHStatusListsTheBox(t *testing.T) {
	f := &fakeSSH{state: ownerssh.State{Enabled: true, Running: true, Keys: []ownerssh.Key{{Fingerprint: "SHA256:x", Type: "ed25519", Bits: 256, Comment: "alex"}}}}
	r := send(sshServer(f), "GET", "/v1/ssh", "")
	for _, want := range []string{`"available":true`, `"enabled":true`, `"running":true`, `"internet":false`, `"fingerprint":"SHA256:x"`, `"comment":"alex"`} {
		if !strings.Contains(r.Body.String(), want) {
			t.Errorf("missing %s in %s", want, r.Body)
		}
	}
	f.state.Internet = true
	r = send(sshServer(f), "GET", "/v1/ssh", "")
	for _, want := range []string{`"internet":true`} {
		if !strings.Contains(r.Body.String(), want) {
			t.Errorf("missing %s in %s", want, r.Body)
		}
	}
}

func TestSSHChangesReachTheManager(t *testing.T) {
	f := &fakeSSH{}
	h := sshServer(f)
	for _, c := range [][3]string{{"POST", "/v1/ssh/keys", `{"public_key":"ssh-ed25519 AAAA a"}`}, {"POST", "/v1/ssh/keys/remove", `{"fingerprint":"SHA256:x"}`},
		{"PUT", "/v1/ssh/enabled", `{"enabled":false}`}, {"PUT", "/v1/ssh/enabled", `{"enabled":true}`}} {
		if r := send(h, c[0], c[1], c[2]); r.Code != 200 {
			t.Fatalf("%s: %d %s", c[1], r.Code, r.Body)
		}
	}
	if got := strings.Join(f.calls, "|"); got != "add ssh-ed25519 AAAA a|rm SHA256:x|off|on" {
		t.Fatalf("%s", got)
	}
	if r := send(h, "PUT", "/v1/ssh/enabled", `{}`); r.Code != 400 || len(f.calls) != 4 {
		t.Errorf("enabled is required: %d", r.Code)
	}
	if r := send(h, "POST", "/v1/ssh/keys", `{"public_key":"a","extra":1}`); r.Code != 400 {
		t.Errorf("unknown field: %d", r.Code)
	}
}

func TestSSHRefusalsAndErrors(t *testing.T) {
	f := &fakeSSH{err: &ownerssh.Refusal{Reason: "no_such_key", Message: "that key is not on this box any more"}}
	h := sshServer(f)
	if r := send(h, "POST", "/v1/ssh/keys/remove", `{"fingerprint":"SHA256:x"}`); r.Code != 409 || !strings.Contains(r.Body.String(), "no_such_key") {
		t.Errorf("refusal: %d %s", r.Code, r.Body)
	}
	f.err = errors.New("onemind-owner said: secret detail")
	if r := send(h, "POST", "/v1/ssh/keys", `{"public_key":"ssh-ed25519 AAAA"}`); r.Code != 500 || strings.Contains(r.Body.String(), "secret detail") {
		t.Errorf("an unknown failure never echoes program output: %d %s", r.Code, r.Body)
	}
	f.stateErr = errors.New("boom")
	if r := send(h, "GET", "/v1/ssh", ""); r.Code != 500 {
		t.Errorf("state error: %d", r.Code)
	}
}
