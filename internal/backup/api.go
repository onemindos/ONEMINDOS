// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
)

// Handler serves the onemindd local backup API (CONTRACT-12-DRAFT §12.5,
// loopback only, H-24):
//
//	GET  /api/v1/backup/status -> Status
//	POST /api/v1/backup/jobs   signed onemind.job/v1 envelope -> JobResult (or a file)
//
// It refuses any caller that is not on the loopback interface. Everything
// that changes anything, backups included, comes only as a job signed with
// the gateway's job key, after the owner approved the action. There is no
// unsigned "run a backup" route: any process on the box (an app with host
// networking, a compromised service) could otherwise start runs, fill the
// destination and block restores behind the run lock. Nothing in the repo
// called it: the updater snapshots with its own restic settings.
func (a *Agent) Handler(base context.Context) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/v1/backup/jobs", a.jobsHandler(base)) // signed jobs (job.go, jobapi.go)
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
