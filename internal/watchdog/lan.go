// SPDX-License-Identifier: Apache-2.0

package watchdog

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"strings"
	"time"
)

// DefaultPort is the UDP port peers listen on for hub alerts.
const DefaultPort = 7481

const (
	packetVersion = 1
	maxSkew       = 10 * time.Minute // no internet means no NTP guarantee: allow a wide window
	maxPacket     = 1024
)

// packet is the wire form. Sig is the hex HMAC-SHA256 of the other fields' JSON under the
// shared key (the cluster alert key, a file in the secret store; never sent, never logged).
type packet struct {
	V      int    `json:"v"`
	Kind   string `json:"kind"`
	HubID  string `json:"hub_id"`
	Silent int64  `json:"silent_s"`
	At     int64  `json:"at"`
	Repeat bool   `json:"repeat,omitempty"`
	Sig    string `json:"sig"`
}

func (p packet) mac(key []byte) string {
	q := p
	q.Sig = ""
	b, _ := json.Marshal(q)
	h := hmac.New(sha256.New, key)
	h.Write(b)
	return hex.EncodeToString(h.Sum(nil))
}

// LANPush sends each alert as one signed UDP datagram to every peer ("host:port"). UDP needs no
// connection, so it works with no internet and no hub. Delivery is best effort; the repeat
// reminder covers a lost packet.
type LANPush struct {
	Peers []string
	Key   []byte
}

func (LANPush) Name() string { return "lan-push" }

func (l LANPush) Alert(ctx context.Context, e Event) error {
	if len(l.Key) == 0 {
		return errors.New("no alert key")
	}
	p := packet{V: packetVersion, Kind: e.Kind, HubID: e.HubID, Silent: int64(e.Silent / time.Second), At: e.At.Unix(), Repeat: e.Repeat}
	p.Sig = p.mac(l.Key)
	b, err := json.Marshal(p)
	if err != nil {
		return err
	}
	var errs []string
	var d net.Dialer
	for _, peer := range l.Peers {
		c, err := d.DialContext(ctx, "udp", peer)
		if err != nil {
			errs = append(errs, "peer unreachable")
			continue
		}
		if _, err := c.Write(b); err != nil {
			errs = append(errs, "send failed")
		}
		c.Close()
	}
	if len(errs) > 0 { // never name the peer: no addresses in logs
		return fmt.Errorf("%d of %d peers: %s", len(errs), len(l.Peers), strings.Join(errs, ", "))
	}
	return nil
}

// Listener receives LAN alerts from other machines and hands verified ones to its Alerters.
type Listener struct {
	Key      []byte
	Alerters []Alerter
	Clock    Clock
}

// Parse verifies a datagram: size, version, signature (constant time) and age. It returns the
// event, or an error without echoing the packet.
func (l *Listener) Parse(b []byte) (Event, error) {
	var p packet
	if len(b) > maxPacket || json.Unmarshal(b, &p) != nil || p.V != packetVersion {
		return Event{}, errors.New("malformed alert")
	}
	want, err := hex.DecodeString(p.mac(l.Key))
	got, gerr := hex.DecodeString(p.Sig)
	if err != nil || gerr != nil || len(l.Key) == 0 || !hmac.Equal(want, got) {
		return Event{}, errors.New("bad signature")
	}
	if p.Kind != KindHubDown && p.Kind != KindHubRecovered {
		return Event{}, errors.New("unknown kind")
	}
	clock := l.Clock
	if clock == nil {
		clock = RealClock
	}
	at := time.Unix(p.At, 0)
	if d := clock.Now().Sub(at); d > maxSkew || d < -maxSkew {
		return Event{}, errors.New("stale alert")
	}
	return Event{Kind: p.Kind, HubID: p.HubID, Silent: time.Duration(p.Silent) * time.Second, At: at, Repeat: p.Repeat}, nil
}

// Serve reads datagrams from conn until ctx ends, delivering each verified alert. It closes conn.
func (l *Listener) Serve(ctx context.Context, conn net.PacketConn, onErr func(error)) {
	go func() { <-ctx.Done(); conn.Close() }()
	buf := make([]byte, maxPacket+1)
	for {
		n, _, err := conn.ReadFrom(buf)
		if err != nil {
			return
		}
		e, perr := l.Parse(buf[:n])
		if perr != nil {
			if onErr != nil {
				onErr(perr)
			}
			continue
		}
		for _, a := range l.Alerters {
			if aerr := a.Alert(ctx, e); aerr != nil && onErr != nil {
				onErr(aerr)
			}
		}
	}
}
