// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// G1 (NATS-ROLE-AND-GATEWAY N1): the local leaf of a joined machine has no passwordless user.

func machineConfig(t *testing.T) *Config {
	t.Helper()
	c := validConfig()
	progs, err := MachinePrograms("3f9c2a1b7d4e", map[string]string{ProgramOnemindd: goldenPubOnemindd, ProgramCLI: goldenPubCLI})
	if err != nil {
		t.Fatal(err)
	}
	c.Local = progs
	return c
}

func TestMachineProgramsRenderExactPermissions(t *testing.T) {
	got, err := machineConfig(t).Render("/etc/onemind/nats/leaf.conf")
	if err != nil {
		t.Fatal(err)
	}
	want := `authorization {
  users: [
    {nkey: "` + goldenPubOnemindd + `", permissions: {publish: {allow: ["onemind.node.3f9c2a1b7d4e.status", "onemind.node.3f9c2a1b7d4e.event.>", "onemind.node.3f9c2a1b7d4e.jobresult.>", "outbox.>", "$JS.API.STREAM.CREATE.OUTBOX", "$JS.API.STREAM.UPDATE.OUTBOX", "$JS.API.STREAM.INFO.OUTBOX"]}, subscribe: {allow: ["_INBOX_onemindd.>", "onemind.node.3f9c2a1b7d4e.status"]}}}  # onemindd
    {nkey: "` + goldenPubCLI + `", permissions: {publish: {allow: ["outbox.>", "$JS.API.STREAM.CREATE.OUTBOX", "$JS.API.STREAM.UPDATE.OUTBOX", "$JS.API.STREAM.INFO.OUTBOX"]}, subscribe: {allow: ["_INBOX_cli.>"]}}}  # cli
  ]
}
`
	if !strings.Contains(string(got), want) {
		t.Fatalf("authorization block mismatch:\n%s", got)
	}
	for _, bad := range []string{"no_auth_user", "password:", "token:", "{user:", `allow: [">"]`, `allow: ["onemind.>"]`} {
		if strings.Contains(string(got), bad) {
			t.Fatalf("rendered config contains %q:\n%s", bad, got)
		}
	}
}

func TestRenderRefusesAnonymousLocalAccess(t *testing.T) {
	c := validConfig()
	c.Local = nil
	if _, err := c.Render("/etc/onemind/nats/leaf.conf"); err == nil || !strings.Contains(err.Error(), "no local program keys") {
		t.Fatalf("a leaf with no local keys must not render, got %v", err)
	}
	for name, mod := range map[string]func(*LocalProgram){
		"match-all publish": func(p *LocalProgram) { p.Publish = []string{">"} },
		"star subscribe":    func(p *LocalProgram) { p.Subscribe = []string{"*"} },
		"no publish":        func(p *LocalProgram) { p.Publish = nil },
		"quote in subject":  func(p *LocalProgram) { p.Publish = []string{`a"b`} },
		"bad key":           func(p *LocalProgram) { p.PublicKey = "nope" },
		"account key":       func(p *LocalProgram) { p.PublicKey = "AAAA" },
		"bad name":          func(p *LocalProgram) { p.Name = "a b" },
	} {
		c := machineConfig(t)
		mod(&c.Local[0])
		if _, err := c.Render("/etc/onemind/nats/leaf.conf"); err == nil {
			t.Errorf("%s: rendered", name)
		}
	}
	c = machineConfig(t)
	c.Local[1].PublicKey = c.Local[0].PublicKey
	if _, err := c.Render("/etc/onemind/nats/leaf.conf"); err == nil {
		t.Error("the same key twice was accepted")
	}
	if _, err := MachinePrograms("3f9c2a1b7d4e", map[string]string{ProgramOnemindd: goldenPubOnemindd}); err == nil {
		t.Error("MachinePrograms without a cli key was accepted")
	}
}

func TestCheckLocalAuth(t *testing.T) {
	good, _ := machineConfig(t).Render("/etc/onemind/nats/leaf.conf")
	if err := CheckLocalAuth(good); err != nil {
		t.Fatal(err)
	}
	for name, conf := range map[string]string{
		"the old config":     strings.Split(string(good), "# Local sign-in")[0],
		"no_auth_user":       string(good) + "no_auth_user: \"sensor\"\n",
		"commented-out auth": strings.ReplaceAll(string(good), "authorization {", "# authorization {"),
	} {
		if CheckLocalAuth([]byte(conf)) == nil && name != "commented-out auth" {
			t.Errorf("%s was accepted", name)
		}
	}
	if CheckLocalAuth([]byte(strings.ReplaceAll(string(good), "authorization {", "# authorization {"))) == nil {
		t.Error("a commented-out authorization block was accepted")
	}
	// A comment that mentions the word must not trigger the refusal.
	if err := CheckLocalAuth([]byte(string(good) + "# no_auth_user is gone\n")); err != nil {
		t.Errorf("a comment tripped the check: %v", err)
	}
}

