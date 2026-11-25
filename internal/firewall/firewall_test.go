// SPDX-License-Identifier: Apache-2.0

package firewall

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"reflect"
	"strings"
	"testing"
	"time"
)

// A trimmed `nft -j list ruleset` (nft 1.1 JSON shapes), plus a foreign table. The real, unedited output
// of the shipped host.nft is in testdata/ and tested below.
const ruleset = `{"nftables":[
 {"metainfo":{"version":"1.1.3","json_schema_version":1}},
 {"table":{"family":"inet","name":"onemind_host","handle":1}},
 {"table":{"family":"ip","name":"kube-proxy","handle":2}},
 {"set":{"family":"inet","name":"lan4","table":"onemind_host","type":"ipv4_addr","handle":3,"flags":["interval"],
   "elem":[{"prefix":{"addr":"10.0.0.0","len":8}},{"prefix":{"addr":"192.168.0.0","len":16}}]}},
 {"chain":{"family":"inet","table":"onemind_host","name":"input","handle":4,"type":"filter","hook":"input","prio":0,"policy":"drop"}},
 {"chain":{"family":"inet","table":"onemind_host","name":"lan","handle":5}},
 {"chain":{"family":"ip","table":"kube-proxy","name":"services","handle":6}},
 {"rule":{"family":"inet","table":"onemind_host","chain":"input","handle":7,"expr":[
   {"match":{"op":"in","left":{"ct":{"key":"state"}},"right":["established","related"]}},{"accept":null}]}},
 {"rule":{"family":"inet","table":"onemind_host","chain":"input","handle":8,"expr":[
   {"match":{"op":"==","left":{"meta":{"key":"iifname"}},"right":"tailscale0"}},
   {"match":{"op":"==","left":{"payload":{"protocol":"tcp","field":"dport"}},"right":{"set":[6443,10250]}}},
   {"counter":{"packets":0,"bytes":0}},{"accept":null}]}},
 {"rule":{"family":"inet","table":"onemind_host","chain":"input","handle":9,"expr":[
   {"match":{"op":"==","left":{"payload":{"protocol":"ip","field":"saddr"}},"right":"@lan4"}},{"jump":{"target":"lan"}}]}},
 {"rule":{"family":"inet","table":"onemind_host","chain":"input","handle":10,"expr":[
   {"match":{"op":"==","left":{"payload":{"protocol":"ip6","field":"saddr"}},"right":{"prefix":{"addr":"fe80::","len":10}}}},{"accept":null}]}},
 {"rule":{"family":"inet","table":"onemind_host","chain":"lan","handle":11,"expr":[
   {"match":{"op":"==","left":{"payload":{"protocol":"tcp","field":"dport"}},"right":{"set":[443,{"range":[8443,8444]}]}}},{"accept":null}]}},
 {"rule":{"family":"inet","table":"onemind_host","chain":"input","handle":12,"expr":[
   {"match":{"op":"==","left":{"meta":{"key":"mark"}},"right":1}},{"accept":null}]}},
 {"rule":{"family":"inet","table":"onemind_host","chain":"input","handle":13,"expr":[{"dnat":{"addr":"192.0.2.1"}}]}},
 {"rule":{"family":"ip","table":"kube-proxy","chain":"services","handle":14,"expr":[{"accept":null}]}}
]}`

func TestParseHostTable(t *testing.T) {
	v, err := Parse([]byte(ruleset))
	if err != nil {
		t.Fatal(err)
	}
	if v.Schema != Schema || v.Host == nil || v.Host.Name != HostTable {
		t.Fatalf("%+v", v)
	}
	if !reflect.DeepEqual(v.Tables, []TableInfo{{"ip", "kube-proxy", 1, 1}, {"inet", "onemind_host", 2, 7}}) {
		t.Fatalf("tables are listed by name and size only: %+v", v.Tables)
	}
	if got := v.Host.Sets; len(got) != 1 || !reflect.DeepEqual(got[0].Elements, []string{"10.0.0.0/8", "192.168.0.0/16"}) {
		t.Fatalf("sets %+v", got)
	}
	in := v.Host.Chains[0]
	if in.Name != "input" || in.Hook != "input" || in.Policy != "drop" || len(in.Rules) != 6 {
		t.Fatalf("input chain %+v", in)
	}
	want := []Rule{
		{Verdict: "accept", Ct: []string{"established", "related"}, Understood: true},
		{Verdict: "accept", Iif: "tailscale0", Proto: "tcp", Dport: []string{"6443", "10250"}, Understood: true},
		{Verdict: "jump", Target: "lan", Saddr: "@lan4", Understood: true},
		{Verdict: "accept", Saddr: "fe80::/10", Understood: true},
		{Verdict: "accept", Understood: false}, // a match on the packet mark is not modelled
		{Verdict: "none", Understood: false},   // dnat is not modelled
	}
	if !reflect.DeepEqual(in.Rules, want) {
		t.Fatalf("rules\n got %+v\nwant %+v", in.Rules, want)
	}
	lan := v.Host.Chains[1]
	if lan.Name != "lan" || lan.Hook != "" || len(lan.Rules) != 1 || !reflect.DeepEqual(lan.Rules[0].Dport, []string{"443", "8443-8444"}) {
		t.Fatalf("lan chain %+v", lan)
	}
	for _, c := range v.Host.Chains {
		for _, r := range c.Rules {
			if strings.Contains(r.Saddr, "192.0.2.1") {
				t.Fatal("foreign data leaked")
			}
		}
	}
}

