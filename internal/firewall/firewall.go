// SPDX-License-Identifier: Apache-2.0

// Package firewall reads the box's live nftables ruleset for the Network screen and `onemind firewall
// show` (P-09 part 1). It is read-only: it runs `nft -j list ruleset` (fixed arguments, no shell, no
// user input) on the host and turns the JSON into a small structured form the gateway can check and
// explain. Raw nft text never leaves this package.
//
// The detailed form covers the OneMind table (`inet onemind_host`, os/rootfs/.../host.nft). Other
// tables (k3s, kube-proxy, mesh guard) are reported by name and size only: they are not the owner's
// rules and their contents are an implementation detail of those services.
//
// Reading never changes the ruleset. The one writer is Allower (allow.go): owner allow rules with
// automatic revert, in two chains of the OneMind table and nowhere else.
package firewall

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"sort"
	"strconv"
	"time"
)

// Schema names the document's shape.
const Schema = "onemind.firewall/v1"

// HostTable is the OneMind host firewall table (family inet).
const HostTable = "onemind_host"

// Caps keep one answer small whatever the ruleset looks like. maxRules counts rules across the whole host
// table (not per chain), so the answer stays far below the gateway's 1 MiB read limit. Whatever a cap cuts
// is counted in View.Truncated: the gateway never calls a firewall it only partly saw "closed".
const (
	maxTables = 32
	maxChains = 64
	maxRules  = 400
	maxSets   = 32
	maxElems  = 64
	maxItems  = 64 // values in one match, e.g. ports in a set
)

// View is GET /v1/firewall on the host service.
type View struct {
	Schema string    `json:"schema"`
	At     time.Time `json:"at"`
	// Tables is every table in the ruleset, by name and size only.
	Tables []TableInfo `json:"tables"`
	// Host is the detailed OneMind table; nil when it is not loaded.
	Host *Table `json:"host"`
	// Truncated counts the chains, rules, sets and set members of the OneMind table that a size cap left
	// out. Zero on every normal box; when it is not zero the gateway reports the firewall as not fully checked.
	Truncated int `json:"truncated"`
	// Allow is the owner allow rules (P-09 part 2); nil when this host service keeps none.
	Allow *AllowState `json:"allow,omitempty"`
}

// TableInfo is one table, without its contents.
type TableInfo struct {
	Family string `json:"family"`
	Name   string `json:"name"`
	Chains int    `json:"chains"`
	Rules  int    `json:"rules"`
}

// Table is a table with its sets and chains.
type Table struct {
	Family string  `json:"family"`
	Name   string  `json:"name"`
	Sets   []Set   `json:"sets"`
	Chains []Chain `json:"chains"`
}

// Set is a named set, e.g. the private address ranges that count as "the LAN".
type Set struct {
	Name     string   `json:"name"`
	Elements []string `json:"elements"`
}

// Chain is a base chain (Hook set) or a regular chain reached by jump.
type Chain struct {
	Name   string `json:"name"`
	Hook   string `json:"hook,omitempty"`
	Policy string `json:"policy,omitempty"`
	Rules  []Rule `json:"rules"`
}

// Rule is one rule in the form the gateway explains. Understood is false when the rule uses anything
// this package does not model; the gateway then says so instead of guessing what it does.
type Rule struct {
	Verdict    string   `json:"verdict"` // accept, drop, reject, jump, goto, return, none
	Target     string   `json:"target,omitempty"`
	Iif        string   `json:"iif,omitempty"`
	Proto      string   `json:"proto,omitempty"` // tcp, udp, icmp, ipv6-icmp
	Sport      []string `json:"sport,omitempty"`
	Dport      []string `json:"dport,omitempty"`
	Saddr      string   `json:"saddr,omitempty"` // "@set", a prefix, or an address
	Ct         []string `json:"ct,omitempty"`    // connection states
	Understood bool     `json:"understood"`
}

// Collector reads the ruleset. Run returns the output of `nft -j list ruleset`.
type Collector struct {
	Run func(ctx context.Context) ([]byte, error)
	Now func() time.Time
	// Allower, when set, adds the owner allow rules to the view. They are offered only when the host table
	// has both lists (owner_lan, owner_mesh): an older image reads fine and says it cannot take rules yet.
	Allower *Allower
}

// Collect reads and parses the live ruleset.
func (c Collector) Collect(ctx context.Context) (*View, error) {
	raw, err := c.Run(ctx)
	if err != nil {
		return nil, err
	}
	now := time.Now
	if c.Now != nil {
		now = c.Now
	}
	v, err := Parse(raw)
	if err != nil {
		return nil, err
	}
	v.At = now().UTC()
	if c.Allower != nil {
		v.Allow = c.Allower.State(v.hasChain(ChainLAN) && v.hasChain(ChainMesh))
	}
	return v, nil
}

