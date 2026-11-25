// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/onemindos/onemindos/internal/firewall"
)

// AllowManager is internal/firewall.Allower: owner allow rules with automatic revert.
type AllowManager interface {
	Add(ctx context.Context, id, proto string, port int, scope string) (firewall.Allow, error)
	Confirm(ctx context.Context, id string) (firewall.Allow, error)
	Remove(ctx context.Context, id string) error
}

// firewallAllowRoutes are the owner allow rule calls. The gateway sends them only for an action the
// owner approved with a passkey (allow) or for an owner's own call (confirm, remove); this service
// checks the values again and can only write into the two owner lists of the OneMind table.
func (s *Server) firewallAllowRoutes(mux *http.ServeMux) {
	if s.FirewallAllow == nil {
		return
	}
	mux.HandleFunc("POST /v1/firewall/allow", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			ID    string `json:"id"`
			Proto string `json:"proto"`
			Port  int    `json:"port"`
			Scope string `json:"scope"`
		}
		dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&body); err != nil {
			apiError(w, http.StatusBadRequest, "bad_request", "malformed", "the request body is not valid")
			return
		}
		rule, err := s.FirewallAllow.Add(r.Context(), body.ID, body.Proto, body.Port, body.Scope)
		s.allowAnswer(w, http.StatusOK, rule, err)
	})
	mux.HandleFunc("POST /v1/firewall/allow/{id}/confirm", func(w http.ResponseWriter, r *http.Request) {
		rule, err := s.FirewallAllow.Confirm(r.Context(), r.PathValue("id"))
		s.allowAnswer(w, http.StatusOK, rule, err)
	})
	mux.HandleFunc("DELETE /v1/firewall/allow/{id}", func(w http.ResponseWriter, r *http.Request) {
		err := s.FirewallAllow.Remove(r.Context(), r.PathValue("id"))
		s.allowAnswer(w, http.StatusOK, map[string]bool{"removed": true}, err)
	})
}

func (s *Server) allowAnswer(w http.ResponseWriter, code int, v any, err error) {
	var ref *firewall.Refusal
	switch {
	case err == nil:
		writeJSON(w, code, v)
	case errors.As(err, &ref) && ref.Reason == "unknown_rule":
		apiError(w, http.StatusNotFound, "not_found", ref.Reason, ref.Message)
	case errors.As(err, &ref):
		apiError(w, http.StatusConflict, "refused", ref.Reason, ref.Message)
	default:
		s.S.log().Error("firewall allow failed", "err", err)
		apiError(w, http.StatusInternalServerError, "internal", "firewall_allow", "the firewall rule could not be saved; see the box's journal")
	}
}
