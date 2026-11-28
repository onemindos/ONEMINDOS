// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"github.com/nats-io/nkeys"
)

// Local sign-in on a joined machine's leaf (D-029 "first fix", design gap G1).
//
// The leaf listens on loopback only, but before this every local program could
// publish into the machine's account with no sign-in: fake heartbeats, fake job
// results, a read of the job queue. Now each local program signs in with its own
// nkey (the seed stays in a 0600 file only that program's user can read; leaf.conf
// holds the public key) and may use only the subjects it needs. There is no
// passwordless user: a client with no key or an unknown key is refused.
//
// Principals and their NATS identities (D-029: every NATS identity mirrors a
// gateway principal; a person never gets one, people use the gateway over HTTPS):
//   - the machine itself: its nkey user in NODE_<id> on the hub, LEAFNODE only (join);
//   - programs on the machine: LocalUser here, one key each (onemindd, the CLI);
//   - an AI agent: its own nkey user in the hub's AGENTS account (core natsconf.py).

// Local program names and their inbox prefixes. A client sets nats.CustomInboxPrefix to its own
// prefix, so no other local user can subscribe to its replies.
const (
	LocalOnemindd = "onemindd"
	LocalCLI      = "cli"
)

// InboxPrefix is the reply-inbox prefix of local program name.
func InboxPrefix(name string) string { return "_INBOX_" + name }

// LocalUser is one program's sign-in on the local leaf.
type LocalUser struct {
	Name      string   `json:"name"`
	Nkey      string   `json:"nkey"` // user public key (U...)
	Publish   []string `json:"publish"`
	Subscribe []string `json:"subscribe"`
}

var subjRe = regexp.MustCompile(`^[A-Za-z0-9_$-]+(\.[A-Za-z0-9_$*-]+)*(\.>)?$`)

func (u LocalUser) validate() error {
	if !nameRe.MatchString(u.Name) {
		return fmt.Errorf("local user name %q: 1-64 of A-Z a-z 0-9 _ -", u.Name)
	}
	if !nkeys.IsValidPublicUserKey(u.Nkey) {
		return fmt.Errorf("local user %s: not a NATS user public nkey", u.Name)
	}
	if len(u.Publish) == 0 || len(u.Subscribe) == 0 {
		return fmt.Errorf("local user %s: needs explicit publish and subscribe allow lists", u.Name)
	}
	for _, s := range append(append([]string{}, u.Publish...), u.Subscribe...) {
		if !subjRe.MatchString(s) || s == ">" || strings.HasPrefix(s, "$SYS") {
			return fmt.Errorf("local user %s: subject %q not allowed (no bare >, no $SYS)", u.Name, s)
		}
	}
	return nil
}

func (u LocalUser) render() string {
	q := func(xs []string) string {
		out := make([]string, len(xs))
		for i, x := range xs {
			out[i] = strconv.Quote(x)
		}
		return strings.Join(out, ", ")
	}
	return fmt.Sprintf("    {nkey: %q, permissions: {publish: {allow: [%s]}, subscribe: {allow: [%s]}}}  # %s\n",
		u.Nkey, q(u.Publish), q(u.Subscribe), u.Name)
}

// outboxAPI is what a program needs to create, update and read the outbox stream on its own leaf.
var outboxAPI = []string{"$JS.API.STREAM.INFO." + OutboxStream, "$JS.API.STREAM.CREATE." + OutboxStream,
	"$JS.API.STREAM.UPDATE." + OutboxStream, OutboxPrefix + ">"}

// OnemindUser is onemindd on node nodeID: its heartbeat, its outbox, and its own job queue on the
// hub (pull, acknowledge, report; D-029 N2). The node check uses this identity to read its own
// heartbeat. It cannot publish a job, use another node's subjects, or reach the leaf's JetStream
// API beyond the outbox.
func OnemindUser(nodeID, pub string) LocalUser {
	p := "onemind.node." + nodeID + "."
	return LocalUser{Name: LocalOnemindd, Nkey: pub,
		Publish: append([]string{p + "status", p + "jobresult.>", p + "jobpull", p + "policyget", p + "policycheck",
			"$JS.ACK.ONEMIND_JOBS.node-" + nodeID + ".>"}, outboxAPI...),
		Subscribe: []string{InboxPrefix(LocalOnemindd) + ".>", p + "status"}}
}

// CLIUser is the owner's `onemind fabric outbox` on the machine: the outbox only.
func CLIUser(pub string) LocalUser {
	return LocalUser{Name: LocalCLI, Nkey: pub, Publish: append([]string{}, outboxAPI...),
		Subscribe: []string{InboxPrefix(LocalCLI) + ".>"}}
}
