// SPDX-License-Identifier: Apache-2.0

// Package service runs onemindd's optional services next to the heartbeat
// agent (docs/leap/core/PLUMBING.md §7). A feature package exposes a
// constructor returning a Service; cmd/onemindd/registry.go lists it in one line.
//
// An optional service must never take the heartbeat down: a service that
// returns an error or panics is logged and stays stopped, and the agent keeps
// running. Every service gets the same context, cancelled on SIGINT/SIGTERM or
// when the agent stops.
package service

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
)

// Service is one optional long-running part of onemindd.
type Service struct {
	// Name appears in logs as service=<Name>; lower-case, unique.
	Name string
	// Enabled reports whether this box runs the service (usually from an
	// ONEMIND_* variable or a config file). nil means always.
	Enabled func() bool
	// Run blocks until ctx is done (return nil) or the service fails.
	Run func(ctx context.Context, log *slog.Logger) error
	// Mount and Handler, when both are set, put the service's HTTP API on the agent's local
	// API under the path prefix Mount (for example "/api/v1/backup/"). Handler is called once,
	// before the agent starts listening, only for an enabled service.
	Mount   string
	Handler func(ctx context.Context) http.Handler
}

// Mounts returns the HTTP handlers of the enabled services by path prefix.
func Mounts(ctx context.Context, services []Service) map[string]http.Handler {
	out := map[string]http.Handler{}
	for _, s := range services {
		if s.Mount == "" || s.Handler == nil || (s.Enabled != nil && !s.Enabled()) {
			continue
		}
		if _, dup := out[s.Mount]; !dup {
			out[s.Mount] = s.Handler(ctx)
		}
	}
	return out
}

// Start launches every enabled service in its own goroutine and returns a
// function that waits for all of them to return. Cancel ctx first.
func Start(ctx context.Context, log *slog.Logger, services []Service) (wait func()) {
	var wg sync.WaitGroup
	seen := map[string]bool{}
	for _, s := range services {
		if s.Name == "" || s.Run == nil || seen[s.Name] {
			log.Error("optional service skipped: needs a unique name and a Run func", "service", s.Name)
			continue
		}
		seen[s.Name] = true
		if s.Enabled != nil && !s.Enabled() {
			log.Debug("optional service disabled", "service", s.Name)
			continue
		}
		wg.Add(1)
		go func(s Service) {
			defer wg.Done()
			l := log.With("service", s.Name)
			l.Info("optional service starting")
			if err := runSafely(ctx, l, s); err != nil {
				l.Error("optional service stopped with an error; the agent keeps running", "err", err)
				return
			}
			l.Info("optional service stopped")
		}(s)
	}
	return wg.Wait
}

func runSafely(ctx context.Context, log *slog.Logger, s Service) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("panic: %v", r)
		}
	}()
	return s.Run(ctx, log)
}
