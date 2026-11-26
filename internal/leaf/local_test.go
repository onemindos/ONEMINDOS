// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"context"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"github.com/nats-io/nkeys"

	"github.com/onemindos/onemindos/internal/backup"
	"github.com/onemindos/onemindos/internal/jobs"
)

// Local sign-in on a joined machine's leaf (D-029 first fix, gap G1): every local program signs in
// with its own key and may use only its own subjects; a client without a key is refused.

func localKey(t *testing.T, dir, name string) (seedFile, pub string) {
	t.Helper()
	kp, err := nkeys.CreateUser()
	if err != nil {
		t.Fatal(err)
	}
	seed, _ := kp.Seed()
	pub, _ = kp.PublicKey()
	seedFile = filepath.Join(dir, name+".nk")
	if err := os.WriteFile(seedFile, seed, 0o600); err != nil {
		t.Fatal(err)
	}
	return seedFile, pub
}

func connectAs(url, seedFile, name string) (*nats.Conn, error) {
	opts := []nats.Option{nats.Timeout(3 * time.Second), nats.CustomInboxPrefix(InboxPrefix(name))}
	if seedFile != "" {
		nk, err := nats.NkeyOptionFromSeed(seedFile)
		if err != nil {
			return nil, err
		}
		opts = append(opts, nk)
	}
	return nats.Connect(url, opts...)
}

