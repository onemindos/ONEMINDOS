// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// Event is one onemind.event/v1 envelope from GET /v1/events (contract §12.8). Events carry ids
// and states only: read the full object over REST. Unknown types are delivered as they come.
type Event struct {
	ID      string          `json:"id"`
	Type    string          `json:"type"`
	TS      string          `json:"ts"`
	Subject map[string]any  `json:"subject"`
	Data    map[string]any  `json:"data"`
	ActorID string          `json:"actor_id,omitempty"`
	Raw     json.RawMessage `json:"-"`
}

// EventsService is GET /v1/events.
type EventsService struct{ c *Client }

// SubscribeOptions selects events. Types are globs ("action.*", "node.status").
type SubscribeOptions struct {
	Types []string
	// SinceID resumes after this event id (an audit seq). Empty starts at the live head.
	SinceID string
	// Silence is how long without a byte (keepalives included) before reconnecting (default 45 s).
	Silence time.Duration
}

// Subscribe streams events to fn until ctx ends or fn returns an error. It reconnects with
// backoff (1 s to 30 s, or the server's retry:) and resumes with Last-Event-ID. A "stream.reset"
// event means the resume point was lost: reload state over REST. A 401/403/404 ends the
// subscription with that error (404: the hub has no event stream yet; fall back to polling).
func (s *EventsService) Subscribe(ctx context.Context, o SubscribeOptions, fn func(Event) error) error {
	if o.Silence <= 0 {
		o.Silence = 45 * time.Second
	}
	last, delay := o.SinceID, time.Second
	for {
		retry, err := s.once(ctx, o, &last, fn)
		var e *Error
		switch {
		case ctx.Err() != nil:
			return ctx.Err()
		case errors.As(err, &e) && e.Status >= 400 && e.Status < 500 && e.Status != http.StatusTooManyRequests:
			return err
		case errors.Is(err, errStop):
			return err.(stopErr).cause
		}
		if retry > 0 {
			delay = retry
		}
		if err := s.c.sleep(ctx, delay/2+backoffJitter(delay/2)); err != nil {
			return err
		}
		if delay < 30*time.Second {
			delay *= 2
		}
	}
}

var errStop = errors.New("stop")

type stopErr struct{ cause error }

func (e stopErr) Error() string        { return e.cause.Error() }
func (e stopErr) Is(target error) bool { return target == errStop }

func backoffJitter(d time.Duration) time.Duration {
	if d <= 0 {
		return 0
	}
	return backoff(1) % d
}

func (s *EventsService) once(ctx context.Context, o SubscribeOptions, last *string, fn func(Event) error) (time.Duration, error) {
	s.c.checkTransport()
	q := url.Values{}
	if len(o.Types) > 0 {
		q.Set("types", strings.Join(o.Types, ","))
	}
	path := "/v1/events"
	if enc := q.Encode(); enc != "" {
		path += "?" + enc
	}
	sctx, cancel := context.WithCancel(ctx)
	defer cancel()
	req, err := http.NewRequestWithContext(sctx, http.MethodGet, s.c.base.String()+path, nil)
	if err != nil {
		return 0, err
	}
	token, err := s.c.tokens.Token(ctx)
	if err != nil {
		return 0, err
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("User-Agent", s.c.userAgent)
	if *last != "" {
		req.Header.Set("Last-Event-ID", *last)
	}
	start := time.Now()
	resp, err := s.c.http.Do(req)
	if err != nil {
		s.c.traceCall(request{method: "GET", path: path}, 0, start)
		return 0, &Error{Code: "network", Message: redact(err.Error(), token), cause: ErrNetwork}
	}
	defer resp.Body.Close()
	s.c.traceCall(request{method: "GET", path: path}, resp.StatusCode, start)
	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return 0, apiError(resp, raw)
	}
	// Watchdog: no byte for o.Silence means the connection is dead.
	alive := make(chan struct{}, 1)
	go func() {
		t := time.NewTimer(o.Silence)
		defer t.Stop()
		for {
			select {
			case <-sctx.Done():
				return
			case <-alive:
				if !t.Stop() {
					<-t.C
				}
				t.Reset(o.Silence)
			case <-t.C:
				cancel()
				return
			}
		}
	}()
	var retry time.Duration
	rd := bufio.NewReaderSize(resp.Body, 64*1024)
	var id, typ string
	var data strings.Builder
	for {
		line, err := rd.ReadString('\n')
		if len(line) > 0 {
			select {
			case alive <- struct{}{}:
			default:
			}
		}
		if err != nil {
			return retry, &Error{Code: "network", Message: "event stream closed", cause: ErrNetwork}
		}
		line = strings.TrimRight(line, "\r\n")
		switch {
		case line == "":
			if data.Len() > 0 {
				ev := Event{Raw: json.RawMessage(data.String())}
				_ = json.Unmarshal(ev.Raw, &ev)
				if ev.Type == "" {
					ev.Type = typ
				}
				if id != "" {
					*last = id
				}
				if err := fn(ev); err != nil {
					return 0, stopErr{err}
				}
			}
			id, typ = "", ""
			data.Reset()
		case strings.HasPrefix(line, ":"):
		default:
			k, v, _ := strings.Cut(line, ":")
			v = strings.TrimPrefix(v, " ")
			switch k {
			case "id":
				id = v
			case "event":
				typ = v
			case "data":
				if data.Len() > 0 {
					data.WriteByte('\n')
				}
				data.WriteString(v)
			case "retry":
				if ms, err := strconv.Atoi(v); err == nil {
					retry = time.Duration(ms) * time.Millisecond
				}
			}
		}
	}
}
