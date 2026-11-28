// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/onemindos/onemindos/internal/svcregistry"
)

// Schema names the status document's shape.
const Schema = "onemind.host/v1"

// Server is the host API on a Unix socket (mode 0660, root and the gateway's
// group; systemd opens it, onemind-host.socket). Each connection's peer
// credentials are checked again: root, or the allowed uid (the gateway's user).
//
//	GET  /v1/status            what this box can do, and why not
//	POST /v1/operations        {action_id, kind, version?} → 202 new, 200 known
//	GET  /v1/operations        recent operations, newest first
//	GET  /v1/operations/{id}   one operation by action id
//	GET  /v1/plans/factory-reset  what a factory reset would erase, keep and warn (read-only)
//	GET  /v1/smb, PUT /v1/smb/shares, PUT /v1/smb/users/{user}/password   file sharing (smb.go)
//	GET  /v1/ssh, POST /v1/ssh/keys, POST /v1/ssh/keys/remove, PUT /v1/ssh/enabled   the owner's SSH keys and switch (ssh.go)
//	GET  /v1/storage/housekeeping  TRIM status, smartd warnings, removable drives (read-only; 404 when Media is nil)
//	GET  /v1/flatpak, GET /v1/flatpak/search, POST|DELETE /v1/flatpak/apps/{id}[/install|update|launch]   Flathub desktop apps (flatpak.go)
//	GET  /v1/network           read-only network facts (internal/netview; 404 when Network is nil)
//	GET  /v1/time              time zone and clock synchronisation (timedatectl; 404 when Time is nil)
//	GET  /v1/keyboard          the keyboard layout now and the layouts the image offers (read-only; 404 when Keymap is nil)
//	GET  /v1/firewall          the live nftables ruleset in a structured form (internal/firewall; 404 when Firewall is nil)
//	POST /v1/firewall/allow, POST .../allow/{id}/confirm, DELETE .../allow/{id}   owner allow rules with automatic revert (firewall_allow.go)
//	GET  /v1/network/changes, PUT /v1/network/{iface}, POST /v1/network/{iface}/confirm   wired address change with automatic rollback (netset.go)
//	GET  /v1/services          service cards: the image's registry joined with systemd (internal/svcregistry; 404 when Services is nil)
//	GET  /v1/services/{unit}/logs?lines=200&follow=1   a registry unit's journal as text lines (404 when ServiceLogs is nil)
type Server struct {
	S        *Service
	AllowUID int // besides root; -1 none
	AllowGID int // -1 none
	// Ctx is the service's lifetime: actions run on it, not on the request's
	// (they outlive the request), so stopping the service stops waiting ones.
	Ctx context.Context
	// PeerCred reads a connection's uid and gid (default SO_PEERCRED; tests replace it).
	PeerCred func(*net.UnixConn) (uid, gid int, ok bool)
	// Network answers GET /v1/network (NET-UI-01). It only reads; nil leaves the route off.
	Network func() (any, error)
	// Firewall answers GET /v1/firewall (P-09 part 1). It only reads (nft -j list ruleset); nil leaves the route off.
	Firewall func(ctx context.Context) (any, error)
	// FirewallAllow keeps the owner allow rules (P-09 part 2): POST /v1/firewall/allow, POST
	// /v1/firewall/allow/{id}/confirm, DELETE /v1/firewall/allow/{id}. Nil leaves the routes off.
	FirewallAllow AllowManager
	// Services answers GET /v1/services (#623). It only reads (systemctl show); nil leaves the route off.
	Services func(ctx context.Context) (any, error)
	// Time answers GET /v1/time: the zone and the clock's sync state (timezone.go). It only reads; nil leaves the route off.
	Time func(ctx context.Context) (any, error)
	// Hostname names the box in GET /v1/status (#875; default os.Hostname): the harmless read the gateway
	// and the boot battery use to prove the socket reaches this service. An error leaves the field out.
	Hostname func() (string, error)
	// ServiceLogs answers GET /v1/services/{unit}/logs (#636): journal lines of a unit the registry lists,
	// unredacted (the gateway redacts every line before anyone sees it). It returns svcregistry.ErrUnknownUnit
	// before writing anything for an unlisted unit; nil leaves the route off.
	ServiceLogs func(ctx context.Context, unit string, lines int, follow bool, w io.Writer) error
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
	Hostname   string       `json:"hostname,omitempty"`
}

type ctxKey struct{}

