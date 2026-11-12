// SPDX-License-Identifier: Apache-2.0

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/mesh"
)

// fakeTS answers `tailscale status --json` with a fixed document (example
// mesh addresses from 100.64.0.0/10).
type fakeTS struct{ out string }

func (f fakeTS) Run(context.Context, ...string) ([]byte, error) { return []byte(f.out), nil }

func TestMeshStatus(t *testing.T) {
	old := newMeshClient
	defer func() { newMeshClient = old }()
	newMeshClient = func() *mesh.Client {
		return &mesh.Client{Runner: fakeTS{`{"BackendState":"Running","Self":{"TailscaleIPs":["100.64.0.5"]},` +
			`"Peer":{"k":{"HostName":"hub","Tags":["tag:onemind-hub"],"CurAddr":"203.0.113.10:41641","Online":true}}}`}, Now: time.Now}
	}
	l, _ := net.Listen("tcp", "127.0.0.1:0")
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"leafnodes":1,"leafs":[{"name":"hub","rtt":"1.2ms"}]}`))
	})}
	go srv.Serve(l)
	defer srv.Close()

	var out bytes.Buffer
	if err := meshCmd([]string{"status", "--leaf-monitor", l.Addr().String()}, &out); err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"state:", "up", "100.64.0.5", "hub: direct", "nats leaf: up (rtt 1.2ms)"} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("missing %q in:\n%s", want, out.String())
		}
	}
	out.Reset()
	if err := meshCmd([]string{"status", "--json", "--leaf-monitor", l.Addr().String()}, &out); err != nil {
		t.Fatal(err)
	}
	var v struct {
		Mesh mesh.State
		Leaf struct{ State string }
	}
	if err := json.Unmarshal(out.Bytes(), &v); err != nil || v.Mesh.State != "up" || v.Leaf.State != "up" {
		t.Fatalf("%v %+v", err, v)
	}
	if err := meshCmd(nil, &out); err == nil {
		t.Fatal("missing subcommand accepted")
	}
}
