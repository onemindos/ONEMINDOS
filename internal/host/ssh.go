// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"net/http"

	"github.com/onemindos/onemindos/internal/ownerssh"
)

// SSHManager is the owner's SSH access (internal/ownerssh.Manager). Nil on a Service means the box has none:
// GET /v1/ssh says so and the rest refuse.
type SSHManager interface {
	Unavailable() string
	State(ctx context.Context) (ownerssh.State, error)
	AddKey(ctx context.Context, line string) error
	RemoveKey(ctx context.Context, fingerprint string) error
	SetEnabled(ctx context.Context, on bool) error
}

// SSHStatus is GET /v1/ssh.
type SSHStatus struct {
	Available bool           `json:"available"`
	Reason    *string        `json:"unavailable_reason"`
	Enabled   bool           `json:"enabled"`
	Running   bool           `json:"running"`
	Internet  bool           `json:"internet"` // a cloud board: port 22 answers any address, not only the LAN and mesh
	Keys      []ownerssh.Key `json:"keys"`
}

func (s *Server) sshStatus(ctx context.Context) (SSHStatus, error) {
	st := SSHStatus{Keys: []ownerssh.Key{}}
	if s.S.SSH == nil {
		why := "this host service has no SSH management"
		st.Reason = &why
		return st, nil
	}
	if why := s.S.SSH.Unavailable(); why != "" {
		st.Reason = &why
		return st, nil
	}
	box, err := s.S.SSH.State(ctx)
	if err != nil {
		return st, err
	}
	return SSHStatus{Available: true, Enabled: box.Enabled, Running: box.Running, Internet: box.Internet, Keys: box.Keys}, nil
}

// sshRoutes adds the owner-SSH calls. The gateway calls them only after an owner approved the action
// (core/onemind_core/sshaccess.py); each one is a single job, applied by onemind-ssh-apply.service.
//
//	GET  /v1/ssh               available, why not, switch, whether sshd runs, internet-facing (cloud board), the keys
//	POST /v1/ssh/keys          {public_key}: authorise one key
//	POST /v1/ssh/keys/remove   {fingerprint}: take one key out
//	PUT  /v1/ssh/enabled       {enabled}: SSH on or off, also after a reboot
func (s *Server) sshRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /v1/ssh", func(w http.ResponseWriter, r *http.Request) {
		st, err := s.sshStatus(r.Context())
		if err != nil {
			s.sshError(w, "state", err)
			return
		}
		writeJSON(w, http.StatusOK, st)
	})
	mux.HandleFunc("POST /v1/ssh/keys", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			PublicKey string `json:"public_key"`
		}
		if !s.smbBody(w, r, &body) || !s.sshReady(w, r) {
			return
		}
		s.sshDone(w, "add", s.S.SSH.AddKey(r.Context(), body.PublicKey), map[string]bool{"added": true})
	})
	mux.HandleFunc("POST /v1/ssh/keys/remove", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Fingerprint string `json:"fingerprint"`
		}
		if !s.smbBody(w, r, &body) || !s.sshReady(w, r) {
			return
		}
		s.sshDone(w, "remove", s.S.SSH.RemoveKey(r.Context(), body.Fingerprint), map[string]bool{"removed": true})
	})
	mux.HandleFunc("PUT /v1/ssh/enabled", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Enabled *bool `json:"enabled"`
		}
		if !s.smbBody(w, r, &body) {
			return
		}
		if body.Enabled == nil {
			apiError(w, http.StatusBadRequest, "bad_request", "malformed", "enabled is required")
			return
		}
		if !s.sshReady(w, r) {
			return
		}
		s.sshDone(w, "switch", s.S.SSH.SetEnabled(r.Context(), *body.Enabled), map[string]bool{"enabled": *body.Enabled})
	})
}

func (s *Server) sshReady(w http.ResponseWriter, r *http.Request) bool {
	st, err := s.sshStatus(r.Context())
	if err != nil {
		s.sshError(w, "state", err)
		return false
	}
	if !st.Available {
		apiError(w, http.StatusConflict, "refused", "ssh_unavailable", *st.Reason)
	}
	return st.Available
}

func (s *Server) sshDone(w http.ResponseWriter, what string, err error, ok any) {
	if err != nil {
		s.sshError(w, what, err)
		return
	}
	writeJSON(w, http.StatusOK, ok)
}

func (s *Server) sshError(w http.ResponseWriter, what string, err error) {
	var ref *ownerssh.Refusal
	if errors.As(err, &ref) {
		apiError(w, http.StatusConflict, "refused", ref.Reason, ref.Message)
		return
	}
	s.S.log().Error("ssh "+what+" failed", "err", err)
	apiError(w, http.StatusInternalServerError, "internal", "ssh_"+what, "SSH access failed on the box; see its journal")
}
