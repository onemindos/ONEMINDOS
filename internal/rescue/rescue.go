// SPDX-License-Identifier: Apache-2.0

// Package rescue is the rescue console (CORE-UPDATE-8, brief 30 B11,
// docs/leap/core/UPDATES.md §3.5): a small web page served by `onemindd rescue`
// on the host, outside Kubernetes, so the owner can still see the slots, roll
// back and collect logs when k3s or the gateway is broken.
//
// It needs only rauc, systemctl and journalctl. Every page needs the owner
// token (checked against the gateway's tokens file, which stores only hashes).
// Rollback is a POST with a CSRF token and a typed confirmation; nothing here
// acts on its own, and no agent principal is accepted (AI never actuates).
package rescue

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"html/template"
	"log/slog"
	"net/http"
	"os/exec"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
)

// MaxLogBytes bounds the log download (and any command's captured output).
const MaxLogBytes = 4 << 20

// Units whose journal the log download collects.
var logUnits = []string{"onemindd.service", "onemind-update.service", "onemind-rescue.service",
	"onemind-health-gate.service", "rauc.service", "k3s.service", "k3s-agent.service"}

// Runner runs a host command and returns its stdout (at most MaxLogBytes).
type Runner interface {
	Run(ctx context.Context, name string, args ...string) ([]byte, error)
}

// Exec is the production Runner: the real rauc, systemctl and journalctl.
type Exec struct{}

type capped struct {
	bytes.Buffer
}

func (c *capped) Write(p []byte) (int, error) {
	if room := MaxLogBytes - c.Len(); room > 0 {
		c.Buffer.Write(p[:min(len(p), room)])
	}
	return len(p), nil // keep draining so the command does not block
}

// Run implements Runner.
func (Exec) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	var out capped
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout = &out
	err := cmd.Run()
	return out.Bytes(), err
}

// Config wires a Server.
type Config struct {
	TokensFile string
	Version    string
	Runner     Runner
	Logger     *slog.Logger
	Now        func() time.Time // tests
	// Terminal mounts the owner-only web terminal (terminal.go); nil leaves it unmounted.
	Terminal *Terminal
}

// Server is the rescue console's HTTP handler.
type Server struct {
	cfg  Config
	csrf string
	lim  *limiter
	mux  *http.ServeMux
	term termState
}

// New returns the handler. The CSRF token is random per process.
func New(cfg Config) *Server {
	if cfg.Now == nil {
		cfg.Now = time.Now
	}
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	b := make([]byte, 32)
	_, _ = rand.Read(b) // crypto/rand.Read never fails (Go 1.24+)
	s := &Server{cfg: cfg, csrf: hex.EncodeToString(b),
		lim: &limiter{fails: map[string][]time.Time{}, now: cfg.Now, maxFails: 5, window: time.Minute}}
	s.mux = http.NewServeMux()
	s.mux.HandleFunc("GET /{$}", s.page)
	s.mux.HandleFunc("GET /status.json", s.statusJSON)
	s.mux.HandleFunc("GET /logs", s.logs)
	s.mux.HandleFunc("POST /rollback", s.rollback)
	if cfg.Terminal != nil {
		s.mountTerminal()
	}
	return s
}

// ServeHTTP checks LAN origin and the owner credential before any route runs.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	h := w.Header()
	h.Set("Cache-Control", "no-store")
	h.Set("X-Content-Type-Options", "nosniff")
	h.Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
	h.Set("Referrer-Policy", "no-referrer")
	if !lanOnly(r) {
		http.Error(w, "rescue console is LAN-only", http.StatusForbidden)
		return
	}
	ip := clientIP(r)
	if s.lim.blocked(ip) {
		http.Error(w, "too many failed attempts, wait a minute", http.StatusTooManyRequests)
		return
	}
	owners, err := ownerDigests(s.cfg.TokensFile)
	if err != nil || len(owners) == 0 {
		s.cfg.Logger.Error("rescue: no owner credential configured; refusing", "file", s.cfg.TokensFile, "err", err)
		http.Error(w, "no owner credential configured on this box", http.StatusServiceUnavailable)
		return
	}
	tok := presented(r)
	if tok == "" || !matches(tok, owners) {
		if tok != "" && isTerminalPath(r.URL.Path) && matches(tok, nonOwnerDigests(s.cfg.TokensFile)) {
			s.deniedNonOwner(w, r) // a valid credential, but never a shell: 403, not 401
			return
		}
		if tok != "" {
			s.lim.fail(ip)
			s.cfg.Logger.Warn("rescue: wrong owner credential", "client", ip)
		}
		h.Set("WWW-Authenticate", `Basic realm="OneMind rescue (password = owner token)", charset="UTF-8"`)
		http.Error(w, "owner token required", http.StatusUnauthorized)
		return
	}
	s.mux.ServeHTTP(w, r)
}

// Status is what the console shows.
type Status struct {
	Version  string            `json:"onemindd_version"`
	RAUC     heartbeat.RAUC    `json:"rauc"`
	K3s      map[string]string `json:"k3s_units"`
	Errors   []string          `json:"errors,omitempty"`
	CSRF     string            `json:"csrf"`
	Terminal bool              `json:"-"`
}

