// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nkeys"
)

// Local sign-in on a joined machine (G1, NATS-ROLE-AND-GATEWAY N1).
//
// The leaf listens on loopback so that onemindd and the owner's tools can use the machine's bus.
// Loopback alone is not a lock: any program on the machine can open 127.0.0.1:4222, and an
// installed app or an AI agent is exactly such a program. So the leaf has no passwordless user.
// Every local program has its own nkey (an Ed25519 key pair: the config holds only the public
// half, the program holds the seed) and its own exact publish and subscribe list, the same
// "one key, one scope" rule the hub applies to its own services (CORE-SEC-4).
//
// The leaf link to the hub is not a local user. The leaf signs in to the hub with the node's own
// nkey (Config.NkeyFile), and the hub's account for this node decides what crosses; local
// permissions govern only programs that connect to 127.0.0.1.

// Names of the local programs.
const (
	ProgramOnemindd = "onemindd" // the node agent: heartbeats, departures, outbox events
	ProgramCLI      = "cli"      // `onemind fabric outbox` run by the owner on this machine
	ProgramSensor   = "sensor"   // local writers on a sensor (`onemind device join`)
)

// LocalKeysDirName is the directory (inside the node's etc dir) that holds the local seeds.
// It is not under nats/: that directory belongs to the nats-server user, and a seed must be
// readable only by the program it belongs to.
const LocalKeysDirName = "nats-local"

// LocalProgram is one program that may connect to the leaf on this machine.
type LocalProgram struct {
	Name      string   `json:"name"`
	PublicKey string   `json:"public_key"` // user public nkey (U...); the seed stays with the program
	Publish   []string `json:"publish"`    // subjects it may publish (exact; wildcards only as listed)
	Subscribe []string `json:"subscribe"`  // subjects it may subscribe to; empty means none
}

// InboxPrefix is the reply-subject prefix a local program must use (nats.CustomInboxPrefix), so
// that its subscribe list can name its own replies and no other program's.
func InboxPrefix(name string) string { return "_INBOX_" + name }

// outboxAPI are the JetStream API subjects that creating, updating and reading the outbox use.
func outboxAPI() []string {
	return []string{
		"$JS.API.STREAM.CREATE." + OutboxStream,
		"$JS.API.STREAM.UPDATE." + OutboxStream,
		"$JS.API.STREAM.INFO." + OutboxStream,
	}
}

// NodeSubjects are the subjects of this node on the bus, relative to the hub's registry
// (contract §12.9): status, event.> and jobresult.>.
func nodeSubjects(nodeID string, jobresult bool) []string {
	p := "onemind.node." + nodeID + "."
	s := []string{p + "status", p + "event.>"}
	if jobresult {
		s = append(s, p+"jobresult.>")
	}
	return s
}

// MachinePrograms are the local programs of a joined machine, with the keys given by name
// (ProgramOnemindd and ProgramCLI are both required). nodeID is the node id the hub knows.
//
//   - onemindd publishes this node's own status, event and jobresult subjects and writes the
//     outbox; it subscribes only to its own replies and its own status subject.
//   - cli writes and reads the outbox and nothing else.
func MachinePrograms(nodeID string, keys map[string]string) ([]LocalProgram, error) {
	if !nameRe.MatchString(nodeID) {
		return nil, fmt.Errorf("bad node id %q", nodeID)
	}
	out := []LocalProgram{}
	for _, p := range []struct {
		name     string
		pub, sub []string
	}{
		// onemindd may also read its own status subject, so `node-check.sh` can watch for the
		// heartbeat on the machine; that is its own subject only, never a wildcard.
		{ProgramOnemindd, append(nodeSubjects(nodeID, true), append([]string{OutboxPrefix + ">"}, outboxAPI()...)...), []string{"onemind.node." + nodeID + ".status"}},
		{ProgramCLI, append([]string{OutboxPrefix + ">"}, outboxAPI()...), nil},
	} {
		k := keys[p.name]
		if k == "" {
			return nil, fmt.Errorf("no key for local program %q", p.name)
		}
		out = append(out, LocalProgram{Name: p.name, PublicKey: k, Publish: p.pub, Subscribe: append([]string{InboxPrefix(p.name) + ".>"}, p.sub...)})
	}
	return out, nil
}

// SensorProgram is the only local program of a sensor: it publishes the sensor's own subjects
// (no job results: a sensor runs no jobs) and reads nothing.
func SensorProgram(nodeID, publicKey string) (LocalProgram, error) {
	if !nameRe.MatchString(nodeID) {
		return LocalProgram{}, fmt.Errorf("bad node id %q", nodeID)
	}
	return LocalProgram{Name: ProgramSensor, PublicKey: publicKey, Publish: nodeSubjects(nodeID, false)}, nil
}

func (p LocalProgram) validate() error {
	if !nameRe.MatchString(p.Name) {
		return fmt.Errorf("local program name must be 1-64 of A-Z a-z 0-9 _ -, got %q", p.Name)
	}
	if !nkeys.IsValidPublicUserKey(p.PublicKey) {
		return fmt.Errorf("local program %s: not a NATS user public key", p.Name)
	}
	if len(p.Publish) == 0 {
		return fmt.Errorf("local program %s: needs at least one publish subject", p.Name)
	}
	for _, s := range append(append([]string{}, p.Publish...), p.Subscribe...) {
		if err := checkSubject(s); err != nil {
			return fmt.Errorf("local program %s: %w", p.Name, err)
		}
	}
	return nil
}

