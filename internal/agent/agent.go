// Package agent is the running part of onemindd: a small HTTP API on :7480
// and a loop that publishes the heartbeat to NATS every 10 s (contract §1-§2).
//
// Design rule: the agent must never die because the hub is away. NATS being
// down only means heartbeats are skipped (not queued: an old heartbeat
// replayed later would make a node look alive when it was not). The local
// API keeps answering so a person at the box can still see its state.
package agent

import (
	"context"
	"encoding/json"
	"log/slog"
	"net"
	"net/http"
	"sync"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/version"
)

// Defaults from contract §1.
const (
	DefaultListen   = ":7480"
	DefaultInterval = 10 * time.Second
)

// Config configures an Agent.
type Config struct {
	Listen    string        // HTTP listen address, default ":7480"
	NATSURL   string        // empty = do not publish (local API only)
	Interval  time.Duration // heartbeat period, default 10 s
	Collector *detect.Collector
	Logger    *slog.Logger
}

// Agent is a running onemindd.
type Agent struct {
	cfg  Config
	log  *slog.Logger
	mu   sync.Mutex
	last heartbeat.Status
	at   time.Time
	nc   *nats.Conn
	sent uint64
	kick chan struct{} // publish now (after a (re)connect)
}

// New returns an Agent with defaults filled in.
func New(cfg Config) *Agent {
	if cfg.Listen == "" {
		cfg.Listen = DefaultListen
	}
	if cfg.Interval <= 0 {
		cfg.Interval = DefaultInterval
	}
	if cfg.Collector == nil {
		cfg.Collector = detect.New()
	}
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	return &Agent{cfg: cfg, log: cfg.Logger, kick: make(chan struct{}, 1)}
}

// Status returns a heartbeat no older than one second (collection runs a
// few commands, so repeated API calls share one result).
func (a *Agent) Status(ctx context.Context) heartbeat.Status {
	a.mu.Lock()
	defer a.mu.Unlock()
	if time.Since(a.at) < time.Second && a.last.Schema != "" {
		return a.last
	}
	a.last = a.cfg.Collector.Collect(ctx)
	a.at = time.Now()
	return a.last
}

// Handler serves the local API:
//
//	GET /api/v1/node  -> the heartbeat object (contract §2)
//	GET /healthz      -> {"ok":true,"boot_id":...,"agent_version":...,"nats_connected":...}
func (a *Agent) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/node", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, a.Status(r.Context()))
	})
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"ok":             true,
			"boot_id":        a.cfg.Collector.BootID(),
			"agent_version":  version.Version,
			"nats_connected": a.natsConnected(),
		})
	})
	return mux
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(code)
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	_ = enc.Encode(v)
}

func (a *Agent) natsConnected() bool {
	a.mu.Lock()
	nc := a.nc
	a.mu.Unlock()
	return nc != nil && nc.IsConnected()
}

// Sent returns how many heartbeats were published (for tests and logs).
func (a *Agent) Sent() uint64 {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.sent
}

// Run serves HTTP and publishes heartbeats until ctx is cancelled.
// It returns an error only if the HTTP listener cannot be opened.
func (a *Agent) Run(ctx context.Context) error {
	ln, err := net.Listen("tcp", a.cfg.Listen)
	if err != nil {
		return err
	}
	return a.Serve(ctx, ln)
}

// Serve is Run with a listener the caller opened (tests use port 0).
func (a *Agent) Serve(ctx context.Context, ln net.Listener) error {
	srv := &http.Server{Handler: a.Handler(), ReadHeaderTimeout: 5 * time.Second}
	errc := make(chan error, 1)
	go func() { errc <- srv.Serve(ln) }()
	a.log.Info("local API listening", "addr", ln.Addr().String())

	if a.cfg.NATSURL != "" {
		a.connectNATS()
		go a.publishLoop(ctx)
	} else {
		a.log.Warn("ONEMIND_NATS_URL not set: heartbeats are not published, local API only")
	}

	select {
	case <-ctx.Done():
	case err := <-errc:
		return err
	}
	shCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	_ = srv.Shutdown(shCtx)
	a.mu.Lock()
	if a.nc != nil {
		a.nc.Close()
	}
	a.mu.Unlock()
	return nil
}

// connectNATS starts a connection that keeps retrying forever in the
// background, including when the server is down at start-up.
func (a *Agent) connectNATS() {
	nc, err := nats.Connect(a.cfg.NATSURL,
		nats.Name("onemindd/"+version.Version),
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2*time.Second),
		nats.ReconnectBufSize(-1), // do not buffer while disconnected; see package doc
		nats.ConnectHandler(func(*nats.Conn) { a.log.Info("NATS connected"); a.kickPublish() }),
		nats.ReconnectHandler(func(*nats.Conn) { a.log.Info("NATS reconnected"); a.kickPublish() }),
		nats.DisconnectErrHandler(func(_ *nats.Conn, err error) {
			a.log.Warn("NATS disconnected; will keep retrying", "err", err)
		}),
	)
	if err != nil {
		// Only bad URLs/options get here; RetryOnFailedConnect handles "down".
		a.log.Error("NATS connect failed; heartbeats disabled", "err", err)
		return
	}
	a.mu.Lock()
	a.nc = nc
	a.mu.Unlock()
}

// kickPublish asks the loop to publish now, so the hub sees a node as soon
// as the link is up instead of up to one interval later.
func (a *Agent) kickPublish() {
	select {
	case a.kick <- struct{}{}:
	default:
	}
}

func (a *Agent) publishLoop(ctx context.Context) {
	t := time.NewTicker(a.cfg.Interval)
	defer t.Stop()
	for {
		a.publishOnce(ctx)
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		case <-a.kick:
		}
	}
}

func (a *Agent) publishOnce(ctx context.Context) {
	a.mu.Lock()
	nc := a.nc
	a.mu.Unlock()
	if nc == nil || !nc.IsConnected() {
		a.log.Debug("NATS not connected; skipping heartbeat")
		return
	}
	st := a.Status(ctx)
	b, err := json.Marshal(st)
	if err != nil {
		a.log.Error("marshal heartbeat", "err", err)
		return
	}
	if err := nc.Publish(heartbeat.Subject(st.NodeID), b); err != nil {
		a.log.Warn("publish heartbeat", "err", err)
		return
	}
	a.mu.Lock()
	a.sent++
	n := a.sent
	a.mu.Unlock()
	if n == 1 {
		a.log.Info("first heartbeat published", "subject", heartbeat.Subject(st.NodeID))
	}
}
