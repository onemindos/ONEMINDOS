// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/onemindos/onemindos/internal/netset"
)

// NetManager is the wired-network side (internal/netset.Manager). Nil on a Service means this box cannot
// change its network: the status says so and the other calls refuse.
type NetManager interface {
	Unavailable() string
	Status(ctx context.Context) netset.Status
	Apply(ctx context.Context, iface string, c netset.Config) (netset.Status, error)
	Confirm(ctx context.Context, iface, actionID string) (netset.Status, error)
}

// netRoutes adds the wired-network change calls (P-08). The gateway sends them only for a change an owner
// approved. Like the file-sharing calls they are desired-state calls, not journaled one-shot actions:
// the box's own record of the pending change is what makes a retry safe.
//
//	GET  /v1/network/changes          available, the change waiting for confirmation, the last finished one
//	PUT  /v1/network/{iface}          {action_id, mode, address, gateway, dns, rollback_seconds}: apply with automatic rollback
//	POST /v1/network/{iface}/confirm  {action_id}: keep the matching pending change on that interface
func (s *Server) netRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /v1/network/changes", func(w http.ResponseWriter, r *http.Request) {
		if s.S.Net == nil {
			why := "this host service cannot change the network"
			writeJSON(w, http.StatusOK, netset.Status{Reason: &why})
			return
		}
		writeJSON(w, http.StatusOK, s.S.Net.Status(r.Context()))
	})
	mux.HandleFunc("PUT /v1/network/{iface}", func(w http.ResponseWriter, r *http.Request) {
		var cfg netset.Config
		dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&cfg); err != nil {
			apiError(w, http.StatusBadRequest, "bad_request", "malformed", "the request body is not valid")
			return
		}
		if !s.netReady(w) {
			return
		}
		// The change outlives the request (the deadline is the box's), so it is not cancelled with it.
		st, err := s.S.Net.Apply(context.WithoutCancel(r.Context()), r.PathValue("iface"), cfg)
		if err != nil {
			s.netError(w, "apply", err)
			return
		}
		writeJSON(w, http.StatusOK, st)
	})
	mux.HandleFunc("POST /v1/network/{iface}/confirm", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			ActionID string `json:"action_id"`
		}
		dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&body); err != nil {
			apiError(w, http.StatusBadRequest, "bad_request", "malformed", "the request body is not valid")
			return
		}
		if !s.netReady(w) {
			return
		}
		// Not cancelled with the request either: a gateway that dies mid-call must not cut Confirm between
		// recording the confirmation and destroying the checkpoint.
		st, err := s.S.Net.Confirm(context.WithoutCancel(r.Context()), r.PathValue("iface"), body.ActionID)
		if err != nil {
			s.netError(w, "confirm", err)
			return
		}
		writeJSON(w, http.StatusOK, st)
	})
}

func (s *Server) netReady(w http.ResponseWriter) bool {
	why := "this host service cannot change the network"
	if s.S.Net != nil {
		why = s.S.Net.Unavailable()
	}
	if why != "" {
		apiError(w, http.StatusConflict, "refused", "network_unavailable", why)
		return false
	}
	return true
}

func (s *Server) netError(w http.ResponseWriter, what string, err error) {
	var ref *netset.Refusal
	if errors.As(err, &ref) {
		apiError(w, http.StatusConflict, "refused", ref.Reason, ref.Message)
		return
	}
	s.S.log().Error("network "+what+" failed", "err", err)
	apiError(w, http.StatusInternalServerError, "internal", "network_"+what, "the network change failed on the box; see its journal")
}
