// SPDX-License-Identifier: Apache-2.0

package relay

import (
	"context"
	"io"
	"log/slog"
	"net"
	"sync"
	"time"
)

// Router is the relay's whole data path: accept, read the server name, dial the route's upstream,
// replay the bytes already read, then copy both ways. Nothing is logged except the route name
// and counters; payload bytes and client addresses stay out of the log.
type Router struct {
	Routes       map[string]string // exact server name -> upstream host:port
	Dial         func(ctx context.Context, network, addr string) (net.Conn, error)
	HelloTimeout time.Duration // client must send its hello within this time
	DialTimeout  time.Duration
	MaxConns     int // concurrent connections; excess are closed at once
	Log          *slog.Logger

	mu       sync.Mutex
	open     int
	accepted int64 // forwarded
	denied   int64 // closed: unknown or missing name, not TLS
}

// NewRouter builds a Router from a validated config.
func NewRouter(c *Config, log *slog.Logger) *Router {
	rt := map[string]string{}
	for _, r := range c.Routes {
		rt[r.Name] = r.Upstream
	}
	if log == nil {
		log = slog.Default()
	}
	return &Router{Routes: rt, Dial: (&net.Dialer{}).DialContext, HelloTimeout: 10 * time.Second,
		DialTimeout: 10 * time.Second, MaxConns: 512, Log: log}
}

// Serve accepts until ctx ends or the listener fails.
func (r *Router) Serve(ctx context.Context, ln net.Listener) error {
	go func() { <-ctx.Done(); ln.Close() }()
	for {
		c, err := ln.Accept()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		go r.handle(ctx, c)
	}
}

func (r *Router) count(denied bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if denied {
		r.denied++
	} else {
		r.accepted++
	}
}

func (r *Router) handle(ctx context.Context, c net.Conn) {
	defer c.Close()
	r.mu.Lock()
	if r.open >= r.MaxConns {
		r.denied++
		r.mu.Unlock()
		return
	}
	r.open++
	r.mu.Unlock()
	defer func() { r.mu.Lock(); r.open--; r.mu.Unlock() }()

	name, hello, err := PeekServerName(c, r.HelloTimeout)
	upstream, ok := r.Routes[name]
	if err != nil || name == "" || !ok {
		r.count(true)
		r.Log.Info("relay: closed a connection", "reason", denyReason(err, name))
		return
	}
	dctx, cancel := context.WithTimeout(ctx, r.DialTimeout)
	u, err := r.Dial(dctx, "tcp", upstream)
	cancel()
	if err != nil {
		r.count(true)
		r.Log.Warn("relay: upstream unreachable", "route", name)
		return
	}
	defer u.Close()
	if _, err := u.Write(hello); err != nil {
		return
	}
	r.count(false)
	done := make(chan struct{}, 2)
	pipe := func(dst, src net.Conn) {
		_, _ = io.Copy(dst, src)
		done <- struct{}{}
	}
	go pipe(u, c)
	go pipe(c, u)
	<-done // either side ending ends the connection; the deferred closes free the other copy
}

func denyReason(err error, name string) string {
	switch {
	case err != nil:
		return "not_tls"
	case name == "":
		return "no_name"
	default:
		return "unknown_name"
	}
}

// Counts returns how many connections were forwarded and how many were closed.
func (r *Router) Counts() (accepted, denied int64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.accepted, r.denied
}
