// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"time"
)

// Schema names the status document's shape.
const Schema = "onemind.host/v1"

// Server is the host API on a Unix socket (mode 0660, root and the gateway's
// group; ops.Listen opens it). Each connection's peer credentials are checked
// again: root, or the allowed uid or gid.
//
//	GET  /v1/status            what this box can do, and why not
//	POST /v1/operations        {action_id, kind, version?} → 202 new, 200 known
//	GET  /v1/operations        recent operations, newest first
//	GET  /v1/operations/{id}   one operation by action id
type Server struct {
	S        *Service
	AllowUID int // besides root; -1 none
	AllowGID int // -1 none
	// PeerCred reads a connection's uid and gid (default SO_PEERCRED; tests replace it).
	PeerCred func(*net.UnixConn) (uid, gid int, ok bool)
}

// Capability is one kind in GET /v1/status.
type Capability struct {
	Kind      string  `json:"kind"`
	Available bool    `json:"available"`
	Reason    *string `json:"unavailable_reason"`
}

// Status is GET /v1/status.
type Status struct {
	Schema     string       `json:"schema"`
	BootID     string       `json:"boot_id"`
	Journal    bool         `json:"journal"`
	Operations []Capability `json:"operations"`
	Active     *Op          `json:"active_operation"`
	At         time.Time    `json:"at"`
}

type ctxKey struct{}

// Serve runs the API on l until ctx ends.
func (s *Server) Serve(ctx context.Context, l net.Listener) error {
	hs := &http.Server{
		Handler:           s.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
		ConnContext: func(ctx context.Context, c net.Conn) context.Context {
			return context.WithValue(ctx, ctxKey{}, c)
		},
	}
	go func() {
		<-ctx.Done()
		sh, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = hs.Shutdown(sh)
	}()
	if err := hs.Serve(l); !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

func (s *Server) peerAllowed(r *http.Request) bool {
	c, _ := r.Context().Value(ctxKey{}).(net.Conn)
	uc, ok := c.(*net.UnixConn)
	if !ok {
		return c == nil // in-process tests (httptest) have no socket
	}
	read := s.PeerCred
	if read == nil {
		if !peerCredSupported {
			return true // no SO_PEERCRED on this OS: the socket mode is the gate (dev only)
		}
		read = peerCred
	}
	uid, gid, known := read(uc)
	if !known {
		return false
	}
	return uid == 0 || (s.AllowUID >= 0 && uid == s.AllowUID) || (s.AllowGID >= 0 && gid == s.AllowGID)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func apiError(w http.ResponseWriter, code int, kind, reason, msg string) {
	writeJSON(w, code, map[string]string{"error": kind, "reason": reason, "message": msg})
}

// Status reports every kind with whether it can run now.
func (s *Server) Status() Status {
	st := Status{Schema: Schema, BootID: s.S.BootID, Journal: s.S.Store != nil, Active: s.S.Active(), At: s.S.now()}
	for _, k := range Kinds {
		c := Capability{Kind: k, Available: true}
		if why := s.S.Unavailable(k); why != "" {
			c.Available, c.Reason = false, &why
		}
		st.Operations = append(st.Operations, c)
	}
	return st
}

// Handler returns the API.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/status", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, s.Status())
	})
	mux.HandleFunc("POST /v1/operations", func(w http.ResponseWriter, r *http.Request) {
		var req Request
		dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&req); err != nil {
			apiError(w, http.StatusBadRequest, "bad_request", "malformed", err.Error())
			return
		}
		// The action outlives the request: it runs on the service's context, not the caller's.
		op, created, err := s.S.Submit(context.WithoutCancel(r.Context()), req)
		var ref *Refusal
		switch {
		case err == nil && created:
			writeJSON(w, http.StatusAccepted, op)
		case err == nil:
			writeJSON(w, http.StatusOK, op)
		case errors.As(err, &ref):
			apiError(w, http.StatusConflict, "refused", ref.Reason, ref.Message)
		case errors.Is(err, ErrNoJournal):
			apiError(w, http.StatusServiceUnavailable, "unavailable", "no_journal", err.Error())
		case req.Validate() != nil:
			apiError(w, http.StatusBadRequest, "bad_request", "invalid", err.Error())
		default:
			apiError(w, http.StatusInternalServerError, "internal", "journal", err.Error())
		}
	})
	mux.HandleFunc("GET /v1/operations", func(w http.ResponseWriter, r *http.Request) {
		if s.S.Store == nil {
			writeJSON(w, http.StatusOK, []Op{})
			return
		}
		all, err := s.S.Store.List()
		if err != nil {
			apiError(w, http.StatusInternalServerError, "internal", "journal", err.Error())
			return
		}
		if len(all) > 50 {
			all = all[:50]
		}
		writeJSON(w, http.StatusOK, append([]Op{}, all...))
	})
	mux.HandleFunc("GET /v1/operations/{id}", func(w http.ResponseWriter, r *http.Request) {
		if s.S.Store == nil {
			apiError(w, http.StatusServiceUnavailable, "unavailable", "no_journal", ErrNoJournal.Error())
			return
		}
		op, err := s.S.Store.Get(r.PathValue("id"))
		switch {
		case errors.Is(err, ErrNotFound):
			apiError(w, http.StatusNotFound, "not_found", "unknown_action", "no host action with that id")
		case err != nil:
			apiError(w, http.StatusInternalServerError, "internal", "journal", err.Error())
		default:
			writeJSON(w, http.StatusOK, op)
		}
	})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !s.peerAllowed(r) {
			apiError(w, http.StatusForbidden, "permission_denied", "peer", "this socket serves root and the gateway only")
			return
		}
		mux.ServeHTTP(w, r)
	})
}
