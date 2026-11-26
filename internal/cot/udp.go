// SPDX-License-Identifier: Apache-2.0

package cot

import (
	"context"
	"errors"
	"fmt"
	"net"
	"sync/atomic"
	"time"

	"golang.org/x/net/ipv4"
)

// DefaultSAGroup is the TAK situational-awareness ("SA") multicast group and
// port that ATAK, iTAK and WinTAK join on a local network by default.
const DefaultSAGroup = "239.2.3.1:6969"

// ProtoMagic is the first byte of a TAK Protocol version 1 (protobuf) packet.
// Version 0 packets are plain XML and start with '<'.
const ProtoMagic = 0xbf

// Sender writes CoT events as UDP datagrams to one address, normally the SA
// multicast group. For a multicast address the TTL is 1 by default, so
// packets stay on the local network and are not routed further.
type Sender struct {
	conn *net.UDPConn
}

// SenderOptions tunes a Sender. The zero value is the safe default.
type SenderOptions struct {
	// TTL for multicast packets. 0 means 1 (LAN only).
	TTL int
	// Interface for multicast packets; nil lets the OS choose.
	Interface *net.Interface
	// Loopback delivers multicast packets to listeners on this host too. Off
	// by default; tests turn it on.
	Loopback bool
}

// NewSender opens a UDP sender to addr ("host:port").
func NewSender(addr string, opt SenderOptions) (*Sender, error) {
	raddr, err := net.ResolveUDPAddr("udp4", addr)
	if err != nil {
		return nil, fmt.Errorf("cot: sender address: %w", err)
	}
	conn, err := net.DialUDP("udp4", nil, raddr)
	if err != nil {
		return nil, fmt.Errorf("cot: sender: %w", err)
	}
	if raddr.IP.IsMulticast() {
		pc := ipv4.NewPacketConn(conn)
		ttl := opt.TTL
		if ttl <= 0 {
			ttl = 1
		}
		if err := pc.SetMulticastTTL(ttl); err != nil {
			conn.Close()
			return nil, fmt.Errorf("cot: multicast ttl: %w", err)
		}
		if err := pc.SetMulticastLoopback(opt.Loopback); err != nil {
			conn.Close()
			return nil, fmt.Errorf("cot: multicast loopback: %w", err)
		}
		if opt.Interface != nil {
			if err := pc.SetMulticastInterface(opt.Interface); err != nil {
				conn.Close()
				return nil, fmt.Errorf("cot: multicast interface: %w", err)
			}
		}
	}
	return &Sender{conn: conn}, nil
}

// Send encodes and writes one event.
func (s *Sender) Send(e *Event) error {
	b, err := Encode(e)
	if err != nil {
		return err
	}
	_, err = s.conn.Write(b)
	return err
}

// Close closes the sender.
func (s *Sender) Close() error { return s.conn.Close() }

// Stats counts what a Receiver saw. Read it with Receiver.Stats.
type Stats struct {
	Accepted  uint64 // valid version-0 events handed to the callback
	Invalid   uint64 // refused by Decode (bad XML, bad fields, too large)
	Protobuf  uint64 // TAK Protocol v1 packets, not decoded yet (phase 6)
	Truncated uint64 // datagrams larger than the read buffer
}

// Receiver reads CoT events from a UDP address. A multicast address is
// joined as a group; any other address is a plain UDP listener.
type Receiver struct {
	conn *net.UDPConn
	now  func() time.Time

	accepted, invalid, protobuf, truncated atomic.Uint64
}

// NewReceiver listens on addr ("host:port"). For a multicast group, ifi picks
// the interface to join on (nil lets the OS choose).
func NewReceiver(addr string, ifi *net.Interface) (*Receiver, error) {
	laddr, err := net.ResolveUDPAddr("udp4", addr)
	if err != nil {
		return nil, fmt.Errorf("cot: receiver address: %w", err)
	}
	var conn *net.UDPConn
	if laddr.IP.IsMulticast() {
		conn, err = net.ListenMulticastUDP("udp4", ifi, laddr)
	} else {
		conn, err = net.ListenUDP("udp4", laddr)
	}
	if err != nil {
		return nil, fmt.Errorf("cot: receiver: %w", err)
	}
	return &Receiver{conn: conn, now: time.Now}, nil
}

// LocalAddr is the address the receiver is bound to.
func (r *Receiver) LocalAddr() net.Addr { return r.conn.LocalAddr() }

// Stats returns the counters so far.
func (r *Receiver) Stats() Stats {
	return Stats{
		Accepted: r.accepted.Load(), Invalid: r.invalid.Load(),
		Protobuf: r.protobuf.Load(), Truncated: r.truncated.Load(),
	}
}

// Run reads datagrams until ctx ends or the receiver is closed, and calls fn
// for each valid event. Invalid packets are counted and dropped; they never
// stop the loop. fn runs on the reading goroutine and must not block long.
func (r *Receiver) Run(ctx context.Context, fn func(*Event, net.Addr)) error {
	stop := context.AfterFunc(ctx, func() { r.conn.Close() })
	defer stop()
	buf := make([]byte, MaxEventBytes+1)
	for {
		n, from, err := r.conn.ReadFromUDP(buf)
		if err != nil {
			if ctx.Err() != nil || errors.Is(err, net.ErrClosed) {
				return ctx.Err()
			}
			return fmt.Errorf("cot: receive: %w", err)
		}
		if n > MaxEventBytes {
			r.truncated.Add(1)
			continue
		}
		if n > 0 && buf[0] == ProtoMagic {
			r.protobuf.Add(1)
			continue
		}
		e, err := Decode(buf[:n], r.now())
		if err != nil {
			r.invalid.Add(1)
			continue
		}
		r.accepted.Add(1)
		fn(e, from)
	}
}

// Close stops the receiver.
func (r *Receiver) Close() error { return r.conn.Close() }
