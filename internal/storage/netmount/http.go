// SPDX-License-Identifier: Apache-2.0

package netmount

import (
	"encoding/json"
	"errors"
	"net/http"
)

// Routes adds the network-mount calls to the storage socket (onemindd storage
// serve; the socket's peer check covers them). They are idempotent: the
// gateway sends a whole approved mount and the hub converges on it.
//
//	GET    /v1/netmounts        {available, smb, nfs: why not, mounts: [...]}
//	PUT    /v1/netmounts/{id}   Spec → Status (test mount read-only, then mount)
//	GET    /v1/netmounts/{id}   Status, read now (mounted | failing | unmounted)
//	DELETE /v1/netmounts/{id}   detach and forget
//
// A request body is never echoed, logged or quoted in an error.
func (m *Manager) Routes(mux *http.ServeMux) {
	mux.HandleFunc("GET /v1/netmounts", func(w http.ResponseWriter, r *http.Request) {
		why := map[string]*string{}
		for _, p := range []string{SMB, NFS} {
			if u := m.Unavailable(p); u != "" {
				why[p] = &u
			} else {
				why[p] = nil
			}
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"available": why[SMB] == nil || why[NFS] == nil, "smb_unavailable": why[SMB],
			"nfs_unavailable": why[NFS], "mounts": m.List(),
		})
	})
	mux.HandleFunc("PUT /v1/netmounts/{id}", func(w http.ResponseWriter, r *http.Request) {
		var s Spec
		dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8<<10))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&s); err != nil {
			apiError(w, http.StatusBadRequest, "bad_request", "malformed", "the request body is not valid")
			return
		}
		st, err := m.Mount(r.Context(), r.PathValue("id"), s)
		m.answer(w, st, err)
	})
	mux.HandleFunc("GET /v1/netmounts/{id}", func(w http.ResponseWriter, r *http.Request) {
		st, err := m.Check(r.Context(), r.PathValue("id"))
		m.answer(w, st, err)
	})
	mux.HandleFunc("DELETE /v1/netmounts/{id}", func(w http.ResponseWriter, r *http.Request) {
		err := m.Unmount(r.Context(), r.PathValue("id"))
		m.answer(w, Status{ID: r.PathValue("id"), State: StateUnmounted, Since: m.now()}, err)
	})
}

func (m *Manager) answer(w http.ResponseWriter, st Status, err error) {
	var ref *Refusal
	switch {
	case err == nil:
		writeJSON(w, http.StatusOK, st)
	case errors.As(err, &ref):
		apiError(w, http.StatusConflict, "refused", ref.Reason, ref.Message)
	default:
		// Never echo err: it may carry output of a program that handled a secret.
		m.log().Error("network mount call failed", "err", err)
		apiError(w, http.StatusInternalServerError, "internal", "netmount", "the network mount failed on the hub; see its journal")
	}
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func apiError(w http.ResponseWriter, code int, kind, reason, msg string) {
	writeJSON(w, code, map[string]string{"error": kind, "reason": reason, "message": msg})
}