func TestNoHostTable(t *testing.T) {
	v, err := Parse([]byte(`{"nftables":[{"metainfo":{}},{"table":{"family":"ip","name":"nat"}}]}`))
	if err != nil || v.Host != nil || len(v.Tables) != 1 {
		t.Fatalf("%+v %v", v, err)
	}
	v, err = Parse([]byte(`{"nftables":[{"metainfo":{}}]}`))
	if err != nil || v.Host != nil || v.Tables == nil {
		t.Fatalf("an empty ruleset is a valid answer: %+v %v", v, err)
	}
}

func TestParseRefusesNonJSON(t *testing.T) {
	if _, err := Parse([]byte("table inet onemind_host {")); err == nil {
		t.Fatal("text output must be refused")
	}
}

func TestRuleCapAndOddRules(t *testing.T) {
	var b strings.Builder
	b.WriteString(`{"nftables":[{"table":{"family":"inet","name":"onemind_host"}},{"chain":{"family":"inet","table":"onemind_host","name":"input","hook":"input","policy":"drop"}}`)
	for i := 0; i < maxRules+50; i++ {
		b.WriteString(`,{"rule":{"family":"inet","table":"onemind_host","chain":"input","expr":[{"accept":null}]}}`)
	}
	b.WriteString(`,{"rule":{"family":"inet","table":"onemind_host","chain":"nope","expr":[{"accept":null}]}}]}`)
	v, err := Parse([]byte(b.String()))
	if err != nil || len(v.Host.Chains[0].Rules) != maxRules {
		t.Fatalf("%v %d", err, len(v.Host.Chains[0].Rules))
	}
	if v.Tables[0].Rules != maxRules+51 {
		t.Fatalf("the table's rule count is still true: %d", v.Tables[0].Rules)
	}
	if v.Truncated != 51 {
		t.Fatalf("every rule the cap cut (and the one in no chain) is counted, not silent: %d", v.Truncated)
	}
}

func TestCapsAreCountedNotSilent(t *testing.T) {
	var b strings.Builder
	b.WriteString(`{"nftables":[{"table":{"family":"inet","name":"onemind_host"}}`)
	for i := 0; i < maxChains+3; i++ { // 3 chains too many; their rules go with them
		fmt.Fprintf(&b, `,{"chain":{"family":"inet","table":"onemind_host","name":"c%d"}},{"rule":{"family":"inet","table":"onemind_host","chain":"c%d","expr":[{"accept":null}]}}`, i, i)
	}
	b.WriteString(`,{"set":{"family":"inet","table":"onemind_host","name":"big","elem":[`)
	for i := 0; i < maxElems+5; i++ {
		if i > 0 {
			b.WriteString(",")
		}
		fmt.Fprintf(&b, `"10.0.%d.1"`, i)
	}
	b.WriteString(`]}}`)
	for i := 0; i < maxSets+2; i++ {
		fmt.Fprintf(&b, `,{"set":{"family":"inet","table":"onemind_host","name":"s%d","elem":[]}}`, i)
	}
	b.WriteString(`]}`)
	v, err := Parse([]byte(b.String()))
	if err != nil {
		t.Fatal(err)
	}
	// 3 chains + their 3 rules + 3 sets past the cap + 5 set members past the cap.
	if len(v.Host.Chains) != maxChains || v.Truncated != 3+3+3+5 {
		t.Fatalf("chains %d truncated %d", len(v.Host.Chains), v.Truncated)
	}
}

