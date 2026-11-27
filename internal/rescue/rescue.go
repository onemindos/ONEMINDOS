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
	"os"
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
	// K3sRecoveryFile is what onemind-k3s-state wrote about its last repair ("" = the image's default path).
	K3sRecoveryFile string
	// HelpDir is the offline help pack served read-only under /help/ (help.go); "" serves none.
	HelpDir string
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
	s.mux.HandleFunc("POST /reset-k3s", s.resetK3s)
	s.mux.HandleFunc("GET /help/{path...}", s.help)
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
	Version string            `json:"onemindd_version"`
	RAUC    heartbeat.RAUC    `json:"rauc"`
	K3s     map[string]string `json:"k3s_units"`
	Errors  []string          `json:"errors,omitempty"`
	// K3sRecovery is the last automatic repair of k3s's state ("repaired", "needs-approval", "reset", "partial",
	// "not-checked") and when; "needs-approval" means the owner's apps are (or may be) in the cluster, nothing was
	// moved and k3s is held until the owner approves the reset (VM 501 bug 1).
	K3sRecovery *K3sRecovery `json:"k3s_recovery,omitempty"`
	CSRF        string       `json:"csrf"`
	Terminal    bool         `json:"-"`
	Help        bool         `json:"-"`
}

// DefaultK3sRecoveryFile is where onemind-k3s-state records its last repair.
const DefaultK3sRecoveryFile = "/data/onemind/k3s-recovery/last.json"

// K3sRecovery is the part of that record the console shows.
type K3sRecovery struct {
	Action string `json:"action"`
	At     string `json:"at"`
	Reason string `json:"reason,omitempty"`
}

func (s *Server) k3sRecovery() *K3sRecovery {
	path := s.cfg.K3sRecoveryFile
	if path == "" {
		path = DefaultK3sRecoveryFile
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var r K3sRecovery
	if json.Unmarshal(b, &r) != nil || r.Action == "" {
		return nil
	}
	return &r
}

func (s *Server) status(ctx context.Context) Status {
	st := Status{Version: s.cfg.Version, RAUC: heartbeat.RAUC{Slots: []heartbeat.Slot{}}, K3s: map[string]string{}, CSRF: s.csrf, Terminal: s.cfg.Terminal != nil && SwitchOn(s.cfg.Terminal.SwitchFile),
		Help: s.hasHelp(), K3sRecovery: s.k3sRecovery()}
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
<h2>Reset k3s state</h2>
{{with .K3sRecovery}}<p{{if eq .Action "needs-approval"}} role="alert"{{end}}>Last k3s state repair: <b>{{.Action}}</b> at {{.At}}.{{with .Reason}} {{.}}.{{end}}{{if eq .Action "needs-approval"}} k3s is held (not started) until you decide, so nothing writes over its old state; your apps do not run meanwhile.{{end}}</p>{{end}}
<form method="post" action="reset-k3s">
<p>Use this when Kubernetes (k3s) will not start after a power cut. It moves k3s's generated state (certificates, tokens, node password and its datastore) aside under <code>/data/onemind/k3s-recovery/</code> and starts k3s again, which makes them anew. Your files, the apps' volumes and the gateway database are not touched. Apps that ran in k3s are not set up again on their own: install them again once k3s is back. Their old data stays on the disk under <code>/data/k3s/storage/</code>, but a new install gets new, empty volumes.</p>
<input type="hidden" name="csrf" value="{{.CSRF}}">
<label>Type <code>reset k3s</code> to confirm: <input name="confirm" autocomplete="off" required></label>
<button type="submit">Reset k3s state</button></form>
{{if .Terminal}}<h2>Terminal</h2><p><a href="terminal">Open a shell</a> (owner only, needs a fresh passkey sign-in).</p>{{end}}
<h2>Logs</h2><p><a href="logs">Download recent logs</a> (onemindd, update, health gate, RAUC, k3s).</p>
{{if .Help}}<h2>Help</h2><p><a href="help/">Offline help</a>: what to do when the box is in trouble. It works with the gateway down.</p>{{end}}
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

// ErrResetNotConfirmed is returned for a reset POST without the CSRF token or the typed confirmation.
var ErrResetNotConfirmed = errors.New("reset needs the page's csrf token and confirm=reset k3s")

// resetK3s is the owner-approved "Reset k3s state": it only starts onemind-k3s-reset.service (the console's own
// sandbox is read-only); that unit stops k3s, moves its generated state aside and starts it again.
func (s *Server) resetK3s(w http.ResponseWriter, r *http.Request) {
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
		strings.Join(strings.Fields(strings.ToLower(r.PostForm.Get("confirm"))), " ") != "reset k3s" {
		http.Error(w, ErrResetNotConfirmed.Error(), http.StatusForbidden)
		return
	}
	s.cfg.Logger.Warn("rescue: owner approved a k3s state reset", "client", clientIP(r))
	if out, err := s.cfg.Runner.Run(r.Context(), "systemctl", "start", "--no-block", "onemind-k3s-reset.service"); err != nil {
		s.cfg.Logger.Error("rescue: starting onemind-k3s-reset failed", "err", err, "out", string(out))
		http.Error(w, "could not start the reset: "+err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = w.Write([]byte("k3s state reset started. k3s restarts and makes its state again; reload this page in a minute or two. Then install your apps again: their old data stays under /data/k3s/storage/.\n"))
}
