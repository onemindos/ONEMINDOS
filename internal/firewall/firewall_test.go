// SPDX-License-Identifier: Apache-2.0

package firewall

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"
)

// A trimmed `nft -j list ruleset` of the shipped host.nft (nft 1.1 JSON shapes), plus a foreign table.
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
   {"match":{"op":"in","left":{"ct":{"key":"state"}},"right":{"set":["established","related"]}}},{"accept":null}]}},
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
