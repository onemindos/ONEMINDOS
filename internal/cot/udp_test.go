// SPDX-License-Identifier: Apache-2.0

package cot

import (
	"context"
	"net"
	"testing"
	"time"
)

// loop sends events through sender into receiver and returns what arrived.
func loop(t *testing.T, r *Receiver, send func(), want int) ([]*Event, Stats) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	got := make(chan *Event, 16)
	done := make(chan error, 1)
	go func() { done <- r.Run(ctx, func(e *Event, _ net.Addr) { got <- e }) }()

	var out []*Event
	tick := time.NewTicker(50 * time.Millisecond)
	defer tick.Stop()
	send()
	for len(out) < want {
		select {
		case e := <-got:
			out = append(out, e)
		case <-tick.C:
			// UDP may drop the first datagrams while the reader starts.
			send()
		case <-ctx.Done():
			t.Fatalf("got %d of %d events before timeout (stats %+v)", len(out), want, r.Stats())
		}
	}
	cancel()
	if err := <-done; err != nil && err != context.Canceled {
		t.Fatalf("Run: %v", err)
	}
	return out, r.Stats()
}

func TestUnicastLoopback(t *testing.T) {
	r, err := NewReceiver("127.0.0.1:0", nil)
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	s, err := NewSender(r.LocalAddr().String(), SenderOptions{})
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	p := machinePos()
	p.Time = time.Now()
	e, err := ToEvent(p)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := net.Dial("udp4", r.LocalAddr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer raw.Close()

	got, st := loop(t, r, func() {
		_, _ = raw.Write([]byte("not cot"))                    // counted as invalid
		_, _ = raw.Write([]byte{ProtoMagic, 0x01, ProtoMagic}) // protocol v1, skipped for now
		if err := s.Send(e); err != nil {
			t.Error(err)
		}
	}, 1)
	if got[0].UID != e.UID || got[0].Point != e.Point {
		t.Fatalf("got %+v", got[0])
	}
	if st.Accepted < 1 || st.Invalid < 1 || st.Protobuf < 1 {
		t.Fatalf("stats %+v", st)
	}
}

func TestSenderRefusesInvalidEvent(t *testing.T) {
	s, err := NewSender("127.0.0.1:9", SenderOptions{})
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	e := validEvent()
	e.Point.Lat = 100
	if err := s.Send(e); err == nil {
		t.Fatal("invalid event sent")
	}
}

// TestMulticastLoopback joins a multicast group on this host and sends to it
// with loopback on and TTL 1. Hosts or sandboxes without a multicast route
// skip it; the unicast test above covers the same code path.
func TestMulticastLoopback(t *testing.T) {
	if testing.Short() {
		t.Skip("short mode")
	}
	// An administratively scoped group and a high port, not the real SA group,
	// so the test never shows up on TAK devices on the developer's network.
	const group = "239.255.77.77:46969"
	r, err := NewReceiver(group, nil)
	if err != nil {
		t.Skipf("no multicast on this host: %v", err)
	}
	defer r.Close()
	s, err := NewSender(group, SenderOptions{Loopback: true})
	if err != nil {
		t.Skipf("no multicast sender on this host: %v", err)
	}
	defer s.Close()
	p := machinePos()
	p.Time = time.Now()
	e, err := ToEvent(p)
	if err != nil {
		t.Fatal(err)
	}
	if err := s.Send(e); err != nil {
		t.Skipf("multicast send failed on this host: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	got := make(chan *Event, 4)
	done := make(chan struct{})
	go func() {
		defer close(done)
		_ = r.Run(ctx, func(e *Event, _ net.Addr) {
			select {
			case got <- e:
			default:
			}
		})
	}()
	defer func() { cancel(); <-done }()
	tick := time.NewTicker(100 * time.Millisecond)
	defer tick.Stop()
	for {
		select {
		case g := <-got:
			if g.UID != e.UID {
				t.Fatalf("got %q", g.UID)
			}
			return
		case <-tick.C:
			_ = s.Send(e)
		case <-ctx.Done():
			t.Skip("multicast loopback not delivered on this host")
		}
	}
}

func TestDefaultSAGroupIsMulticast(t *testing.T) {
	a, err := net.ResolveUDPAddr("udp4", DefaultSAGroup)
	if err != nil || !a.IP.IsMulticast() || a.Port != 6969 {
		t.Fatalf("%v %v", a, err)
	}
}
