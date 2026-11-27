// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
)

// The hub's AGENTS account (#627, core/onemind_core/natsconf.py) proven
// against a real in-process nats-server: testdata/hub-accounts-agents.golden.conf
// is what the gateway renders for agents agent:aaa and agent:bbb
// (core/tests/test_agents_nats.py checks it byte for byte, and checks that
// dropping agent bbb removes exactly bbb's line). The two public keys in it
// are swapped for keys made here, whose seeds the two agents sign in with.

type agentsHub struct {
	srv      *server.Server
	url      string
	accounts string
}

func startAgentsHub(t *testing.T, pubA, pubB string) *agentsHub {
	t.Helper()
	dir := t.TempDir()
	golden, err := os.ReadFile(filepath.Join("testdata", "hub-accounts-agents.golden.conf"))
	if err != nil {
		t.Fatal(err)
	}
	h := &agentsHub{accounts: filepath.Join(dir, "accounts.conf")}
	acc := strings.NewReplacer(goldenPubA, pubA, goldenPubB, pubB).Replace(string(golden))
	if err := os.WriteFile(h.accounts, []byte(acc), 0o600); err != nil {
		t.Fatal(err)
	}
	port := freePort(t)
	h.url = fmt.Sprintf("nats://127.0.0.1:%d", port)
	conf := filepath.Join(dir, "hub.conf")
	body := fmt.Sprintf("server_name: hub\nlisten: \"127.0.0.1:%d\"\ninclude \"accounts.conf\"\n", port)
	if err := os.WriteFile(conf, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	h.srv = startServer(t, conf)
	return h
}

// agentConn signs in as one agent and records every permission error the
// server sends it (a refused publish or subscribe arrives asynchronously).
type agentConn struct {
	*nats.Conn
	mu     sync.Mutex
	denied []string
}

func (a *agentConn) refused(what string) bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	for _, d := range a.denied {
		if strings.Contains(d, what) {
			return true
		}
	}
	return false
}

func connectAgent(t *testing.T, url, token string, seed []byte, pub string) (*agentConn, error) {
	t.Helper()
	a := &agentConn{}
	nc, err := nats.Connect(url, nats.Nkey(pub, signerFor(t, seed)), nats.CustomInboxPrefix("_INBOX_"+token),
		nats.ErrorHandler(func(_ *nats.Conn, _ *nats.Subscription, err error) {
			a.mu.Lock()
			a.denied = append(a.denied, err.Error())
			a.mu.Unlock()
		}))
	if err != nil {
		return nil, err
	}
	a.Conn = nc
	t.Cleanup(nc.Close)
	return a, nil
}