// checkSubject refuses a subject that is empty, matches everything, or could break out of its
// quoted string in the config.
func checkSubject(s string) error {
	if s == "" || s == ">" || s == "*" || strings.HasPrefix(s, ".") || strings.HasSuffix(s, ".") || strings.Contains(s, "..") {
		return fmt.Errorf("bad subject %q", s)
	}
	for _, r := range s {
		if r <= ' ' || r == '"' || r == '\'' || r == '\\' || r == '{' || r == '}' || r == '#' || r == ',' || r == ';' {
			return fmt.Errorf("bad subject %q", s)
		}
	}
	return nil
}

func quoteAll(xs []string) string {
	q := make([]string, len(xs))
	for i, x := range xs {
		q[i] = strconv.Quote(x)
	}
	return strings.Join(q, ", ")
}

// renderLocal is the authorization block: no passwordless user, one nkey user per program.
func renderLocal(b *bytes.Buffer, progs []LocalProgram) error {
	if len(progs) == 0 {
		return errors.New("no local program keys: refusing to render a leaf that any program on this machine can use (G1)")
	}
	names, keys := map[string]bool{}, map[string]bool{}
	b.WriteString("# Local sign-in (G1): every program on this machine has its own nkey and its own subjects.\n# There is no passwordless user: a client without a key is refused.\nauthorization {\n  users: [\n")
	for _, p := range progs {
		if err := p.validate(); err != nil {
			return err
		}
		if names[p.Name] || keys[p.PublicKey] {
			return fmt.Errorf("local program %s listed twice (name or key)", p.Name)
		}
		names[p.Name], keys[p.PublicKey] = true, true
		sub := `subscribe: {deny: [">"]}`
		if len(p.Subscribe) > 0 {
			sub = "subscribe: {allow: [" + quoteAll(p.Subscribe) + "]}"
		}
		fmt.Fprintf(b, "    {nkey: %q, permissions: {publish: {allow: [%s]}, %s}}  # %s\n", p.PublicKey, quoteAll(p.Publish), sub, p.Name)
	}
	b.WriteString("  ]\n}\n")
	return nil
}

// CheckLocalAuth refuses a leaf.conf that lets an anonymous local client in: it must have an
// authorization block with nkey users and no no_auth_user. It does not look for user/password
// or token entries: Render never writes them, and an nkey user list is the only form this file
// takes, so the check is the two properties the old open config lacked. Render runs it on every
// config it produces; onemind-leaf-check runs the same rule on the file on disk.
func CheckLocalAuth(conf []byte) error {
	s := string(conf)
	var body []string
	for _, l := range strings.Split(s, "\n") {
		if t := strings.TrimSpace(l); t != "" && !strings.HasPrefix(t, "#") && !strings.HasPrefix(t, "//") {
			if i := strings.Index(t, "#"); i >= 0 {
				t = strings.TrimSpace(t[:i])
			}
			body = append(body, t)
		}
	}
	text := strings.Join(body, "\n")
	if strings.Contains(text, "no_auth_user") {
		return errors.New("leaf.conf has no_auth_user: that is a passwordless local user (G1)")
	}
	if !strings.Contains(text, "authorization {") || !strings.Contains(text, "{nkey:") {
		return errors.New("leaf.conf has no authorization block with nkey users: any local program could connect (G1)")
	}
	return nil
}

// WriteLocalSeed makes the user key pair of one local program and writes its seed to
// dir/<name>.nk (0600, atomic). An existing valid seed is kept, so a second join does not
// change a key a program already holds. It returns the public key.
func WriteLocalSeed(dir, name string) (string, error) {
	if !nameRe.MatchString(name) {
		return "", fmt.Errorf("bad local program name %q", name)
	}
	path := filepath.Join(dir, name+".nk")
	if raw, err := os.ReadFile(path); err == nil {
		if kp, err := nkeys.FromSeed(bytes.TrimSpace(raw)); err == nil {
			if pub, err := kp.PublicKey(); err == nil && nkeys.IsValidPublicUserKey(pub) {
				return pub, nil
			}
		}
	}
	kp, err := nkeys.CreateUser()
	if err != nil {
		return "", err
	}
	seed, err := kp.Seed()
	if err != nil {
		return "", err
	}
	pub, err := kp.PublicKey()
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	if _, err := writeAtomic(path, append(seed, '\n'), 0o600); err != nil {
		return "", err
	}
	return pub, nil
}

// ClientOptions are the nats.go options a local program uses to sign in to the leaf: its seed
// file and its own reply prefix (see InboxPrefix).
func ClientOptions(name, seedFile string) ([]nats.Option, error) {
	nk, err := nats.NkeyOptionFromSeed(seedFile)
	if err != nil {
		return nil, fmt.Errorf("local NATS key %s: %w", seedFile, err)
	}
	return []nats.Option{nk, nats.CustomInboxPrefix(InboxPrefix(name))}, nil
}

// RenderLocalAuth is the authorization block alone, for tests that run a server with the same
// local sign-in as a real leaf but no hub link.
func RenderLocalAuth(progs []LocalProgram) ([]byte, error) {
	var b bytes.Buffer
	if err := renderLocal(&b, progs); err != nil {
		return nil, err
	}
	return b.Bytes(), nil
}
