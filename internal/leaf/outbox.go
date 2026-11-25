// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// Store-and-forward for a leaf-only node (CORE-FABRIC-5, #170; report ch. 6, Z-07).
//
// A small device (under 4 GB, SD card) joins as a NATS leaf and not as a k3s node. Whatever it
// wants the hub to know goes first into a bounded JetStream stream on its own leaf (the outbox),
// and the hub pulls from that stream (a stream source). Two properties give "every message
// once":
//   - the producer names each message (Nats-Msg-Id), so a retry after a lost acknowledgement is
//     dropped as a duplicate by the outbox;
//   - the hub's source remembers how far it has read, so after an outage it resumes at the next
//     message and neither skips nor repeats one.
//
// This is deliberately not used for heartbeats: those are latest-wins and stay unbuffered
// (internal/agent).

const (
	// OutboxStream is the name of the stream on the leaf.
	OutboxStream = "OUTBOX"
	// OutboxPrefix is the subject prefix of everything in the outbox.
	OutboxPrefix = "outbox."
	// DefaultOutboxMaxBytes bounds the outbox on a small SD card (inside MaxFileStore).
	DefaultOutboxMaxBytes = 128 << 20
	// DefaultOutboxMaxAge is how long an undelivered message is kept.
	DefaultOutboxMaxAge = 7 * 24 * time.Hour
	// DefaultDedupeWindow is how long a message id is remembered for duplicate detection.
	DefaultDedupeWindow = 24 * time.Hour
	// DefaultHubCopyMaxBytes bounds the hub's copy of one leaf's outbox: the registry retention of
	// ONEMIND_NODE_OUTBOX (sdk/schema/onemind.subjects.json, kinds/node). The gateway gives a copy
	// less on a small hub disk (core/onemind_core/jetstream.py node_copy_bytes).
	DefaultHubCopyMaxBytes = 256 << 20
)

// ErrOutboxFull is returned by Enqueue when the outbox is at its byte limit: the message is
// refused, never silently replacing an older one that the hub has not read yet.
var ErrOutboxFull = errors.New("outbox is full: the hub has not collected the backlog yet")

// OutboxConfig sizes the outbox. Zero values mean the defaults.
type OutboxConfig struct {
	MaxBytes int64
	MaxAge   time.Duration
}

// StreamConfig returns the JetStream stream the leaf creates for its outbox.
func (c OutboxConfig) StreamConfig() jetstream.StreamConfig {
	if c.MaxBytes <= 0 {
		c.MaxBytes = DefaultOutboxMaxBytes
	}
	if c.MaxAge <= 0 {
		c.MaxAge = DefaultOutboxMaxAge
	}
	return jetstream.StreamConfig{
		Name:     OutboxStream,
		Subjects: []string{OutboxPrefix + ">"},
		// WorkQueue: a message is removed from the leaf once the hub has stored it, so the outbox
		// holds only what the hub has not collected. On a WorkQueue stream nats-server (v2.15.3)
		// makes the hub's source consumer durable with AckFlowControl: the hub's flow-control reply
		// names the last stream sequence it stored, and only that acknowledges (removes) messages,
		// so an event lost in flight when the link dies stays here (TestHubSourceLosesNothingWhen-
		// TheLinkDiesMidStream). It also keeps messages while no consumer exists yet (Interest
		// would discard them), which is the hub-outage case.
		Retention:  jetstream.WorkQueuePolicy,
		Storage:    jetstream.FileStorage,
		MaxBytes:   c.MaxBytes,
		MaxAge:     c.MaxAge,
		Discard:    jetstream.DiscardNew, // refuse when full, never drop unread messages
		Duplicates: DefaultDedupeWindow,
	}
}

// EnsureOutbox creates the outbox stream, or brings an existing one to cfg.
func EnsureOutbox(ctx context.Context, js jetstream.JetStream, cfg OutboxConfig) error {
	_, err := js.CreateOrUpdateStream(ctx, cfg.StreamConfig())
	return err
}

// HubSourceStream returns the stream the hub creates for one leaf: it sources the leaf's outbox
// through the leaf's JetStream domain (the API prefix routes the requests over the leaf link).
// domain is the leaf's JetStream domain (node-<node_id>, Config.Domain).
//
// The copy keeps the registry retention of node events (#747): DefaultOutboxMaxAge and
// DefaultHubCopyMaxBytes, dropping its own oldest event when full (discard old), so it never refuses
// what the source delivers and one node can fill only its own copy.
func HubSourceStream(domain string) (jetstream.StreamConfig, error) {
	if !nameRe.MatchString(domain) || domain == "hub" {
		return jetstream.StreamConfig{}, fmt.Errorf("bad leaf domain %q", domain)
	}
	return jetstream.StreamConfig{
		Name:      "NODE_" + strings.ReplaceAll(domain, "-", "_") + "_OUTBOX",
		Retention: jetstream.LimitsPolicy,
		Storage:   jetstream.FileStorage,
		MaxBytes:  DefaultHubCopyMaxBytes,
		MaxAge:    DefaultOutboxMaxAge,
		Discard:   jetstream.DiscardOld,
		Sources: []*jetstream.StreamSource{{
			Name:     OutboxStream,
			External: &jetstream.ExternalStream{APIPrefix: "$JS." + domain + ".API"},
		}},
		Duplicates: DefaultDedupeWindow,
	}, nil
}

// Enqueue stores one message in the outbox. id must be unique per message and stable across
// retries (for example a UUID made once when the event happens). The result says whether the
// outbox had already stored this id.
func Enqueue(ctx context.Context, js jetstream.JetStream, suffix string, data []byte, id string) (duplicate bool, err error) {
	if id == "" || len(id) > 128 || strings.ContainsAny(id, " \t\r\n") {
		return false, errors.New("message id is required (1-128 characters, no spaces)")
	}
	if suffix == "" || strings.ContainsAny(suffix, " \t\r\n*>") || strings.HasPrefix(suffix, ".") || strings.HasSuffix(suffix, ".") || strings.Contains(suffix, "..") {
		return false, fmt.Errorf("bad subject %q: dotted words, no wildcards", suffix)
	}
	ack, err := js.Publish(ctx, OutboxPrefix+suffix, data, jetstream.WithMsgID(id))
	if err != nil {
		if errors.Is(err, jetstream.ErrNoStreamResponse) {
			return false, errors.New("the leaf has no outbox yet (run `onemind fabric outbox init`)")
		}
		if strings.Contains(err.Error(), "maximum bytes exceeded") || strings.Contains(err.Error(), "insufficient resources") {
			return false, ErrOutboxFull
		}
		return false, err
	}
	return ack.Duplicate, nil
}

// OutboxStatus is what is waiting in the outbox.
type OutboxStatus struct {
	Messages uint64 `json:"messages"`
	Bytes    uint64 `json:"bytes"`
	MaxBytes int64  `json:"max_bytes"`
	LastSeq  uint64 `json:"last_seq"`
}

// Status reads the outbox's size.
func Status(ctx context.Context, js jetstream.JetStream) (OutboxStatus, error) {
	s, err := js.Stream(ctx, OutboxStream)
	if err != nil {
		return OutboxStatus{}, err
	}
	info, err := s.Info(ctx)
	if err != nil {
		return OutboxStatus{}, err
	}
	return OutboxStatus{Messages: info.State.Msgs, Bytes: info.State.Bytes, MaxBytes: info.Config.MaxBytes, LastSeq: info.State.LastSeq}, nil
}
