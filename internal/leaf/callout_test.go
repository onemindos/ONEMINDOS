// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/jwt/v2"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nkeys"
)

// D-029 hybrid: NATS asks the gateway who may connect (core/onemind_core/callout.py). The gateway
// writes its JWTs with `cryptography` (natsjwt.py); here the official jwt/v2 library decodes and
// validates a fixed answer, and nats-server 2.15.3 runs the accounts file with the auth_callout block
// (hub-accounts-callout.golden.conf, core/tests/test_nats_callout.py): with no responder running, the
// pinned hub service and a machine's leaf still get in, and any other client is refused (fail closed).
// core/tests/test_nats_callout.py runs the real responder against a real nats-server.

const calloutPubGW = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3" // test_nats_callout.py PUB_GW

type calloutVector struct {
	Issuer    string   `json:"issuer"`
	ServerID  string   `json:"server_id"`
	UserNkey  string   `json:"user_nkey"`
	Now       int64    `json:"now"`
	Response  string   `json:"response"`
	Agent     string   `json:"agent"`
	Publish   []string `json:"publish"`
	Subscribe []string `json:"subscribe"`
}

func TestGatewayCalloutAnswerDecodesWithJWTv2(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("testdata", "callout-vector.json"))
	if err != nil {
		t.Fatal(err)
	}
	var v calloutVector
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatal(err)
	}
	arc, err := jwt.DecodeAuthorizationResponseClaims(v.Response)
	if err != nil {
		t.Fatalf("decode response: %v", err)
	}
	var vr jwt.ValidationResults
	arc.Validate(&vr)
	if len(vr.Errors()) > 0 || arc.Issuer != v.Issuer || arc.Audience != v.ServerID || arc.Subject != v.UserNkey || arc.Error != "" {
		t.Fatalf("response: %+v %v", arc, vr.Errors())
	}
	uc, err := jwt.DecodeUserClaims(arc.Jwt)
	if err != nil {
		t.Fatalf("decode user: %v", err)
	}
	var uvr jwt.ValidationResults
	uc.Validate(&uvr)
	// Validate reports an expired JWT as an error; the vector's clock is fixed in the past on purpose.
	for _, e := range uvr.Errors() {
		if !strings.Contains(e.Error(), "expired") {
			t.Fatalf("user claims: %v", e)
		}
	}
	if uc.Issuer != v.Issuer || uc.Subject != v.UserNkey || uc.Audience != "AGENTS" || uc.Name != v.Agent ||
		uc.Expires != v.Now+600 || uc.IssuedAt != v.Now {
		t.Fatalf("user: %+v", uc.ClaimsData)
	}
	if !reflect.DeepEqual([]string(uc.Pub.Allow), v.Publish) || !reflect.DeepEqual([]string(uc.Sub.Allow), v.Subscribe) ||
		uc.Resp == nil || uc.Resp.MaxMsgs != 1000 || uc.Resp.Expires != 10*time.Minute || len(uc.Pub.Deny) != 0 {
		t.Fatalf("permissions: %+v", uc.Permissions)
	}
	for _, s := range append(append([]string{}, v.Publish...), v.Subscribe...) {
		if s == ">" || strings.HasPrefix(s, "$JS") || strings.HasPrefix(s, "$SYS") {
			t.Fatalf("agent may use %q", s)
		}
	}
}

// With the callout on and nothing answering it (the gateway down), the pinned list still connects.
func TestCalloutFailsClosedButPinnedUsersStillConnect(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	seedA, pubA := userKey(t)
	gwKP, _ := nkeys.CreateUser()
	gwSeed, _ := gwKP.Seed()
	gwPub, _ := gwKP.PublicKey()
	golden, err := os.ReadFile(filepath.Join("testdata", "hub-accounts-callout.golden.conf"))
	if err != nil {
		t.Fatal(err)
	}
	acc := strings.NewReplacer(goldenPubA, pubA, calloutPubGW, gwPub).Replace(string(golden))
	if err := os.WriteFile(filepath.Join(dir, "accounts.conf"), []byte(acc), 0o600); err != nil {
		t.Fatal(err)
	}
	p := newPKI(t, dir, "box")
	cert, key := p.issue(t, "nats-hub", true)
	cport, leafPort := freePort(t), freePort(t)
	conf := filepath.Join(dir, "hub.conf")
	body := fmt.Sprintf(`server_name: hub
listen: "127.0.0.1:%d"
leafnodes {
  listen: "127.0.0.1:%d"
  tls { cert_file: %q, key_file: %q, ca_file: %q, verify: true, timeout: 5 }
}
include "accounts.conf"
`, cport, leafPort, cert, key, p.caFile)
	if err := os.WriteFile(conf, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	startServer(t, conf)
	url := fmt.Sprintf("nats://127.0.0.1:%d", cport)

	// The gateway (a pinned hub service) signs in with nobody answering the callout.
	gwFile := filepath.Join(dir, "gw.nk")
	if err := os.WriteFile(gwFile, gwSeed, 0o600); err != nil {
		t.Fatal(err)
	}
	nk, err := nats.NkeyOptionFromSeed(gwFile)
	if err != nil {
		t.Fatal(err)
	}
	gw, err := nats.Connect(url, nk, nats.Timeout(5*time.Second))
	if err != nil {
		t.Fatalf("pinned hub service refused with the gateway down: %v", err)
	}
	gw.Close()

	// A machine's leaf (pinned) joins with nobody answering.
	_, sup := startSourcedLeaf(t, dir, "aaa111", p, fmt.Sprintf("127.0.0.1:%d", leafPort), seedA)
	if h := sup.Check(t.Context()); h.State != StateUp {
		t.Fatalf("pinned machine refused with the gateway down: %+v", h)
	}

	// Anyone else, an agent's key included, waits for the gateway and is refused.
	agentSeed, _ := userKey(t)
	agentFile := filepath.Join(dir, "agent.nk")
	if err := os.WriteFile(agentFile, agentSeed, 0o600); err != nil {
		t.Fatal(err)
	}
	ank, _ := nats.NkeyOptionFromSeed(agentFile)
	for name, opts := range map[string][]nats.Option{"agent key": {ank}, "no key": nil} {
		if nc, err := nats.Connect(url, append(opts, nats.Timeout(5*time.Second))...); err == nil {
			nc.Close()
			t.Fatalf("%s accepted with no callout answer", name)
		}
	}
}
