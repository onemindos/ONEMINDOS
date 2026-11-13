// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"path/filepath"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/agent"
	"github.com/onemindos/onemindos/internal/detect"
)

func fixture(board string) string {
	return filepath.Join("..", "..", "..", "internal", "detect", "testdata", board)
}

// The simulated machines report the contract §2 board of their fixture tree.
func TestFixtureBoards(t *testing.T) {
	for _, tc := range []struct{ dir, board string }{{"rpi5", "rpi5"}, {"jetson", "jetson-orin"}} {
		col := detect.NewFixture(fixture(tc.dir), "arm64")
		if got := col.Board(); got != tc.board {
			t.Errorf("%s: board %q, want %q", tc.dir, got, tc.board)
		}
	}
}

// The local API serves onemindd's §2 heartbeat for the fixture (same code path as onemindd).
func TestServesHeartbeat(t *testing.T) {
	col := detect.NewFixture(fixture("rpi5"), "arm64")
	col.NodeID = "compose-sim-rpi5"
	col.Hostname = "sim-pi5"
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	a := agent.New(agent.Config{Collector: col, Interval: time.Hour})
	go func() { _ = a.Serve(ctx, ln) }()
	var hb map[string]any
	for i := 0; i < 50; i++ {
		resp, err := http.Get("http://" + ln.Addr().String() + "/api/v1/node")
		if err == nil {
			err = json.NewDecoder(resp.Body).Decode(&hb)
			resp.Body.Close()
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if hb["schema"] != "onemind.node.status/v1" || hb["node_id"] != "compose-sim-rpi5" || hb["board"] != "rpi5" || hb["hostname"] != "sim-pi5" {
		t.Fatalf("unexpected heartbeat: %v", hb)
	}
}

func TestCheck(t *testing.T) {
	if err := check(fixture("rpi5"), "arm64", "node", ""); err != nil {
		t.Fatal(err)
	}
	for _, bad := range [][4]string{
		{"", "arm64", "node", ""},
		{fixture("rpi5"), "riscv64", "node", ""},
		{fixture("rpi5"), "arm64", "king", ""},
		{fixture("rpi5"), "arm64", "node", "bad id!"},
		{"/nonexistent-fixture", "arm64", "node", ""},
	} {
		if check(bad[0], bad[1], bad[2], bad[3]) == nil {
			t.Errorf("check(%q) accepted", bad)
		}
	}
}
