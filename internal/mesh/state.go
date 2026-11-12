// SPDX-License-Identifier: Apache-2.0

package mesh

import (
	"net/netip"
	"sort"
	"strings"
	"time"
)

// Mesh states and paths (NETWORKING.md §12, §15).
const (
	StateUp   = "up"   // tailscaled Running with a mesh address
	StateDown = "down" // installed but not Running, or tailscaled unreachable
	StateNone = "none" // tailscale not installed: no mesh on this machine

	PathDirect  = "direct"  // WireGuard over a direct UDP path
	PathRelayed = "relayed" // through a DERP relay (embedded or the relay VM)
	PathNone    = "none"    // no peer is connected
)

// HubTag is the ACL tag the hub's pre-auth key carries (§6.1).
const HubTag = "tag:onemind-hub"

// activeWindow is how recent a WireGuard handshake must be for a peer to count
// as connected. WireGuard re-handshakes every 2 min while traffic flows
// (REKEY_AFTER_TIME = 120 s), so 3 min leaves one missed rekey of slack.
const activeWindow = 3 * time.Minute

// State is the full local view of the mesh. It contains mesh addresses and peer
// names, so it is served only on the loopback API and the local CLI; the
// heartbeat gets the reduced Heartbeat() object.
type State struct {
	State string `json:"state"`
	// Addr is this machine's mesh IPv4 address (empty unless up).
	Addr string `json:"addr,omitempty"`
	// Path summarises the connected peers: relayed if any connected peer is
	// relayed, else direct if any is connected, else none. On a worker or leaf
	// HubPath is the more useful field.
	Path string `json:"path"`
	// HubPath is the path to the hub (a peer tagged tag:onemind-hub), or "none"
	// when no hub peer is connected or this machine is the hub.
	HubPath string `json:"hub_path"`
	// LastHandshake is the most recent WireGuard handshake with any peer
	// (RFC 3339, UTC), nil when there has been none.
	LastHandshake *string `json:"last_handshake"`
	Peers         []Peer  `json:"peers"`
	// Health lists tailscaled's own warnings, verbatim.
	Health []string `json:"health,omitempty"`
	// Backend is tailscaled's BackendState (Running, NeedsLogin, Stopped, …).
	Backend string `json:"backend,omitempty"`
	Error   string `json:"error,omitempty"`
}

// Peer is one other mesh machine or device as this machine sees it.
type Peer struct {
	Name          string   `json:"name"`
	Addr          string   `json:"addr,omitempty"`
	Tags          []string `json:"tags,omitempty"`
	Online        bool     `json:"online"`
	Path          string   `json:"path"`
	LastHandshake *string  `json:"last_handshake"`
}

// Heartbeat is the optional, additive heartbeat object (contract §2, proposed
// §12.16 in NETWORKING.md §15). It deliberately carries no addresses or peer
// names: contract §2 forbids IP addresses in the heartbeat, and the gateway
// reads mesh addresses from Headscale instead.
type Heartbeat struct {
	State         string  `json:"state"`
	Path          string  `json:"path"`
	HubPath       string  `json:"hub_path"`
	Peers         int     `json:"peers"`
	Direct        int     `json:"direct"`
	Relayed       int     `json:"relayed"`
	LastHandshake *string `json:"last_handshake"`
}

// Heartbeat reduces s to the privacy-safe heartbeat object.
func (s *State) Heartbeat() *Heartbeat {
	h := &Heartbeat{State: s.State, Path: s.Path, HubPath: s.HubPath, Peers: len(s.Peers), LastHandshake: s.LastHandshake}
	if h.HubPath == "" {
		h.HubPath = PathNone
	}
	for _, p := range s.Peers {
		switch p.Path {
		case PathDirect:
			h.Direct++
		case PathRelayed:
			h.Relayed++
		}
	}
	return h
}

func rfc3339(t time.Time) *string {
	if t.IsZero() || t.Unix() <= 0 {
		return nil
	}
	s := t.UTC().Format(time.RFC3339)
	return &s
}

// meshIPv4 returns the first address in the mesh range, or "".
func meshIPv4(ips []string) string {
	for _, s := range ips {
		if ip, err := netip.ParseAddr(s); err == nil && ip.Is4() && meshPrefix.Contains(ip) {
			return ip.String()
		}
	}
	return ""
}

// peerPath decides one peer's path. A direct UDP address (CurAddr) means
// direct whatever the handshake age; otherwise a recent handshake means DERP
// or a peer relay carried it; otherwise the peer is idle.
func peerPath(p *tsPeer, now time.Time) string {
	if p.CurAddr != "" {
		return PathDirect
	}
	if !p.LastHandshake.IsZero() && now.Sub(p.LastHandshake) <= activeWindow && (p.Relay != "" || p.PeerRelay != "") {
		return PathRelayed
	}
	return PathNone
}

func hasTag(tags []string, t string) bool {
	for _, x := range tags {
		if x == t {
			return true
		}
	}
	return false
}

func fromStatus(st *tsStatus, now time.Time) *State {
	s := &State{State: StateDown, Path: PathNone, HubPath: PathNone, Peers: []Peer{}, Backend: st.BackendState, Health: st.Health}
	if st.Self != nil {
		s.Addr = meshIPv4(st.Self.TailscaleIPs)
	}
	if st.BackendState == "Running" && s.Addr != "" {
		s.State = StateUp
	}
	var last time.Time
	anyDirect, anyRelayed := false, false
	for _, p := range st.Peer {
		if p == nil {
			continue
		}
		name := p.HostName
		if dn := strings.TrimSuffix(p.DNSName, "."); dn != "" {
			name = strings.SplitN(dn, ".", 2)[0]
		}
		path := peerPath(p, now)
		if s.State != StateUp {
			path = PathNone
		}
		s.Peers = append(s.Peers, Peer{
			Name: name, Addr: meshIPv4(p.TailscaleIPs), Tags: p.Tags, Online: p.Online,
			Path: path, LastHandshake: rfc3339(p.LastHandshake),
		})
		switch path {
		case PathDirect:
			anyDirect = true
		case PathRelayed:
			anyRelayed = true
		}
		if hasTag(p.Tags, HubTag) && path != PathNone {
			s.HubPath = path
		}
		if p.LastHandshake.After(last) {
			last = p.LastHandshake
		}
	}
	switch {
	case anyRelayed:
		s.Path = PathRelayed
	case anyDirect:
		s.Path = PathDirect
	}
	s.LastHandshake = rfc3339(last)
	sort.Slice(s.Peers, func(i, j int) bool { return s.Peers[i].Name < s.Peers[j].Name })
	return s
}
