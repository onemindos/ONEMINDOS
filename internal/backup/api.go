// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"time"
)

// Handler serves the onemindd local backup API (CONTRACT-12-DRAFT §12.5,
// loopback only, H-24):
//
//	POST /api/v1/backup/run    {reason, wait, action_id?, target_id?} -> {run_id, state}
//	GET  /api/v1/backup/status -> Status
//
// It refuses any caller that is not on the loopback interface. Restores and
// file browsing are not here: they are owner actions that reach the node as
// signed jobs from the gateway.
func (a *Agent) Handler(base context.Context) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/v1/backup/run", func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Reason   string `json:"reason"`
			Wait     bool   `json:"wait"`
			ActionID string `json:"action_id"`
			TargetID string `json:"target_id"`
		}
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad_request", "detail": err.Error()})
			return
		}
		switch req.Reason {
		case ReasonManual, ReasonPreUpdate, ReasonPreDelete:
		default:
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad_request", "detail": "reason must be manual, pre-update or pre-delete"})
			return
		}
		rr := RunRequest{ID: NewRunID(a.Now()), Reason: req.Reason, ActionID: req.ActionID, TargetID: req.TargetID}
		if req.Wait {
			// The request context ends if the updater gives up; the run
			// keeps its own deadline so a half-written snapshot is avoided.
			ctx, cancel := context.WithTimeout(base, 6*time.Hour)
			defer cancel()
			rr.Wait = true
			run, err := a.Run(ctx, rr)
			if err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "internal", "detail": err.Error()})
				return
			}
			writeJSON(w, http.StatusOK, map[string]string{"run_id": run.ID, "state": run.State, "error": run.Error})
			return
		}
		if !a.tryAcquire(rr.ID) {
			writeJSON(w, http.StatusConflict, map[string]string{"error": "busy", "running": a.Running()})
			return
		}
		go func() {
			defer a.release()
			_, _ = a.runLocked(base, rr)
		}()
		writeJSON(w, http.StatusAccepted, map[string]string{"run_id": rr.ID, "state": StateRunning})
	})
	mux.HandleFunc("GET /api/v1/backup/status", func(w http.ResponseWriter, r *http.Request) {
		s, err := a.Status(r.Context())
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "internal", "detail": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, s)
	})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !fromLoopback(r) {
			writeJSON(w, http.StatusForbidden, map[string]string{"error": "forbidden", "detail": "loopback only"})
			return
		}
		mux.ServeHTTP(w, r)
	})
}

func fromLoopback(r *http.Request) bool {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return false
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}
