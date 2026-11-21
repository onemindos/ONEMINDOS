// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/onemindos/onemindos/internal/smb"
)

// SMBManager is the file-sharing side (internal/smb.Manager). Nil on a Service
// means the box has no file sharing: GET /v1/smb says so and the rest refuse.
type SMBManager interface {
	Unavailable() string
	Apply(ctx context.Context, list []smb.Share) error
	SetPassword(ctx context.Context, user, password string) error
	Current() []smb.Share
}

// SMBStatus is GET /v1/smb.
type SMBStatus struct {
	Available bool    `json:"available"`
	Reason    *string `json:"unavailable_reason"`
	Shares    int     `json:"shares"`
}

func (s *Server) smbStatus() SMBStatus {
	if s.S.SMB == nil {
		why := "this host service has no file sharing"
		return SMBStatus{Reason: &why}
	}
	if why := s.S.SMB.Unavailable(); why != "" {
		return SMBStatus{Reason: &why}
	}
	return SMBStatus{Available: true, Shares: len(s.S.SMB.Current())}
}

// smbRoutes adds the file-sharing calls (docs/leap/core/FILE-SHARING.md). They
// are idempotent desired-state calls, not journaled one-shot actions: the
// gateway sends the whole approved list and the box converges on it.
//
//	GET /v1/smb                           available, why not, how many shares
//	PUT /v1/smb/shares                    {shares: [...]}: make the box share exactly this
//	PUT /v1/smb/users/{user}/password     {password}: set that person's SMB password
func (s *Server) smbRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /v1/smb", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, s.smbStatus())
	})
	mux.HandleFunc("PUT /v1/smb/shares", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Shares []smb.Share `json:"shares"`
		}
		if !s.smbBody(w, r, &body) {
			return
		}
		if !s.smbReady(w) {
			return
		}
		if err := s.S.SMB.Apply(r.Context(), body.Shares); err != nil {
			s.smbError(w, "apply", err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]int{"applied": len(body.Shares)})
	})
	mux.HandleFunc("PUT /v1/smb/users/{user}/password", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Password string `json:"password"`
		}
		if !s.smbBody(w, r, &body) {
			return
		}
		if !s.smbReady(w) {
			return
		}
		if err := s.S.SMB.SetPassword(r.Context(), r.PathValue("user"), body.Password); err != nil {
			s.smbError(w, "password", err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
	})
}

func (s *Server) smbBody(w http.ResponseWriter, r *http.Request, v any) bool {
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 64<<10))
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		apiError(w, http.StatusBadRequest, "bad_request", "malformed", "the request body is not valid")
		return false
	}
	return true
}

func (s *Server) smbReady(w http.ResponseWriter) bool {
	st := s.smbStatus()
	if !st.Available {
		apiError(w, http.StatusConflict, "refused", "smb_unavailable", *st.Reason)
	}
	return st.Available
}

func (s *Server) smbError(w http.ResponseWriter, what string, err error) {
	var ref *smb.Refusal
	if errors.As(err, &ref) {
		apiError(w, http.StatusConflict, "refused", ref.Reason, ref.Message)
		return
	}
	// Never echo err: it may carry output of a program that handled a secret.
	s.S.log().Error("smb "+what+" failed", "err", err)
	apiError(w, http.StatusInternalServerError, "internal", "smb_"+what, "file sharing failed on the box; see its journal")
}