func (s *Server) status(ctx context.Context) Status {
	st := Status{Version: s.cfg.Version, RAUC: heartbeat.RAUC{Slots: []heartbeat.Slot{}}, K3s: map[string]string{}, CSRF: s.csrf, Terminal: s.cfg.Terminal != nil && SwitchOn(s.cfg.Terminal.SwitchFile)}
	if b, err := s.cfg.Runner.Run(ctx, "rauc", "status", "--output-format=json"); err != nil {
		st.Errors = append(st.Errors, "rauc status: "+err.Error())
	} else {
		st.RAUC = detect.ParseRAUC(b)
	}
	units := []string{"k3s.service", "k3s-agent.service"}
	// is-active exits non-zero for an inactive unit but still prints one state per unit.
	b, _ := s.cfg.Runner.Run(ctx, "systemctl", append([]string{"is-active"}, units...)...)
	lines := strings.Split(strings.TrimSpace(string(b)), "\n")
	for i, u := range units {
		st.K3s[u] = "unknown"
		if i < len(lines) && strings.TrimSpace(lines[i]) != "" {
			st.K3s[u] = strings.TrimSpace(lines[i])
		}
	}
	return st
}

func (s *Server) statusJSON(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(s.status(r.Context()))
}

var pageTmpl = template.Must(template.New("p").Parse(`<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>OneMind rescue</title>
<body style="font-family:sans-serif;max-width:46em;margin:1em auto;padding:0 1em">
<h1>OneMind rescue console</h1>
<p>onemindd {{.Version}}. k3s: {{range $u, $s := .K3s}}{{$u}} <b>{{$s}}</b>; {{end}}</p>
{{range .Errors}}<p role="alert">{{.}}</p>{{end}}
<h2>Slots</h2><p>Booted: <b>{{with .RAUC.BootedSlot}}{{.}}{{else}}unknown{{end}}</b></p>
<table border="1" cellpadding="4"><tr><th>Slot</th><th>Boot name</th><th>State</th><th>Boot status</th><th>Version</th></tr>
{{range .RAUC.Slots}}<tr><td>{{.Name}}</td><td>{{.Bootname}}</td><td>{{.State}}</td><td>{{.BootStatus}}</td><td>{{.BundleVersion}}</td></tr>{{end}}</table>
<h2>Roll back</h2><form method="post" action="rollback">
<p>Boots the other slot (the previous OS version) and restarts the box now.</p>
<input type="hidden" name="csrf" value="{{.CSRF}}">
<label>Type <code>rollback</code> to confirm: <input name="confirm" autocomplete="off" required></label>
<button type="submit">Roll back and restart</button></form>
{{if .Terminal}}<h2>Terminal</h2><p><a href="terminal">Open a shell</a> (owner only, needs a fresh passkey sign-in).</p>{{end}}
<h2>Logs</h2><p><a href="logs">Download recent logs</a> (onemindd, update, health gate, RAUC, k3s).</p>
</body></html>`))

func (s *Server) page(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_ = pageTmpl.Execute(w, s.status(r.Context()))
}

func (s *Server) logs(w http.ResponseWriter, r *http.Request) {
	args := []string{"--no-pager", "-o", "short-iso", "-n", "5000"}
	for _, u := range logUnits {
		args = append(args, "-u", u)
	}
	b, err := s.cfg.Runner.Run(r.Context(), "journalctl", args...)
	if len(b) > MaxLogBytes {
		b = b[:MaxLogBytes]
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="onemind-rescue-logs.txt"`)
	if err != nil && len(b) == 0 {
		http.Error(w, "journalctl: "+err.Error(), http.StatusInternalServerError)
		return
	}
	_, _ = w.Write(b)
}

// ErrNotConfirmed is returned for a rollback POST without the CSRF token or confirmation.
var ErrNotConfirmed = errors.New("rollback needs the page's csrf token and confirm=rollback")

func (s *Server) rollback(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, 4096)
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	if o := r.Header.Get("Origin"); o != "" && o != "https://"+r.Host && o != "http://"+r.Host {
		http.Error(w, "cross-site request refused", http.StatusForbidden)
		return
	}
	if subtle.ConstantTimeCompare([]byte(r.PostForm.Get("csrf")), []byte(s.csrf)) != 1 ||
		strings.TrimSpace(strings.ToLower(r.PostForm.Get("confirm"))) != "rollback" {
		http.Error(w, ErrNotConfirmed.Error(), http.StatusForbidden)
		return
	}
	ctx := r.Context()
	s.cfg.Logger.Warn("rescue: owner requested rollback", "client", clientIP(r))
	if out, err := s.cfg.Runner.Run(ctx, "rauc", "status", "mark-active", "other"); err != nil {
		s.cfg.Logger.Error("rescue: rauc mark-active other failed", "err", err, "out", string(out))
		http.Error(w, "rauc status mark-active other failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = w.Write([]byte("The other slot is marked active. The box restarts now; reconnect in a few minutes.\n"))
	if f, ok := w.(http.Flusher); ok {
		f.Flush()
	}
	// Reboot even if the client goes away: detach from the request context.
	if _, err := s.cfg.Runner.Run(context.WithoutCancel(ctx), "systemctl", "reboot"); err != nil {
		s.cfg.Logger.Error("rescue: systemctl reboot failed", "err", err)
	}
}