func TestAListLongerThanTheCapMakesTheRuleNotUnderstood(t *testing.T) {
	var ports []string
	for i := 1; i <= maxItems+1; i++ {
		ports = append(ports, fmt.Sprint(i))
	}
	r := parseRule([]any{
		map[string]any{"match": map[string]any{"op": "==", "left": map[string]any{"payload": map[string]any{"protocol": "tcp", "field": "dport"}},
			"right": map[string]any{"set": toAny(ports)}}},
		map[string]any{"accept": nil}})
	if r.Understood {
		t.Fatalf("a port list the cap cut must not be read as the whole list: %+v", r)
	}
}

func toAny(in []string) []any {
	out := make([]any, len(in))
	for i, s := range in {
		out[i] = s
	}
	return out
}

func TestWorstCaseAnswerFitsTheGatewayReadLimit(t *testing.T) {
	v := &View{Schema: Schema, Tables: []TableInfo{}, Host: &Table{Family: "inet", Name: HostTable}}
	long := strings.Repeat("1", maxItems)
	for c := 0; c < maxChains; c++ {
		ch := Chain{Name: "chain", Hook: "input", Policy: "drop"}
		for i := 0; i < maxRules/maxChains+1; i++ {
			ports := make([]string, maxItems)
			for j := range ports {
				ports[j] = long[:11]
			}
			ch.Rules = append(ch.Rules, Rule{Verdict: "accept", Iif: strings.Repeat("e", 40), Proto: "tcp", Dport: ports, Saddr: strings.Repeat("a", 43), Ct: []string{"established"}})
		}
		v.Host.Chains = append(v.Host.Chains, ch)
	}
	raw, _ := json.Marshal(v)
	if len(raw) > 1<<20 {
		t.Fatalf("%d bytes is over the gateway's 1 MiB read limit", len(raw))
	}
}

// The unedited output of `nft -j list ruleset` (nftables 1.1.3, Debian 13) after loading the shipped
// os/rootfs/layers/onemind/usr/lib/onemind/host.nft and adding the samba rule the way onemind-smb.service does.
// nft writes a list of values as a plain array and a single value as a bare string; both must be read.
func TestShippedHostNftAsNftReallyPrintsIt(t *testing.T) {
	raw, err := os.ReadFile("testdata/host-ruleset.json")
	if err != nil {
		t.Fatal(err)
	}
	v, err := Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	if v.Truncated != 0 || v.Host == nil || len(v.Host.Chains) != 4 {
		t.Fatalf("%+v", v)
	}
	for _, c := range v.Host.Chains {
		for i, r := range c.Rules {
			if !r.Understood {
				t.Fatalf("the shipped rule %s #%d must be understood: %+v", c.Name, i+1, r)
			}
		}
	}
	in := v.Host.Chains[0].Rules
	if !reflect.DeepEqual(in[0], Rule{Verdict: "accept", Ct: []string{"established", "related"}, Understood: true}) ||
		!reflect.DeepEqual(in[1], Rule{Verdict: "drop", Ct: []string{"invalid"}, Understood: true}) ||
		!reflect.DeepEqual(in[2], Rule{Verdict: "accept", Iif: "lo", Understood: true}) {
		t.Fatalf("first three input rules: %+v", in[:3])
	}
	if len(in) != 15 || in[13].Saddr != "@lan4" || in[13].Verdict != "jump" || in[14].Saddr != "@lan6" {
		t.Fatalf("input rules %d %+v", len(in), in[13])
	}
	v.At = time.Time{}
	got, _ := json.MarshalIndent(v, "", " ")
	if os.Getenv("UPDATE_GOLDEN") != "" {
		if err := os.WriteFile("testdata/host-view.golden.json", append(got, '\n'), 0o644); err != nil {
			t.Fatal(err)
		}
		return
	}
	golden, err := os.ReadFile("testdata/host-view.golden.json")
	if err != nil {
		t.Fatal(err)
	}
	if strings.TrimSpace(string(golden)) != string(got) {
		t.Fatalf("the golden view changed (the gateway test reads it too); rerun with UPDATE_GOLDEN=1 if intended:\n%s", got)
	}
}

