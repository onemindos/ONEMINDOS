// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestMonitorLink(t *testing.T) {
	dir := t.TempDir()
	conf := filepath.Join(dir, "leaf.conf")
	l, _ := net.Listen("tcp", "127.0.0.1:0")
	up := true
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if up {
			w.Write([]byte(`{"leafnodes":1,"leafs":[{"name":"hub","rtt":"2ms"}]}`))
		} else {
			w.Write([]byte(`{"leafnodes":0,"leafs":[]}`))
		}
	})}
	go srv.Serve(l)
	defer srv.Close()
	m := NewMonitor(conf, l.Addr().String())
	if m.Service().Enabled() {
		t.Fatal("enabled without a leaf.conf")
	}
	if m.Link() != "none" {
		t.Fatal("unchecked monitor must report none")
	}
	os.WriteFile(conf, []byte("#"), 0o600)
	if !m.Service().Enabled() {
		t.Fatal("not enabled with a leaf.conf")
	}
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hc := &http.Client{Timeout: time.Second}
	m.check(context.Background(), hc, log)
	if m.Link() != "up" || m.Last().RTT != "2ms" {
		t.Fatalf("%s %+v", m.Link(), m.Last())
	}
	up = false
	m.check(context.Background(), hc, log)
	if m.Link() != "down" {
		t.Fatal(m.Link())
	}
}
