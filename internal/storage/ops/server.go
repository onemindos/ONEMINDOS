// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/onemindos/onemindos/internal/storage"
)

// Server is onemindd's local storage API on a Unix socket (storage.md §4.8:
// "onemindd exposes the operations on its local socket only"). The socket is
// mode 0660, owned by root and the gateway's group; each connection's peer
// credentials are checked again (root, or the allowed uid/gid). Nothing here
// approves anything: an operation starts only with the plan_sha256 of a plan
// the gateway's owner approved, and the engine re-renders that plan itself.
//
//	GET  /v1/status              set, disks, health, running operation
//	POST /v1/plans               {kind, device?, member?, unprotect?, wipe?} → plan (dry run)
//	POST /v1/operations          the same + {plan_sha256, action_id} → 202 operation
//	GET  /v1/operations          recent operations
//	GET  /v1/operations/{id}     one operation (journal)
//	POST /v1/recovery-key/take   the pending recovery key, once (H-11)
type Server struct {
	E               *Engine
	RecoveryKeyFile string        // default storage.RecoveryKeyFile
	AllowUID        int           // besides root; -1 none
	AllowGID        int           // -1 none
	HealthEvery     time.Duration // SMART is read at most this often (default 10 min, storage.md §4.7)

	mu       sync.Mutex
	health   map[string]storage.Health
	healthAt time.Time
}

// Status is GET /v1/status.
type Status struct {
	Mount              string                    `json:"mount"`
	Mirror             *storage.Mirror           `json:"mirror"`
	Disks              []storage.Disk            `json:"disks"`
	Health             map[string]storage.Health `json:"health"`
	Active             *Op                       `json:"active_operation"`
	Journal            bool                      `json:"operations_available"`
	RecoveryKeyPending bool                      `json:"recovery_key_pending"`
	TPM2               bool                      `json:"tpm2"`
	At                 time.Time                 `json:"at"`
}

type ctxKey struct{}

// Listen opens the socket at path with mode 0660 and group gid (-1: keep).
func Listen(path string, gid int) (net.Listener, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	if fi, err := os.Lstat(path); err == nil && fi.Mode()&os.ModeSocket != 0 {
		_ = os.Remove(path)
	}
	l, err := net.Listen("unix", path)
	if err != nil {
		return nil, err
	}
	if err := os.Chmod(path, 0o660); err != nil {
		l.Close()
		return nil, err
	}
	if gid >= 0 {
		if err := os.Chown(path, 0, gid); err != nil {
			l.Close()
			return nil, err
		}
	}
	return l, nil
}

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
	err := hs.Serve(l)
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}

func (s *Server) peerAllowed(r *http.Request) bool {
	c, _ := r.Context().Value(ctxKey{}).(net.Conn)
	uc, ok := c.(*net.UnixConn)
	if !ok {
		return c == nil // in-process tests (httptest) have no socket
	}
	uid, gid, known := peerCred(uc)
	if !known {
		return true // no SO_PEERCRED on this OS: the socket's mode is the only gate (dev only)
	}
	return uid == 0 || (s.AllowUID >= 0 && uid == s.AllowUID) || (s.AllowGID >= 0 && gid == s.AllowGID)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func apiError(w http.ResponseWriter, code int, kind, msg string, extra map[string]any) {
	body := map[string]any{"error": kind, "message": msg}
	for k, v := range extra {
		body[k] = v
	}
	writeJSON(w, code, body)
}

func decode(w http.ResponseWriter, r *http.Request) (Request, bool) {
	var req Request
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8192))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		apiError(w, http.StatusBadRequest, "bad_request", err.Error(), nil)
		return req, false
	}
	return req, true
}

