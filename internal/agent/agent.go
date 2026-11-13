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
	"sync/atomic"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/onemindos/onemindos/internal/detect"
	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/mesh"
	"github.com/onemindos/onemindos/internal/version"
)

// Defaults from contract §1. The local API listens on loopback only (hardening H-24): it has no
// authentication, and the hub learns the same data from heartbeats. Set ONEMIND_AGENT_ADDR=:7480
// to listen on every interface (the compose demo does, inside its container).
const (
	DefaultListen   = "127.0.0.1:7480"
	DefaultInterval = 10 * time.Second
)

// Config configures an Agent.
type Config struct {
	Listen    string        // HTTP listen address, default "127.0.0.1:7480"
	NATSURL   string        // empty = do not publish (local API only)
	Interval  time.Duration // heartbeat period, default 10 s
	Collector *detect.Collector
	Logger    *slog.Logger
	// UpdateReport, when set, supplies the optional "update" object of the
	// heartbeat (read from the update service's status file). nil = omit.
	UpdateReport func() *heartbeat.Update
	// MeshReport and FabricReport supply the optional "mesh" and "fabric"
	// objects (contract §12.10). nil, or a nil result, omits them.
	MeshReport   func() *mesh.Heartbeat
	FabricReport func() *heartbeat.Fabric
	// Mounts adds optional services' HTTP APIs under their path prefix (service.Mounts).
	Mounts map[string]http.Handler
}

// Agent is a running onemindd.
type Agent struct {
	cfg Config
	log *slog.Logger

	stMu     sync.Mutex // guards last, at, inflight; never held during Collect
	last     heartbeat.Status
	at       time.Time
	inflight *collection

	ncMu sync.Mutex // guards nc
	nc   *nats.Conn

	sent atomic.Uint64
	kick chan struct{} // publish now (after a (re)connect)
}

// collection is one in-flight Collect that concurrent callers share.
type collection struct {
	done chan struct{}
	st   heartbeat.Status
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
// few commands, so repeated API calls share one result, and concurrent
// callers share one in-flight collection).
//
// The collection runs detached from ctx: a client that hangs up mid-collect
// must not leave a degraded snapshot (k3s not ready, no RAUC slots, no GPU
// model) in the cache, where it would be published as truth. Each command
// still has the collector's own timeout. If ctx ends first, Status returns
// the last cached heartbeat (which may be stale or empty) and ok = false.
func (a *Agent) Status(ctx context.Context) (st heartbeat.Status, ok bool) {
	a.stMu.Lock()
	if time.Since(a.at) < time.Second && a.last.Schema != "" {
		st = a.last
		a.stMu.Unlock()
		return st, true
	}
	c := a.inflight
	if c == nil {
		c = &collection{done: make(chan struct{})}
		a.inflight = c
		go a.collect(c)
	}
	a.stMu.Unlock()

	select {
	case <-c.done:
		return c.st, true
	case <-ctx.Done():
		a.stMu.Lock()
		defer a.stMu.Unlock()
		return a.last, false
	}
}

func (a *Agent) collect(c *collection) {
	c.st = a.cfg.Collector.Collect(context.Background())
	if a.cfg.UpdateReport != nil {
		c.st.Update = a.cfg.UpdateReport()
	}
	if a.cfg.MeshReport != nil {
		c.st.Mesh = a.cfg.MeshReport()
	}
	if a.cfg.FabricReport != nil {
		c.st.Fabric = a.cfg.FabricReport()
	}
	a.stMu.Lock()
	a.last, a.at, a.inflight = c.st, time.Now(), nil
	a.stMu.Unlock()
	close(c.done)
}

// Handler serves the local API:
//
//	GET /api/v1/node  -> the heartbeat object (contract §2)
//	GET /healthz      -> {"ok":true,"boot_id":...,"agent_version":...,"nats_connected":...}
func (a *Agent) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/node", func(w http.ResponseWriter, r *http.Request) {
		st, ok := a.Status(r.Context())
		if !ok {
			return // the client went away
		}
		writeJSON(w, http.StatusOK, st)
	})
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"ok":             true,
			"boot_id":        a.cfg.Collector.BootID(),
			"agent_version":  version.Version,
			"nats_connected": a.natsConnected(),
		})
	})
	for prefix, h := range a.cfg.Mounts {
		mux.Handle(prefix, h)
	}
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

func (a *Agent) conn() *nats.Conn {
	a.ncMu.Lock()
	defer a.ncMu.Unlock()
	return a.nc
}

func (a *Agent) natsConnected() bool {
	nc := a.conn()
	return nc != nil && nc.IsConnected()
}

// Sent returns how many heartbeats were published (for tests and logs).
func (a *Agent) Sent() uint64 { return a.sent.Load() }

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
	if nc := a.conn(); nc != nil {
		nc.Close()
	}
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
	a.ncMu.Lock()
	a.nc = nc
	a.ncMu.Unlock()
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
	nc := a.conn()
	if nc == nil || !nc.IsConnected() {
		a.log.Debug("NATS not connected; skipping heartbeat")
		return
	}
	st, ok := a.Status(ctx)
	if !ok {
		return // shutting down
	}
	b, err := json.Marshal(st)
	if err != nil {
		a.log.Error("marshal heartbeat", "err", err)
		return
	}
	if err := nc.Publish(heartbeat.Subject(st.NodeID), b); err != nil {
		a.log.Warn("publish heartbeat", "err", err)
		return
	}
	if a.sent.Add(1) == 1 {
		a.log.Info("first heartbeat published", "subject", heartbeat.Subject(st.NodeID))
	}
}