// Serve runs the API on l until ctx ends.
func (s *Server) Serve(ctx context.Context, l net.Listener) error {
	hs := &http.Server{
		Handler:           s.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       time.Minute,
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
	name := s.Hostname
	if name == nil {
		name = os.Hostname
	}
	if h, err := name(); err == nil {
		st.Hostname = h
	}
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
	if s.Network != nil {
		mux.HandleFunc("GET /v1/network", func(w http.ResponseWriter, r *http.Request) {
			v, err := s.Network()
			if err != nil {
				apiError(w, http.StatusInternalServerError, "internal", "network", "the network facts could not be read")
				return
			}
			writeJSON(w, http.StatusOK, v)
		})
	}
	if s.S != nil && s.S.Media != nil {
		mux.HandleFunc("GET /v1/storage/housekeeping", func(w http.ResponseWriter, r *http.Request) {
			if why := s.S.Media.Unavailable(); why != "" {
				apiError(w, http.StatusServiceUnavailable, "unavailable", "unavailable", why)
				return
			}
			writeJSON(w, http.StatusOK, s.S.Media.View(r.Context()))
		})
	}
	if s.S != nil && s.S.Keymap != nil {
		mux.HandleFunc("GET /v1/keyboard", func(w http.ResponseWriter, r *http.Request) {
			v, err := s.S.Keymap.View()
			if err != nil {
				apiError(w, http.StatusInternalServerError, "internal", "keyboard", "the keyboard layouts could not be read")
				return
			}
			writeJSON(w, http.StatusOK, v)
		})
	}
	if s.Firewall != nil {
		mux.HandleFunc("GET /v1/firewall", func(w http.ResponseWriter, r *http.Request) {
			v, err := s.Firewall(r.Context())
			if err != nil {
				apiError(w, http.StatusInternalServerError, "internal", "firewall", "the firewall rules could not be read")
				return
			}
			writeJSON(w, http.StatusOK, v)
		})
	}
	if s.Services != nil {
		mux.HandleFunc("GET /v1/services", func(w http.ResponseWriter, r *http.Request) {
			v, err := s.Services(r.Context())
			if err != nil {
				apiError(w, http.StatusInternalServerError, "internal", "services", "systemd could not be asked about the services")
				return
			}
			writeJSON(w, http.StatusOK, v)
		})
	}
	if s.Time != nil {
		mux.HandleFunc("GET /v1/time", func(w http.ResponseWriter, r *http.Request) {
			v, err := s.Time(r.Context())
			if err != nil {
				apiError(w, http.StatusInternalServerError, "internal", "time", "the clock could not be read")
				return
			}
			writeJSON(w, http.StatusOK, v)
		})
	}
	if s.ServiceLogs != nil {
		mux.HandleFunc("GET /v1/services/{unit}/logs", s.serviceLogs)
	}
	mux.HandleFunc("POST /v1/operations", func(w http.ResponseWriter, r *http.Request) {
		var req Request
		dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&req); err != nil {
			apiError(w, http.StatusBadRequest, "bad_request", "malformed", err.Error())
			return
		}
		ctx := s.Ctx
		if ctx == nil {
			ctx = context.WithoutCancel(r.Context())
		}
		op, created, err := s.S.Submit(ctx, req)
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
	mux.HandleFunc("GET /v1/plans/factory-reset", func(w http.ResponseWriter, r *http.Request) {
		if s.S.Reset == nil {
			apiError(w, http.StatusServiceUnavailable, "unavailable", "unavailable", s.S.Unavailable(KindFactoryReset))
			return
		}
		writeJSON(w, http.StatusOK, s.S.Reset.Plan(r.Context()))
	})
	s.smbRoutes(mux)
	s.sshRoutes(mux)
	s.firewallAllowRoutes(mux)
	s.flatpakRoutes(mux)
	s.netRoutes(mux)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !s.peerAllowed(r) {
			apiError(w, http.StatusForbidden, "permission_denied", "peer", "this socket serves root and the gateway only")
			return
		}
		mux.ServeHTTP(w, r)
	})
}

// serviceLogs streams a unit's journal as text/plain, one line per journal entry, flushed as it comes.
func (s *Server) serviceLogs(w http.ResponseWriter, r *http.Request) {
	lines := 200
	if v := r.URL.Query().Get("lines"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 1 || n > svcregistry.MaxLogLines {
			apiError(w, http.StatusBadRequest, "bad_request", "invalid", fmt.Sprintf("lines must be 1-%d", svcregistry.MaxLogLines))
			return
		}
		lines = n
	}
	fw := &flushWriter{w: w}
	err := s.ServiceLogs(r.Context(), r.PathValue("unit"), lines, r.URL.Query().Get("follow") == "1", fw)
	switch {
	case fw.started:
		return // the stream is under way: an error now just ends it
	case errors.Is(err, svcregistry.ErrUnknownUnit):
		apiError(w, http.StatusNotFound, "not_found", "unknown_unit", err.Error())
	case err != nil:
		apiError(w, http.StatusInternalServerError, "internal", "journal", "the journal could not be read")
	default:
		fw.start()
	}
}

// flushWriter sends the 200 header on the first write and flushes after each one.
type flushWriter struct {
	w       http.ResponseWriter
	started bool
}

func (f *flushWriter) start() {
	if !f.started {
		f.started = true
		f.w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		f.w.Header().Set("Cache-Control", "no-store")
		f.w.WriteHeader(http.StatusOK)
	}
}

func (f *flushWriter) Write(p []byte) (int, error) {
	f.start()
	n, err := f.w.Write(p)
	if fl, ok := f.w.(http.Flusher); ok {
		fl.Flush()
	}
	return n, err
}

// ActivationListener returns the socket systemd passed (LISTEN_PID, LISTEN_FDS,
// fd 3: sd_listen_fds), or nil when the process was not socket-activated.
// systemd creates the socket with its owner, group and mode, so this service
// needs no chown (and no CAP_CHOWN under SystemCallFilter=~@privileged).
func ActivationListener(getenv func(string) string, pid int, fd uintptr) (net.Listener, error) {
	if getenv("LISTEN_PID") != strconv.Itoa(pid) {
		return nil, nil
	}
	if n, err := strconv.Atoi(getenv("LISTEN_FDS")); err != nil || n != 1 {
		return nil, fmt.Errorf("socket activation: want exactly one socket, LISTEN_FDS=%q", getenv("LISTEN_FDS"))
	}
	f := os.NewFile(fd, "host.sock")
	defer f.Close()
	l, err := net.FileListener(f)
	if err != nil {
		return nil, fmt.Errorf("socket activation: %w", err)
	}
	if _, ok := l.(*net.UnixListener); !ok {
		l.Close()
		return nil, errors.New("socket activation: the passed socket is not a Unix socket")
	}
	return l, nil
}