func TestWriteLocalSeedKeepsAnExistingKey(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "nats-local")
	pub1, err := WriteLocalSeed(dir, ProgramOnemindd)
	if err != nil {
		t.Fatal(err)
	}
	pub2, err := WriteLocalSeed(dir, ProgramOnemindd)
	if err != nil || pub1 != pub2 {
		t.Fatalf("second call changed the key: %v %s %s", err, pub1, pub2)
	}
	pub3, _ := WriteLocalSeed(dir, ProgramCLI)
	if pub3 == pub1 {
		t.Fatal("two programs share a key")
	}
	fi, err := os.Stat(filepath.Join(dir, "onemindd.nk"))
	if err != nil || fi.Mode().Perm() != 0o600 {
		t.Fatalf("seed file: %v %v", err, fi)
	}
	if di, _ := os.Stat(dir); di.Mode().Perm() != 0o700 {
		t.Fatalf("seed dir mode %o", di.Mode().Perm())
	}
	if _, err := WriteLocalSeed(dir, "../x"); err == nil {
		t.Fatal("a path in the program name was accepted")
	}
}

// The real thing: a node leaf rendered with MachinePrograms, linked to a hub with per-node
// accounts. An unauthenticated local client is refused; onemindd, signed in with its own seed,
// publishes its status to the hub and runs the outbox; no program can step outside its list.
func TestLocalLeafRefusesAnonymousAndKeepsEachProgramToItsSubjects(t *testing.T) {
	dir := t.TempDir()
	seedA, pubA := userKey(t)
	_, pubB := userKey(t)
	hub := startAccountsHub(t, dir, pubA, pubB)

	nd := filepath.Join(dir, "aaa111")
	nkeyFile := filepath.Join(nd, "leaf.nkey")
	if _, err := WriteNkeyFile(nkeyFile, seedA); err != nil {
		t.Fatal(err)
	}
	keys := filepath.Join(nd, LocalKeysDirName)
	pubs := map[string]string{}
	for _, n := range []string{ProgramOnemindd, ProgramCLI} {
		p, err := WriteLocalSeed(keys, n)
		if err != nil {
			t.Fatal(err)
		}
		pubs[n] = p
	}
	progs, err := MachinePrograms("aaa111", pubs)
	if err != nil {
		t.Fatal(err)
	}
	c := &Config{
		ServerName: "node-aaa111", Listen: fmt.Sprintf("127.0.0.1:%d", freePort(t)),
		Monitor: fmt.Sprintf("127.0.0.1:%d", freePort(t)), StoreDir: filepath.Join(nd, "store"),
		HubURLs: []string{fmt.Sprintf("tls://127.0.0.1:%d", hub.leafPort)}, CAFile: hub.pki.caFile, NkeyFile: nkeyFile,
		Local: progs,
	}
	c.CertFile, c.KeyFile = hub.pki.issue(t, "node-aaa111", false)
	confPath := filepath.Join(nd, "leaf.conf")
	if _, err := Apply(confPath, c); err != nil {
		t.Fatal(err)
	}
	startServer(t, confPath)
	s := &Supervisor{ConfPath: confPath, Config: c}
	if h := waitHealth(t, s, StateUp, 15*time.Second); h.State != StateUp {
		t.Fatalf("leaf never connected: %+v", h)
	}
	url := "nats://" + c.Listen

	// 1. Anonymous: refused, and so is an unknown key.
	if nc, err := nats.Connect(url); err == nil {
		nc.Close()
		t.Fatal("a local client with no key was accepted")
	}
	strangerSeed, _ := userKey(t)
	if nc, err := nats.Connect(url, nats.Nkey(mustPub(t, strangerSeed), signerFor(t, strangerSeed))); err == nil {
		nc.Close()
		t.Fatal("a local client with an unlisted key was accepted")
	}
	if nc, err := nats.Connect(url, nats.UserInfo("sensor", "")); err == nil {
		nc.Close()
		t.Fatal("a passwordless user name was accepted")
	}

	connect := func(name string) *nats.Conn {
		opts, err := ClientOptions(name, filepath.Join(keys, name+".nk"))
		if err != nil {
			t.Fatal(err)
		}
		nc, err := nats.Connect(url, append(opts, nats.Timeout(5*time.Second))...)
		if err != nil {
			t.Fatalf("%s could not sign in: %v", name, err)
		}
		t.Cleanup(nc.Close)
		return nc
	}
	od, cli := connect(ProgramOnemindd), connect(ProgramCLI)

	// 2. onemindd's own status reaches the hub (the gateway's loopback user sees it).
	gw, err := nats.Connect(hub.client)
	if err != nil {
		t.Fatal(err)
	}
	defer gw.Close()
	got := make(chan string, 64)
	if _, err := gw.Subscribe("onemind.node.*.status", func(m *nats.Msg) { got <- m.Subject + "=" + string(m.Data) }); err != nil {
		t.Fatal(err)
	}
	gw.Flush()
	deadline := time.Now().Add(10 * time.Second)
	for ok := false; !ok; {
		_ = od.Publish("onemind.node.aaa111.status", []byte("hb"))
		od.Flush()
		select {
		case m := <-got:
			ok = m == "onemind.node.aaa111.status=hb"
		case <-time.After(150 * time.Millisecond):
		}
		if time.Now().After(deadline) {
			t.Fatal("onemindd's heartbeat never reached the hub through the leaf")
		}
	}

	// 3. The outbox works for onemindd and for the CLI with only their lists.
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	jsOD, err := jetstream.New(od)
	if err != nil {
		t.Fatal(err)
	}
	if err := EnsureOutbox(ctx, jsOD, OutboxConfig{}); err != nil {
		t.Fatalf("onemindd cannot create the outbox: %v", err)
	}
	if err := EnsureOutbox(ctx, jsOD, OutboxConfig{MaxBytes: 64 << 20}); err != nil { // the update path
		t.Fatalf("onemindd cannot update the outbox: %v", err)
	}
	if _, err := Enqueue(ctx, jsOD, "events.test", []byte("x"), "id-1"); err != nil {
		t.Fatalf("onemindd cannot enqueue: %v", err)
	}
	jsCLI, err := jetstream.New(cli)
	if err != nil {
		t.Fatal(err)
	}
	if st, err := Status(ctx, jsCLI); err != nil || st.Messages != 1 {
		t.Fatalf("cli outbox status: %+v %v", st, err)
	}
	if _, err := Enqueue(ctx, jsCLI, "events.cli", []byte("y"), "id-2"); err != nil {
		t.Fatalf("cli cannot enqueue: %v", err)
	}

	// 4. Nothing outside the lists: no other node's subjects, no wildcard reads, no other
	// program's replies, no JetStream beyond the outbox. A refused publish or subscribe is a
	// permissions violation the server reports to the connection's error handler.
	violations := func(nc *nats.Conn) chan error {
		ch := make(chan error, 16)
		nc.SetErrorHandler(func(_ *nats.Conn, _ *nats.Subscription, err error) { ch <- err })
		return ch
	}
	odErr, cliErr := violations(od), violations(cli)
	expectViolation := func(who string, ch chan error, do func() error) {
		t.Helper()
		if err := do(); err != nil {
			return // refused synchronously is also a refusal
		}
		select {
		case err := <-ch:
			if !strings.Contains(strings.ToLower(err.Error()), "permissions violation") {
				t.Errorf("%s: unexpected error %v", who, err)
			}
		case <-time.After(3 * time.Second):
			t.Errorf("%s: the server did not refuse the action", who)
		}
	}
	expectViolation("onemindd publishing as another node", odErr, func() error {
		if err := od.Publish("onemind.node.bbb222.status", []byte("spoof")); err != nil {
			return err
		}
		return od.Flush()
	})
	expectViolation("onemindd reading everything", odErr, func() error {
		if _, err := od.Subscribe(">", func(*nats.Msg) {}); err != nil {
			return err
		}
		return od.Flush()
	})
	expectViolation("onemindd deleting the outbox", odErr, func() error {
		// A refused request gets no reply, so wait only briefly for one.
		short, stop := context.WithTimeout(ctx, time.Second)
		defer stop()
		_ = jsOD.DeleteStream(short, OutboxStream)
		return nil
	})
	expectViolation("cli speaking as the node", cliErr, func() error {
		if err := cli.Publish("onemind.node.aaa111.status", []byte("spoof")); err != nil {
			return err
		}
		return cli.Flush()
	})
	expectViolation("cli listening to onemindd's replies", cliErr, func() error {
		if _, err := cli.Subscribe("_INBOX_onemindd.>", func(*nats.Msg) {}); err != nil {
			return err
		}
		return cli.Flush()
	})
	// The stream survived the refused delete.
	if st, err := Status(ctx, jsCLI); err != nil || st.Messages != 2 {
		t.Fatalf("outbox after the refused actions: %+v %v", st, err)
	}
}