// Shapes nft prints for rules the screen does not model (real output, testdata/host-ruleset-extra-rules.json).
func TestRealNftShapesTheViewDoesNotModelAreNotUnderstood(t *testing.T) {
	raw, err := os.ReadFile("testdata/host-ruleset-extra-rules.json")
	if err != nil {
		t.Fatal(err)
	}
	v, err := Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	in := v.Host.Chains[0].Rules[15:]
	want := []struct {
		understood bool
		ct         []string
	}{
		{true, []string{"new"}},                // tcp dport 22 ct state new
		{true, nil},                            // ip saddr 0.0.0.0/0 tcp dport 80
		{true, nil},                            // iifname eth0 tcp dport 81
		{false, nil},                           // limit
		{false, nil},                           // log
		{false, nil},                           // dport != 84
		{false, nil},                           // icmp type
		{true, []string{"established", "new"}}, // ct state { new, established }
		{true, []string{"established", "new"}}, // ct state new,established
	}
	if len(in) != len(want) {
		t.Fatalf("%d rules", len(in))
	}
	for i, w := range want {
		if in[i].Understood != w.understood || !reflect.DeepEqual(in[i].Ct, w.ct) {
			t.Errorf("rule %d: %+v", i, in[i])
		}
	}
	if in[1].Saddr != "0.0.0.0/0" {
		t.Errorf("a prefix of length 0 is kept as 0.0.0.0/0, got %q", in[1].Saddr)
	}
}

func TestCollect(t *testing.T) {
	at := time.Date(2026, 11, 25, 12, 0, 0, 0, time.UTC)
	c := Collector{Run: func(context.Context) ([]byte, error) { return []byte(ruleset), nil }, Now: func() time.Time { return at }}
	v, err := c.Collect(context.Background())
	if err != nil || !v.At.Equal(at) {
		t.Fatalf("%+v %v", v, err)
	}
	c.Run = func(context.Context) ([]byte, error) { return nil, errors.New("nft: permission denied") }
	if _, err := c.Collect(context.Background()); err == nil {
		t.Fatal("a failed nft run is an error")
	}
}

// libnftables-json(5): a set member with a comment, timeout or expiry is {"elem": {"val": ..., ...}}. It
// must be read, and a member the parser cannot read must be counted as cut, never dropped silently.
func TestSetMembersWithCommentOrTimeoutAreReadAndUnknownOnesAreCounted(t *testing.T) {
	raw := `{"nftables":[
 {"table":{"family":"inet","name":"onemind_host","handle":1}},
 {"set":{"family":"inet","name":"trusted","table":"onemind_host","type":"ipv4_addr","handle":2,"flags":["interval","timeout"],
   "elem":[{"prefix":{"addr":"192.168.0.0","len":16}},
           {"elem":{"val":{"prefix":{"addr":"0.0.0.0","len":0}},"timeout":60,"expires":50,"comment":"temp"}},
           {"mystery":1}]}}
]}`
	v, err := Parse([]byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	got := v.Host.Sets[0].Elements
	if !reflect.DeepEqual(got, []string{"192.168.0.0/16", "0.0.0.0/0"}) {
		t.Fatalf("elements %v: the member with a comment must be read", got)
	}
	if v.Truncated != 1 {
		t.Fatalf("truncated=%d: the member the parser cannot read must be counted", v.Truncated)
	}
}

func TestAnUnknownItemInARuleListMakesTheRuleNotUnderstood(t *testing.T) {
	r := parseRule([]any{
		map[string]any{"match": map[string]any{"op": "==",
			"left":  map[string]any{"payload": map[string]any{"protocol": "tcp", "field": "dport"}},
			"right": map[string]any{"set": []any{float64(22), map[string]any{"mystery": 1.0}}}}},
		map[string]any{"accept": nil},
	})
	if r.Understood {
		t.Fatalf("a list with an item that cannot be read must not be trusted: %+v", r)
	}
}

func TestSocketReaderReadsWhatTheReaderUnitPrints(t *testing.T) {
	dir, err := os.MkdirTemp("", "fw")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)
	path := dir + "/r.sock"
	ln, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go func() {
		c, err := ln.Accept()
		if err != nil {
			return
		}
		_, _ = c.Write([]byte(ruleset))
		c.Close()
	}()
	v, err := Collector{Run: SocketReader(path)}.Collect(context.Background())
	if err != nil || v.Host == nil {
		t.Fatalf("%v %+v", err, v)
	}
	if _, err := (Collector{Run: SocketReader(dir + "/none.sock")}).Collect(context.Background()); err == nil {
		t.Fatal("a missing reader socket must be an error, not an empty ruleset")
	}
}
