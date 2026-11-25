// SPDX-License-Identifier: Apache-2.0

package agent

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"time"

	"github.com/nats-io/nats.go/jetstream"

	"github.com/onemindos/onemindos/internal/leaf"
)

// Durable node events (lab finding, CORE-FABRIC-5 follow-up to #170).
//
// Heartbeats stay latest-wins and unbuffered (see the package doc): an old one replayed later
// would make a node look alive. Node events are different: they are facts ("disk replaced",
// "update staged") that the hub must learn even if the link was cut when they happened. With
// Config.Durable the agent writes each event into the leaf outbox (internal/leaf/outbox.go), which
// the hub drains after the link is back, once per event id. It also writes a compact
// "heartbeat of record" every RecordEvery, so after an outage the hub has the node's history
// during the gap and not only a last_seen jump.

// EventSchema is the "schema" of a durable node event.
const EventSchema = "onemind.node.event/v1"

// DefaultRecordEvery is how often a heartbeat of record is written to the outbox.
const DefaultRecordEvery = 5 * time.Minute

// maxEventBody bounds one event posted to the local API.
const maxEventBody = 64 << 10

var kindRe = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,31}(\.[a-z0-9][a-z0-9_-]{0,31}){0,3}$`)

// Event is the envelope stored in the outbox.
type Event struct {
	Schema string          `json:"schema"`
	ID     string          `json:"id"`
	NodeID string          `json:"node_id"`
	Kind   string          `json:"kind"`
	At     time.Time       `json:"at"`
	Data   json.RawMessage `json:"data,omitempty"`
}

// ErrNotDurable is returned by Emit when the agent runs without durable events.
// ErrBadEvent marks an event the caller got wrong (kind or data), as opposed to a link problem.
var ErrBadEvent = errors.New("bad event")

var ErrNotDurable = errors.New("durable events are off (set ONEMIND_AGENT_DURABLE=1 on a node with a leaf outbox)")

func newEventID() string {
	var b [12]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

func (a *Agent) outbox() (jetstream.JetStream, error) {
	nc := a.conn()
	if nc == nil {
		return nil, errors.New("not connected to the leaf")
	}
	return jetstream.New(nc)
}

// Emit stores one event in the leaf outbox and returns its id. kind is dotted lowercase words
// (for example "disk.replaced"). The message id is made once here, so a retry of the same call
// path by the outbox (lost ack) is deduplicated; the caller must not call Emit twice for one fact.
func (a *Agent) Emit(ctx context.Context, kind string, data json.RawMessage) (string, error) {
	if !a.cfg.Durable {
		return "", ErrNotDurable
	}
	if !kindRe.MatchString(kind) {
		return "", fmt.Errorf("%w: kind %q must be dotted lowercase words", ErrBadEvent, kind)
	}
	if len(data) > 0 && !json.Valid(data) {
		return "", fmt.Errorf("%w: data must be JSON", ErrBadEvent)
	}
	nodeID := a.cfg.Collector.ID()
	ev := Event{Schema: EventSchema, ID: newEventID(), NodeID: nodeID, Kind: kind, At: time.Now().UTC(), Data: data}
	return ev.ID, a.enqueue(ctx, ev)
}

func (a *Agent) enqueue(ctx context.Context, ev Event) error {
	js, err := a.outbox()
	if err != nil {
		return err
	}
	b, err := json.Marshal(ev)
	if err != nil {
		return err
	}
	_, err = leaf.Enqueue(ctx, js, "events."+ev.Kind, b, ev.ID)
	return err
}

// recordHeartbeat writes the current heartbeat into the outbox. Its id is the node and the
// time bucket, so a retry inside one bucket stores it once.
func (a *Agent) recordHeartbeat(ctx context.Context) error {
	st, ok := a.Status(ctx)
	if !ok {
		return ctx.Err()
	}
	b, err := json.Marshal(st)
	if err != nil {
		return err
	}
	every := a.cfg.RecordEvery
	now := time.Now().UTC()
	ev := Event{
		Schema: EventSchema,
		ID:     fmt.Sprintf("hb-%s-%d", st.NodeID, now.UnixMilli()/every.Milliseconds()),
		NodeID: st.NodeID, Kind: "heartbeat", At: now, Data: b,
	}
	return a.enqueue(ctx, ev)
}

// recordLoop makes sure the outbox exists, then records a heartbeat every RecordEvery.
// Failures are logged and retried at the next tick: the agent never dies for this.
func (a *Agent) recordLoop(ctx context.Context) {
	t := time.NewTicker(a.cfg.RecordEvery)
	defer t.Stop()
	for {
		if nc := a.conn(); nc != nil && nc.IsConnected() {
			if js, err := a.outbox(); err == nil {
				if err := leaf.EnsureOutbox(ctx, js, leaf.OutboxConfig{}); err != nil {
					a.log.Warn("outbox not ready", "err", err)
				} else if err := a.recordHeartbeat(ctx); err != nil {
					a.log.Warn("record heartbeat", "err", err)
				}
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
	}
}

// handleEvent serves POST /api/v1/events {"kind": "...", "data": {...}} (loopback API).
func (a *Agent) handleEvent(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, maxEventBody)
	var in struct {
		Kind string          `json:"kind"`
		Data json.RawMessage `json:"data"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "body must be JSON {kind, data}"})
		return
	}
	id, err := a.Emit(r.Context(), in.Kind, in.Data)
	switch {
	case err == nil:
		writeJSON(w, http.StatusAccepted, map[string]string{"id": id})
	case errors.Is(err, ErrBadEvent):
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
	case errors.Is(err, ErrNotDurable):
		writeJSON(w, http.StatusNotFound, map[string]string{"error": err.Error()})
	case errors.Is(err, leaf.ErrOutboxFull):
		writeJSON(w, http.StatusInsufficientStorage, map[string]string{"error": err.Error()})
	default:
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": err.Error()})
	}
}