func (v *View) hasChain(name string) bool {
	if v.Host == nil {
		return false
	}
	for _, c := range v.Host.Chains {
		if c.Name == name {
			return true
		}
	}
	return false
}

type nftDoc struct {
	Nftables []map[string]json.RawMessage `json:"nftables"`
}

// Parse turns the output of `nft -j list ruleset` into a View.
func Parse(raw []byte) (*View, error) {
	var doc nftDoc
	if err := json.Unmarshal(raw, &doc); err != nil {
		return nil, fmt.Errorf("nft output is not JSON: %w", err)
	}
	type key struct{ family, table string }
	var order []key
	info := map[key]*TableInfo{}
	chains := map[key][]*Chain{}
	chainAt := map[[3]string]*Chain{}
	var sets []Set
	truncated, hostRules := 0, 0
	for _, item := range doc.Nftables {
		for kind, body := range item {
			var m map[string]any
			if err := json.Unmarshal(body, &m); err != nil {
				continue
			}
			k := key{str(m["family"]), str(m["name"])}
			switch kind {
			case "table":
				if _, ok := info[k]; !ok && len(order) < maxTables {
					info[k] = &TableInfo{Family: k.family, Name: k.table}
					order = append(order, k)
				}
			case "chain":
				tk := key{str(m["family"]), str(m["table"])}
				t := info[tk]
				if t == nil {
					continue
				}
				t.Chains++
				if tk.family != "inet" || tk.table != HostTable {
					continue
				}
				if len(chains[tk]) >= maxChains {
					truncated++
					continue
				}
				ch := &Chain{Name: str(m["name"]), Hook: str(m["hook"]), Policy: str(m["policy"]), Rules: []Rule{}}
				chains[tk] = append(chains[tk], ch)
				chainAt[[3]string{tk.family, tk.table, ch.Name}] = ch
			case "set":
				if str(m["family"]) == "inet" && str(m["table"]) == HostTable {
					if len(sets) >= maxSets {
						truncated++
						continue
					}
					s := Set{Name: str(m["name"]), Elements: []string{}}
					if el, ok := m["elem"].([]any); ok {
						for _, e := range el {
							vals, cut := flatten(e)
							if cut || len(s.Elements)+len(vals) > maxElems {
								truncated++
								continue
							}
							s.Elements = append(s.Elements, vals...)
						}
					}
					sets = append(sets, s)
				}
			case "rule":
				tk := key{str(m["family"]), str(m["table"])}
				if t := info[tk]; t != nil {
					t.Rules++
				}
				if tk.family != "inet" || tk.table != HostTable {
					continue
				}
				ch := chainAt[[3]string{tk.family, tk.table, str(m["chain"])}]
				if ch == nil || hostRules >= maxRules {
					truncated++ // a rule in a chain that was cut, or past the rule cap
					continue
				}
				hostRules++
				ch.Rules = append(ch.Rules, parseRule(m["expr"]))
			}
		}
	}
	v := &View{Schema: Schema, Tables: []TableInfo{}, Truncated: truncated}
	for _, k := range order {
		v.Tables = append(v.Tables, *info[k])
	}
	sort.SliceStable(v.Tables, func(i, j int) bool { return v.Tables[i].Name < v.Tables[j].Name })
	hk := key{"inet", HostTable}
	if _, ok := info[hk]; ok {
		t := &Table{Family: "inet", Name: HostTable, Sets: sets, Chains: []Chain{}}
		if t.Sets == nil {
			t.Sets = []Set{}
		}
		for _, ch := range chains[hk] {
			t.Chains = append(t.Chains, *ch)
		}
		v.Host = t
	}
	return v, nil
}

func str(v any) string {
	s, _ := v.(string)
	return s
}

// values flattens a match's right-hand side into display strings: numbers, names, ranges "a-b",
// prefixes "addr/len", and the members of a set. libnftables-json(5) writes a list of values as a plain
// JSON array (`"right": ["established","related"]`) and an anonymous set as {"set": [...]}; both are read.
func values(v any) []string {
	out, _ := flatten(v)
	return out
}

