// SPDX-License-Identifier: Apache-2.0

package service

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
)

type syncBuf struct {
	mu sync.Mutex
	b  bytes.Buffer
}

func (s *syncBuf) Write(p []byte) (int, error) { s.mu.Lock(); defer s.mu.Unlock(); return s.b.Write(p) }
func (s *syncBuf) String() string              { s.mu.Lock(); defer s.mu.Unlock(); return s.b.String() }

func TestStartRunsEnabledAndSurvivesFailures(t *testing.T) {
	var buf syncBuf
	log := slog.New(slog.NewTextHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug}))
	ctx, cancel := context.WithCancel(context.Background())
	var ran, stopped atomic.Int32
	started := make(chan struct{}, 1)
	svcs := []Service{
		{Name: "loop", Run: func(ctx context.Context, _ *slog.Logger) error {
			ran.Add(1)
			started <- struct{}{}
			<-ctx.Done()
			stopped.Add(1)
			return nil
		}},
		{Name: "off", Enabled: func() bool { return false }, Run: func(context.Context, *slog.Logger) error {
			ran.Add(100)
			return nil
		}},
		{Name: "fails", Run: func(context.Context, *slog.Logger) error { return errors.New("no disk") }},
		{Name: "panics", Run: func(context.Context, *slog.Logger) error { panic("bug") }},
		{Name: "loop", Run: func(context.Context, *slog.Logger) error { ran.Add(1000); return nil }},
		{Name: "", Run: func(context.Context, *slog.Logger) error { return nil }},
	}
	wait := Start(ctx, log, svcs)
	<-started
	cancel()
	wait()
	if ran.Load() != 1 || stopped.Load() != 1 {
		t.Fatalf("ran %d stopped %d", ran.Load(), stopped.Load())
	}
	out := buf.String()
	for _, want := range []string{"service=fails", "no disk", "service=panics", "panic: bug", "service=off", "unique name"} {
		if !strings.Contains(out, want) {
			t.Errorf("log missing %q:\n%s", want, out)
		}
	}
}

func TestStartWithNothing(t *testing.T) {
	Start(context.Background(), slog.New(slog.DiscardHandler), nil)()
}