func waitRefused(t *testing.T, a *agentConn, what string) {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for !a.refused(what) {
		if time.Now().After(deadline) {
			t.Fatalf("the server never refused %q; errors seen: %v", what, a.denied)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func TestAgentServesPromptAndHeartbeatAndStaysInItsLane(t *testing.T) {
	seedA, pubA := userKey(t)
	seedB, pubB := userKey(t)
	hub := startAgentsHub(t, pubA, pubB)

	// The gateway: a loopback client with no credentials lands in ONEMIND as hub-local.
	gw, err := nats.Connect(hub.url)
	if err != nil {
		t.Fatal(err)
	}
	defer gw.Close()
	core, err := gw.SubscribeSync("onemind.>")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := gw.Subscribe("onemind.request.agent.>", func(m *nats.Msg) {
		_ = m.Respond([]byte("card for " + m.Subject))
	}); err != nil {
		t.Fatal(err)
	}
	hb, err := gw.SubscribeSync("agents.hb.>")
	if err != nil {
		t.Fatal(err)
	}
	gw.Flush()

	a, err := connectAgent(t, hub.url, "aaa", seedA, pubA)
	if err != nil {
		t.Fatal(err)
	}
	b, err := connectAgent(t, hub.url, "bbb", seedB, pubB)
	if err != nil {
		t.Fatal(err)
	}

	// A serves its prompt subject; the gateway asks and gets the answer.
	if _, err := a.Subscribe("agents.prompt.aaa.*.*", func(m *nats.Msg) {
		_ = m.Respond([]byte("answer: " + string(m.Data)))
	}); err != nil {
		t.Fatal(err)
	}
	if err := a.Flush(); err != nil {
		t.Fatal(err)
	}
	reply, err := gw.Request("agents.prompt.aaa.owner.main", []byte("hello"), 3*time.Second)
	if err != nil || string(reply.Data) != "answer: hello" {
		t.Fatalf("prompt to agent aaa: %v %v", reply, err)
	}

	// A's heartbeat reaches the gateway.
	if err := a.Publish("agents.hb.aaa.owner.main", []byte("alive")); err != nil {
		t.Fatal(err)
	}
	m, err := hb.NextMsg(3 * time.Second)
	if err != nil || m.Subject != "agents.hb.aaa.owner.main" {
		t.Fatalf("heartbeat: %v %v", m, err)
	}

	// A asks for something under its own id; the subject names the sender.
	r, err := a.Request("onemind.request.agent.aaa.app_install", []byte("{}"), 3*time.Second)
	if err != nil || string(r.Data) != "card for onemind.request.agent.aaa.app_install" {
		t.Fatalf("request from agent aaa: %v %v", r, err)
	}
	if m, err := core.NextMsg(time.Second); err != nil || m.Subject != "onemind.request.agent.aaa.app_install" {
		t.Fatalf("the gateway should see exactly A's request: %v %v", m, err)
	}

	// No core subject, no other agent's request id, no other agent's heartbeat.
	for _, subj := range []string{"onemind.event.home.door.opened", "onemind.node.aaa111.status",
		"onemind.asset.device.lamp1.state", "onemind.audit", "onemind.request.agent.bbb.app_install",
		"agents.hb.bbb.owner.main"} {
		_ = a.Publish(subj, []byte("forged"))
		waitRefused(t, a, subj)
	}
	if m, err := core.NextMsg(300 * time.Millisecond); err == nil {
		t.Fatalf("a refused publish reached the gateway: %s", m.Subject)
	}
	if m, err := hb.NextMsg(100 * time.Millisecond); err == nil {
		t.Fatalf("A spoke as B: %s", m.Subject)
	}

	// No JetStream API.
	if _, err := a.Request("$JS.API.INFO", nil, time.Second); err == nil {
		t.Fatal("an agent must not reach the JetStream API")
	}
	waitRefused(t, a, "$JS.API.INFO")

	// A cannot listen on B's prompt subject: B still gets its prompts, A gets nothing.
	spy, err := a.SubscribeSync("agents.prompt.bbb.*.*")
	if err != nil {
		t.Fatal(err)
	}
	waitRefused(t, a, "agents.prompt.bbb")
	if _, err := b.Subscribe("agents.prompt.bbb.*.*", func(m *nats.Msg) { _ = m.Respond([]byte("b here")) }); err != nil {
		t.Fatal(err)
	}
	b.Flush()
	if reply, err := gw.Request("agents.prompt.bbb.owner.main", []byte("secret"), 3*time.Second); err != nil || string(reply.Data) != "b here" {
		t.Fatalf("prompt to agent bbb: %v %v", reply, err)
	}
	if m, err := spy.NextMsg(300 * time.Millisecond); err == nil {
		t.Fatalf("A read B's prompt: %s", m.Data)
	}
}

func TestRevokedAgentIsRefusedOnNextConnect(t *testing.T) {
	seedA, pubA := userKey(t)
	seedB, pubB := userKey(t)
	hub := startAgentsHub(t, pubA, pubB)
	if _, err := connectAgent(t, hub.url, "bbb", seedB, pubB); err != nil {
		t.Fatalf("agent bbb before revocation: %v", err)
	}

	// What the gateway writes once the owner removes B's key: the same file without B's line.
	body, err := os.ReadFile(hub.accounts)
	if err != nil {
		t.Fatal(err)
	}
	var kept []string
	for _, line := range strings.SplitAfter(string(body), "\n") {
		if !strings.Contains(line, pubB) {
			kept = append(kept, line)
		}
	}
	if err := os.WriteFile(hub.accounts, []byte(strings.Join(kept, "")), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := hub.srv.Reload(); err != nil {
		t.Fatal(err)
	}

	_, err = connectAgent(t, hub.url, "bbb", seedB, pubB)
	if !errors.Is(err, nats.ErrAuthorization) && (err == nil || !strings.Contains(strings.ToLower(err.Error()), "authorization")) {
		t.Fatalf("revoked agent bbb must be refused, got %v", err)
	}
	if _, err := connectAgent(t, hub.url, "aaa", seedA, pubA); err != nil {
		t.Fatalf("agent aaa must still sign in: %v", err)
	}
}

// #1199 review, D-029 "Stop everything also cuts AI agents off the bus": the
// kill switch rewrites the file without the AGENTS account
// (hub-accounts-agents-stopped.golden.conf, core/tests/test_agents_nats.py)
// and NATS reloads. Agents already connected are cut at that reload, not
// when their credentials run out, and cannot sign in again.
func TestKillSwitchReloadCutsConnectedAgents(t *testing.T) {
	seedA, pubA := userKey(t)
	seedB, pubB := userKey(t)
	hub := startAgentsHub(t, pubA, pubB)
	var conns []*agentConn
	for token, k := range map[string][2]any{"aaa": {seedA, pubA}, "bbb": {seedB, pubB}} {
		a, err := connectAgent(t, hub.url, token, k[0].([]byte), k[1].(string))
		if err != nil {
			t.Fatalf("agent %s before the stop: %v", token, err)
		}
		conns = append(conns, a)
	}
	stopped, err := os.ReadFile(filepath.Join("testdata", "hub-accounts-agents-stopped.golden.conf"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(hub.accounts, stopped, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := hub.srv.Reload(); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(5 * time.Second)
	for _, a := range conns {
		for a.IsConnected() && time.Now().Before(deadline) {
			time.Sleep(20 * time.Millisecond)
		}
		if a.IsConnected() {
			t.Fatal("an agent stayed connected after the kill switch reload")
		}
	}
	if _, err := connectAgent(t, hub.url, "aaa", seedA, pubA); err == nil {
		t.Fatal("agent aaa signed in again while stopped")
	}
}

// A user with no key and no agent key never lands in AGENTS: the
// passwordless loopback user is ONEMIND's, and an unknown nkey is refused.
func TestUnknownAgentKeyIsRefused(t *testing.T) {
	_, pubA := userKey(t)
	_, pubB := userKey(t)
	seedC, pubC := userKey(t)
	hub := startAgentsHub(t, pubA, pubB)
	if _, err := connectAgent(t, hub.url, "ccc", seedC, pubC); err == nil {
		t.Fatal("an agent key the owner never registered must be refused")
	}
}