// flatten is values plus whether the maxItems cap cut something (the caller must then not trust the match).
func flatten(v any) ([]string, bool) {
	switch x := v.(type) {
	case string:
		return []string{x}, false
	case float64:
		return []string{strconv.FormatInt(int64(x), 10)}, false
	case []any:
		return flattenList(x)
	case map[string]any:
		if set, ok := x["set"].([]any); ok {
			return flattenList(set)
		}
		// A set member with a comment, timeout or expiry is printed as {"elem": {"val": ..., ...}}.
		if el, ok := x["elem"].(map[string]any); ok {
			if val, ok := el["val"]; ok {
				return flatten(val)
			}
		}
		if r, ok := x["range"].([]any); ok && len(r) == 2 {
			a, b := values(r[0]), values(r[1])
			if len(a) == 1 && len(b) == 1 {
				return []string{a[0] + "-" + b[0]}, false
			}
			return nil, true
		}
		if p, ok := x["prefix"].(map[string]any); ok {
			if ln, ok := p["len"].(float64); ok {
				return []string{str(p["addr"]) + "/" + strconv.Itoa(int(ln))}, false
			}
		}
	}
	// A shape this package does not read is reported as cut, never silently dropped: the caller counts it
	// as not understood or truncated, so a member it could not read can never make a set look like "LAN".
	return nil, true
}

func flattenList(list []any) ([]string, bool) {
	out := []string{}
	for _, e := range list {
		vals, cut := flatten(e)
		if cut || len(out)+len(vals) > maxItems {
			return out, true
		}
		out = append(out, vals...)
	}
	return out, false
}

// parseRule models the expressions the OneMind table uses. Anything else clears Understood.
func parseRule(raw any) Rule {
	r := Rule{Verdict: "none", Understood: true}
	exprs, _ := raw.([]any)
	for _, e := range exprs {
		m, _ := e.(map[string]any)
		if len(m) != 1 {
			r.Understood = false
			continue
		}
		for kind, body := range m {
			switch kind {
			case "accept", "drop", "return":
				r.Verdict = kind
			case "reject":
				r.Verdict = "reject"
			case "jump", "goto":
				r.Verdict, r.Target = kind, str(asMap(body)["target"])
			case "counter":
				// counting changes nothing about what is allowed
			case "match":
				if !parseMatch(&r, asMap(body)) {
					r.Understood = false
				}
			default:
				r.Understood = false
			}
		}
	}
	return r
}

func asMap(v any) map[string]any {
	m, _ := v.(map[string]any)
	return m
}

func parseMatch(r *Rule, m map[string]any) bool {
	if op := str(m["op"]); op != "==" && op != "in" {
		return false
	}
	right, cut := flatten(m["right"])
	if len(right) == 0 || cut {
		return false // nothing to read, or a list longer than the cap: not trusted
	}
	left := asMap(m["left"])
	if meta := asMap(left["meta"]); meta != nil {
		switch str(meta["key"]) {
		case "iifname":
			if len(right) != 1 || r.Iif != "" {
				return false
			}
			r.Iif = right[0]
			return true
		case "l4proto":
			if len(right) != 1 || r.Proto != "" {
				return false
			}
			r.Proto = right[0]
			return true
		}
		return false
	}
	if ct := asMap(left["ct"]); ct != nil && str(ct["key"]) == "state" {
		r.Ct = append(r.Ct, right...)
		return true
	}
	if pl := asMap(left["payload"]); pl != nil {
		proto, field := str(pl["protocol"]), str(pl["field"])
		switch {
		case (proto == "tcp" || proto == "udp") && (field == "dport" || field == "sport"):
			if r.Proto != "" && r.Proto != proto {
				return false
			}
			r.Proto = proto
			if field == "dport" {
				r.Dport = append(r.Dport, right...)
			} else {
				r.Sport = append(r.Sport, right...)
			}
			return true
		case (proto == "ip" || proto == "ip6") && field == "saddr":
			if len(right) != 1 || r.Saddr != "" {
				return false
			}
			r.Saddr = right[0]
			return true
		}
	}
	return false
}

// maxRaw caps what is read from the reader socket.
const maxRaw = 8 << 20

// SocketReader returns a Collector.Run that connects to the firewall read socket and reads the whole answer
// (the output of `nft -j list ruleset`, printed by a one-shot unit that holds CAP_NET_ADMIN). It sends
// nothing, honours ctx for the connect and the read, and refuses an answer larger than 8 MiB.
func SocketReader(path string) func(ctx context.Context) ([]byte, error) {
	return func(ctx context.Context) ([]byte, error) {
		var d net.Dialer
		conn, err := d.DialContext(ctx, "unix", path)
		if err != nil {
			return nil, fmt.Errorf("firewall reader: %w", err)
		}
		defer conn.Close()
		if dl, ok := ctx.Deadline(); ok {
			_ = conn.SetDeadline(dl)
		}
		raw, err := io.ReadAll(io.LimitReader(conn, maxRaw+1))
		if err != nil {
			return nil, fmt.Errorf("firewall reader: %w", err)
		}
		if len(raw) > maxRaw {
			return nil, fmt.Errorf("firewall reader: answer larger than %d bytes", maxRaw)
		}
		return raw, nil
	}
}
