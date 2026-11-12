// SPDX-License-Identifier: Apache-2.0

// Package mesh enrolls this machine into the hub's Headscale coordinator and
// reports its mesh state (docs/architecture/NETWORKING.md §5, §12).
//
// It drives the system Tailscale client (tailscaled + the tailscale CLI, BSD-3)
// instead of embedding tsnet. The reasons, in order:
//
//  1. k3s (flannel-iface tailscale0, §8), the NATS leaf (§7) and every other
//     process on the box must use the mesh, so it needs the kernel TUN
//     interface that only the system daemon provides. tsnet gives one Go
//     process a userspace node and nothing else.
//  2. A second node identity inside onemindd would double the Headscale
//     machines per box and the Pi's memory budget (§14).
//  3. It keeps tailscale's large dependency tree out of onemindd (go.mod stays
//     Apache/MIT/BSD with no new modules), and the pinned tailscale package is
//     updated with the OS image, not with the agent.
//
// The CLI (`tailscale up`, `tailscale status --json`) is used rather than the
// raw LocalAPI socket: `--auth-key file:<path>` keeps the one-time key out of
// argv (H-09), and the CLI is the interface tailscale documents. All calls go
// through the Runner interface so tests use a fake.
package mesh

import (
	"errors"
	"fmt"
	"net/netip"
	"net/url"
	"regexp"
	"strings"
)

// Bundle is the `mesh` block of the fabric join bundle (NETWORKING.md §5.1).
// AuthKey is a one-time Headscale pre-auth key: it is used once and never
// logged, stored or put on a command line.
type Bundle struct {
	ControlURL   string   `json:"control_url"`
	ControlAddrs []string `json:"control_addrs,omitempty"`
	CASHA256     string   `json:"ca_sha256,omitempty"`
	AuthKey      string   `json:"auth_key"`
	Hostname     string   `json:"hostname"`
	HubMeshIP    string   `json:"hub_mesh_ip,omitempty"`
	// ShieldsUp blocks all inbound mesh connections to this machine; set for
	// leaves (§5.1), which serve nothing to the mesh.
	ShieldsUp bool `json:"shields_up,omitempty"`
}

// meshPrefix is Headscale's IPv4 range (§3). Addresses outside it are not
// mesh addresses, whatever tailscale reports.
var meshPrefix = netip.MustParsePrefix("100.64.0.0/10")

// hostnameRe is one DNS label in lower case: the MagicDNS name of the node
// (node-<node_id>, §3).
var hostnameRe = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`)

var sha256Re = regexp.MustCompile(`^[0-9a-f]{64}$`)

// Validate checks the bundle before anything touches the system. Errors never
// include the auth key.
func (b *Bundle) Validate() error {
	u, err := url.Parse(b.ControlURL)
	if err != nil || u.Scheme != "https" || u.Host == "" || u.User != nil {
		return fmt.Errorf("control_url must be an https URL without credentials, got %q", b.ControlURL)
	}
	if u.RawQuery != "" || u.Fragment != "" {
		return fmt.Errorf("control_url must not carry a query or fragment, got %q", b.ControlURL)
	}
	if strings.TrimSpace(b.AuthKey) == "" {
		return errors.New("auth_key is empty")
	}
	if strings.ContainsAny(b.AuthKey, " \t\r\n") || len(b.AuthKey) > 512 {
		return errors.New("auth_key is malformed")
	}
	if !hostnameRe.MatchString(b.Hostname) {
		return fmt.Errorf("hostname must be one lower-case DNS label, got %q", b.Hostname)
	}
	if b.CASHA256 != "" && !sha256Re.MatchString(b.CASHA256) {
		return errors.New("ca_sha256 must be 64 lower-case hex characters")
	}
	if b.HubMeshIP != "" {
		ip, err := netip.ParseAddr(b.HubMeshIP)
		if err != nil || !meshPrefix.Contains(ip) {
			return fmt.Errorf("hub_mesh_ip must be an address in %s, got %q", meshPrefix, b.HubMeshIP)
		}
	}
	for _, a := range b.ControlAddrs {
		if _, err := netip.ParseAddr(a); err != nil {
			return fmt.Errorf("control_addrs: %q is not an IP address", a)
		}
	}
	return nil
}