// Handler returns the API.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/status", func(w http.ResponseWriter, r *http.Request) {
		st, err := s.Status(r.Context())
		if err != nil {
			apiError(w, http.StatusInternalServerError, "internal", err.Error(), nil)
			return
		}
		writeJSON(w, http.StatusOK, st)
	})
	mux.HandleFunc("POST /v1/plans", func(w http.ResponseWriter, r *http.Request) {
		req, ok := decode(w, r)
		if !ok {
			return
		}
		p, err := s.E.Plan(r.Context(), req)
		if err != nil {
			apiError(w, http.StatusBadRequest, "bad_request", err.Error(), nil)
			return
		}
		writeJSON(w, http.StatusOK, p)
	})
	mux.HandleFunc("POST /v1/operations", func(w http.ResponseWriter, r *http.Request) {
		req, ok := decode(w, r)
		if !ok {
			return
		}
		op, err := s.E.Start(r.Context(), req)
		var pe *PlanError
		switch {
		case err == nil:
			writeJSON(w, http.StatusAccepted, op)
		case errors.Is(err, ErrBusy):
			apiError(w, http.StatusConflict, "busy", err.Error(), map[string]any{"active_operation": s.E.Active()})
		case errors.Is(err, ErrNoJournal):
			apiError(w, http.StatusServiceUnavailable, "unavailable", err.Error(), nil)
		case errors.As(err, &pe) && pe.Code == "blocked":
			apiError(w, http.StatusConflict, "stale_precondition", err.Error(), map[string]any{"reason": "plan_blocked", "plan": pe.Plan})
		case errors.As(err, &pe):
			apiError(w, http.StatusConflict, "stale_precondition", err.Error(), map[string]any{"reason": "plan_changed", "plan": pe.Plan})
		default:
			apiError(w, http.StatusBadRequest, "bad_request", err.Error(), nil)
		}
	})
	mux.HandleFunc("GET /v1/operations", func(w http.ResponseWriter, r *http.Request) {
		if s.E.Store == nil {
			writeJSON(w, http.StatusOK, []*Op{})
			return
		}
		all, err := s.E.Store.List()
		if err != nil {
			apiError(w, http.StatusInternalServerError, "internal", err.Error(), nil)
			return
		}
		if len(all) > 50 {
			all = all[:50]
		}
		if a := s.E.Active(); a != nil {
			for i := range all {
				if all[i].ID == a.ID {
					all[i] = a
				}
			}
		}
		writeJSON(w, http.StatusOK, all)
	})
	mux.HandleFunc("GET /v1/operations/{id}", func(w http.ResponseWriter, r *http.Request) {
		op, err := s.E.Get(r.PathValue("id"))
		switch {
		case errors.Is(err, ErrNotFound):
			apiError(w, http.StatusNotFound, "not_found", "no such operation", nil)
		case errors.Is(err, ErrNoJournal):
			apiError(w, http.StatusServiceUnavailable, "unavailable", err.Error(), nil)
		case err != nil:
			apiError(w, http.StatusInternalServerError, "internal", err.Error(), nil)
		default:
			writeJSON(w, http.StatusOK, op)
		}
	})
	mux.HandleFunc("POST /v1/recovery-key/take", func(w http.ResponseWriter, r *http.Request) {
		key, err := s.takeRecoveryKey()
		if errors.Is(err, os.ErrNotExist) {
			apiError(w, http.StatusNotFound, "not_found", "no recovery key is waiting to be shown (it is shown once)", nil)
			return
		}
		if err != nil {
			apiError(w, http.StatusInternalServerError, "internal", err.Error(), nil)
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"recovery_key": key})
	})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !s.peerAllowed(r) {
			apiError(w, http.StatusForbidden, "permission_denied", "this socket serves root and the gateway only", nil)
			return
		}
		mux.ServeHTTP(w, r)
	})
}

func (s *Server) keyFile() string {
	if s.RecoveryKeyFile != "" {
		return s.RecoveryKeyFile
	}
	return storage.RecoveryKeyFile
}

// takeRecoveryKey returns the pending key and destroys the file (overwrite,
// then remove), so it is shown exactly once.
func (s *Server) takeRecoveryKey() (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	path := s.keyFile()
	b, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	if f, err := os.OpenFile(path, os.O_WRONLY, 0); err == nil {
		_, _ = f.Write(make([]byte, len(b)))
		_ = f.Sync()
		f.Close()
	}
	if err := os.Remove(path); err != nil {
		return "", err
	}
	return string(b), nil
}

// Status reads the set and disks now; SMART at most every HealthEvery.
func (s *Server) Status(ctx context.Context) (Status, error) {
	st := Status{Mount: s.E.Mount, Journal: s.E.Store != nil, Active: s.E.Active(), TPM2: storage.TPM2Present(), At: s.E.now()}
	if _, err := os.Stat(s.keyFile()); err == nil {
		st.RecoveryKeyPending = true
	}
	m, err := s.E.Facts.Mirror(ctx, s.E.Mount)
	if err != nil {
		return st, err
	}
	disks, err := s.E.Facts.Disks(ctx, m)
	if err != nil {
		return st, err
	}
	st.Mirror, st.Disks = m, disks
	every := s.HealthEvery
	if every <= 0 {
		every = 10 * time.Minute
	}
	s.mu.Lock()
	stale := s.health == nil || st.At.Sub(s.healthAt) >= every
	s.mu.Unlock()
	if stale {
		h := map[string]storage.Health{}
		for _, d := range disks {
			if v, err := s.E.Facts.Health(ctx, d); err == nil {
				h[d.Path] = v
			}
		}
		s.mu.Lock()
		s.health, s.healthAt = h, st.At
		s.mu.Unlock()
	}
	s.mu.Lock()
	st.Health = s.health
	s.mu.Unlock()
	return st, nil
}