func TestRenderLocalUsers(t *testing.T) {
	_, pub := userKey(t)
	_, pub2 := userKey(t)
	c := validConfig()
	c.LocalUsers = []LocalUser{OnemindUser("3f9c2a1b7d4e", pub), CLIUser(pub2)}
	got, err := c.Render("/etc/onemind/nats/leaf.conf")
	if err != nil {
		t.Fatal(err)
	}
	want := "authorization {\n  users: [\n" +
		`    {nkey: "` + pub + `", permissions: {publish: {allow: ["onemind.node.3f9c2a1b7d4e.status", "onemind.node.3f9c2a1b7d4e.jobresult.>", "onemind.node.3f9c2a1b7d4e.jobpull", "$JS.ACK.ONEMIND_JOBS.node-3f9c2a1b7d4e.>", "$JS.API.STREAM.INFO.OUTBOX", "$JS.API.STREAM.CREATE.OUTBOX", "$JS.API.STREAM.UPDATE.OUTBOX", "outbox.>"]}, subscribe: {allow: ["_INBOX_onemindd.>"]}}}  # onemindd` + "\n" +
		`    {nkey: "` + pub2 + `", permissions: {publish: {allow: ["$JS.API.STREAM.INFO.OUTBOX", "$JS.API.STREAM.CREATE.OUTBOX", "$JS.API.STREAM.UPDATE.OUTBOX", "outbox.>"]}, subscribe: {allow: ["_INBOX_cli.>"]}}}  # cli` + "\n" +
		"  ]\n}\n"
	if !strings.HasSuffix(string(got), want) || strings.Contains(string(got), "no_auth_user") {
		t.Fatalf("render:\n%s\nwant suffix:\n%s", got, want)
	}
	for name, mut := range map[string]func(*LocalUser){
		"bad key":        func(u *LocalUser) { u.Nkey = "UNOTAKEY" },
		"bare wildcard":  func(u *LocalUser) { u.Publish = []string{">"} },
		"system account": func(u *LocalUser) { u.Subscribe = []string{"$SYS.>"} },
		"quote":          func(u *LocalUser) { u.Publish = []string{`a"b`} },
		"no allow list":  func(u *LocalUser) { u.Subscribe = nil },
		"bad name":       func(u *LocalUser) { u.Name = "a b" },
	} {
		c := validConfig()
		u := CLIUser(pub2)
		mut(&u)
		c.LocalUsers = []LocalUser{u}
		if _, err := c.Render("/etc/onemind/nats/leaf.conf"); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	c = validConfig()
	c.LocalUsers = []LocalUser{CLIUser(pub2), CLIUser(pub2)}
	if err := c.Validate(); err == nil {
		t.Error("two users with one key accepted")
	}
}

// The real thing: node A's leaf with local sign-in, joined to the hub with the gateway's accounts.
func TestLocalSignInRefusesStrangersAndScopesEachProgram(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	odSeed, odPub := localKey(t, dir, "onemindd")
	cliSeed, cliPub := localKey(t, dir, "cli")
	l := newSourcingLabWith(t, []LocalUser{OnemindUser("aaa111", odPub), CLIUser(cliPub)})

	// No key, or a key the leaf does not know: refused at connect.
	if nc, err := connectAs(l.leafA, "", "x"); err == nil {
		nc.Close()
		t.Fatal("a local client with no key was accepted")
	}
	strangerSeed, _ := localKey(t, dir, "stranger")
	if nc, err := connectAs(l.leafA, strangerSeed, "x"); err == nil {
		nc.Close()
		t.Fatal("a local client with an unknown key was accepted")
	}

	hub, err := nats.Connect(l.hubURL)
	if err != nil {
		t.Fatal(err)
	}
	defer hub.Close()
	got := make(chan string, 16)
	if _, err := hub.Subscribe("onemind.node.*.status", func(m *nats.Msg) { got <- m.Subject }); err != nil {
		t.Fatal(err)
	}
	_ = hub.Flush()

	errs := make(chan error, 16)
	od, err := nats.Connect(l.leafA, nats.CustomInboxPrefix(InboxPrefix(LocalOnemindd)),
		func() nats.Option { o, _ := nats.NkeyOptionFromSeed(odSeed); return o }(),
		nats.ErrorHandler(func(_ *nats.Conn, _ *nats.Subscription, e error) { errs <- e }))
	if err != nil {
		t.Fatal(err)
	}
	defer od.Close()
	// Its own heartbeat reaches the hub.
	waitUntil(t, 30*time.Second, "onemindd's heartbeat at the hub", func() bool {
		_ = od.Publish("onemind.node.aaa111.status", []byte(`{}`))
		_ = od.Flush()
		select {
		case s := <-got:
			return s == "onemind.node.aaa111.status"
		case <-time.After(300 * time.Millisecond):
			return false
		}
	})
	// Another node's heartbeat, a job, or a read of everything: permission violations.
	for _, subj := range []string{"onemind.node.bbb222.status", "onemind.node.aaa111.job.host.check", "onemind.node.aaa111.event.x"} {
		_ = od.Publish(subj, []byte(`{}`))
	}
	if _, err := od.Subscribe(">", func(*nats.Msg) {}); err != nil {
		t.Fatal(err)
	}
	_ = od.Flush()
	violations := 0
	deadline := time.After(5 * time.Second)
	for violations < 4 {
		select {
		case e := <-errs:
			if strings.Contains(strings.ToLower(e.Error()), "permissions violation") {
				violations++
			}
		case <-deadline:
			t.Fatalf("only %d of 4 permission violations reported", violations)
		}
	}
	// Its outbox works signed in, with its own inbox.
	js, err := jetstream.New(od)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if err := EnsureOutbox(ctx, js, OutboxConfig{}); err != nil {
		t.Fatalf("onemindd outbox: %v", err)
	}
	if _, err := Enqueue(ctx, js, "events.sensor", []byte("x"), "ev-1"); err != nil {
		t.Fatalf("onemindd enqueue: %v", err)
	}
	// Its job queue is allowed signed in (D-029 N2; jobs_test.go runs it end to end): a pull raises
	// no permission violation, whatever the hub answers without a queue here.
	in := &jobs.Intake{NC: od, NodeID: "aaa111", Verifier: backup.NewNodeJobVerifier("aaa111", filepath.Join(dir, "none.pub"), dir),
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)), PollWait: 200 * time.Millisecond}
	_, _ = in.PullOnce(ctx)
	_ = od.Flush()
	select {
	case e := <-errs:
		t.Fatalf("job pull refused: %v", e)
	case <-time.After(time.Second):
	}

	// The CLI user: the outbox, nothing else.
	cliErrs := make(chan error, 4)
	cli, err := nats.Connect(l.leafA, nats.CustomInboxPrefix(InboxPrefix(LocalCLI)),
		func() nats.Option { o, _ := nats.NkeyOptionFromSeed(cliSeed); return o }(),
		nats.ErrorHandler(func(_ *nats.Conn, _ *nats.Subscription, e error) { cliErrs <- e }))
	if err != nil {
		t.Fatal(err)
	}
	defer cli.Close()
	cjs, _ := jetstream.New(cli)
	if _, err := Status(ctx, cjs); err != nil {
		t.Fatalf("cli outbox status: %v", err)
	}
	_ = cli.Publish("onemind.node.aaa111.status", []byte(`{}`))
	_ = cli.Flush()
	select {
	case e := <-cliErrs:
		if !strings.Contains(strings.ToLower(e.Error()), "permissions violation") {
			t.Fatalf("cli: %v", e)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("the cli user published a heartbeat")
	}
	var stray atomic.Int32
	select {
	case s := <-got:
		if s != "onemind.node.aaa111.status" {
			stray.Add(1)
		}
	case <-time.After(time.Second):
	}
	if stray.Load() != 0 {
		t.Fatal("a refused heartbeat reached the hub")
	}
}
