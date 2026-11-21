// SPDX-License-Identifier: Apache-2.0

// Package netview reads the box's network facts for the dashboard's Network screen (NET-UI-01,
// #239): interfaces and their addresses, default gateways, DNS servers, Wi-Fi signal, and what is
// listening. It is read-only: it opens files and asks the kernel, and changes nothing.
//
// It runs inside `onemindd host serve` (GET /v1/network), on the host, because the gateway runs in
// a container and cannot see the host's interfaces. Node heartbeats are not used: their contract
// (sdk/contracts/poc-v0.md section 2) forbids IP and MAC addresses.
//
// Sources are injected so tests use fixtures instead of the machine they run on.
package netview

import (
	"bufio"
	"bytes"
	"encoding/hex"
	"net"
	"net/netip"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Schema names the document's shape.
const Schema = "onemind.netview/v1"

// Caps keep one answer small whatever the host looks like.
const (
	maxInterfaces = 64
	maxAddrs      = 16
	maxPorts      = 400
)

// View is GET /v1/network.
type View struct {
	Schema     string      `json:"schema"`
	At         time.Time   `json:"at"`
	Interfaces []Interface `json:"interfaces"`
	Gateways   []Gateway   `json:"gateways"`
	DNS        []string    `json:"dns"`
	Ports      []Port      `json:"ports"`
}

// Interface is one network interface.
type Interface struct {
	Name      string   `json:"name"`
	Kind      string   `json:"kind"` // ethernet, wifi, loopback, bridge, virtual
	State     string   `json:"state"`
	MAC       string   `json:"mac,omitempty"`
	MTU       int      `json:"mtu"`
	Addresses []string `json:"addresses"` // CIDR form, e.g. 192.0.2.10/24
	Wifi      *Wifi    `json:"wifi,omitempty"`
}

// Wifi is what /proc/net/wireless reports. The network name needs nl80211 (the iw tool), which the
// image does not ship, so it is not reported.
type Wifi struct {
	SignalDBm *int `json:"signal_dbm"`
}

// Gateway is one default route.
type Gateway struct {
	Interface string `json:"interface"`
	Via       string `json:"via"`
	Family    string `json:"family"` // ipv4 or ipv6
}

// Port is one listening socket.
type Port struct {
	Proto string `json:"proto"` // tcp or udp
	Addr  string `json:"addr"`
	Port  int    `json:"port"`
	Scope string `json:"scope"` // any (every interface), loopback, address (one address)
}

// Sources is everything the collector reads from the machine.
type Sources struct {
	Interfaces func() ([]net.Interface, error)
	Addrs      func(net.Interface) ([]net.Addr, error)
	ReadFile   func(path string) ([]byte, error)
	Exists     func(path string) bool
	Now        func() time.Time
}

// Collect gathers one View. A source that cannot be read leaves its part empty; only the
// interface list failing is an error, because without it there is nothing to show.
func (s Sources) Collect() (View, error) {
	v := View{Schema: Schema, At: s.Now().UTC(), Interfaces: []Interface{}, Gateways: []Gateway{}, DNS: []string{}, Ports: []Port{}}
	ifs, err := s.Interfaces()
	if err != nil {
		return v, err
	}
	sort.Slice(ifs, func(i, j int) bool { return ifs[i].Name < ifs[j].Name })
	wireless := s.wireless()
	for _, nif := range ifs {
		if len(v.Interfaces) == maxInterfaces {
			break
		}
		i := Interface{Name: nif.Name, Kind: s.kind(nif.Name), State: s.sysfs(nif.Name, "operstate", "unknown"), MTU: nif.MTU, Addresses: []string{}}
		if nif.Flags&net.FlagLoopback == 0 && len(nif.HardwareAddr) == 6 {
			i.MAC = nif.HardwareAddr.String()
		}
		if addrs, err := s.Addrs(nif); err == nil {
			for _, a := range addrs {
				if p, err := netip.ParsePrefix(a.String()); err == nil && len(i.Addresses) < maxAddrs {
					i.Addresses = append(i.Addresses, p.String())
				}
			}
			sort.Strings(i.Addresses)
		}
		if i.Kind == "wifi" {
			i.Wifi = &Wifi{SignalDBm: wireless[nif.Name]}
		}
		v.Interfaces = append(v.Interfaces, i)
	}
	v.Gateways = s.gateways()
	v.DNS = s.dns()
	v.Ports = s.ports()
	return v, nil
}

func (s Sources) sysfs(iface, file, def string) string {
	b, err := s.ReadFile("/sys/class/net/" + iface + "/" + file)
	if t := strings.TrimSpace(string(b)); err == nil && t != "" && len(t) <= 32 {
		return t
	}
	return def
}

// kind uses the kernel's own markers, so a Wi-Fi card is told from a cable port from a container veth.
func (s Sources) kind(name string) string {
	base := "/sys/class/net/" + name
	switch {
	case s.sysfs(name, "type", "") == "772":
		return "loopback"
	case s.Exists(base + "/phy80211"):
		return "wifi"
	case s.Exists(base + "/bridge"):
		return "bridge"
	case s.Exists(base + "/device"):
		return "ethernet"
	}
	return "virtual"
}

// wireless parses /proc/net/wireless: "wlan0: 0000 60. -50. -256 ..." (the level is dBm when negative).
func (s Sources) wireless() map[string]*int {
	out := map[string]*int{}
	b, err := s.ReadFile("/proc/net/wireless")
	if err != nil {
		return out
	}
	sc := bufio.NewScanner(bytes.NewReader(b))
	for sc.Scan() {
		name, rest, ok := strings.Cut(sc.Text(), ":")
		f := strings.Fields(rest)
		if !ok || len(f) < 3 {
			continue
		}
		if lv, err := strconv.ParseFloat(strings.TrimSuffix(f[2], "."), 64); err == nil && lv < 0 && lv > -200 {
			d := int(lv)
			out[strings.TrimSpace(name)] = &d
		}
	}
	return out
}

// gateways reads /proc/net/route (IPv4, per-word little-endian hex) and /proc/net/ipv6_route (plain hex).
func (s Sources) gateways() []Gateway {
	out := []Gateway{}
	if b, err := s.ReadFile("/proc/net/route"); err == nil {
		sc := bufio.NewScanner(bytes.NewReader(b))
		sc.Scan() // header
		for sc.Scan() {
			f := strings.Fields(sc.Text())
			if len(f) < 8 || f[1] != "00000000" || f[7] != "00000000" {
				continue
			}
			if flags, err := strconv.ParseUint(f[3], 16, 32); err != nil || flags&2 == 0 { // RTF_GATEWAY
				continue
			}
			if ip, ok := hexAddr(f[2], true); ok && !ip.IsUnspecified() {
				out = append(out, Gateway{Interface: f[0], Via: ip.String(), Family: "ipv4"})
			}
		}
	}
	if b, err := s.ReadFile("/proc/net/ipv6_route"); err == nil {
		sc := bufio.NewScanner(bytes.NewReader(b))
		for sc.Scan() {
			f := strings.Fields(sc.Text())
			if len(f) < 10 || f[0] != strings.Repeat("0", 32) || f[1] != "00" {
				continue
			}
			if ip, ok := hexAddr(f[4], false); ok && !ip.IsUnspecified() {
				out = append(out, Gateway{Interface: f[9], Via: ip.String(), Family: "ipv6"})
			}
		}
	}
	return out
}

// dns lists the real upstream servers when systemd-resolved is in use (its 127.0.0.53 stub says nothing).
func (s Sources) dns() []string {
	out := []string{}
	for _, path := range []string{"/run/systemd/resolve/resolv.conf", "/etc/resolv.conf"} {
		b, err := s.ReadFile(path)
		if err != nil {
			continue
		}
		sc := bufio.NewScanner(bytes.NewReader(b))
		for sc.Scan() {
			f := strings.Fields(sc.Text())
			if len(f) >= 2 && f[0] == "nameserver" && len(out) < 8 {
				if a, err := netip.ParseAddr(f[1]); err == nil {
					out = append(out, a.String())
				}
			}
		}
		if len(out) > 0 {
			break
		}
	}
	return out
}

// ports lists sockets in LISTEN (tcp) or bound with no peer (udp), from /proc/net. This is what the
// box listens on, not what is reachable: the firewall's rules decide that and are not read here.
func (s Sources) ports() []Port {
	out := []Port{}
	seen := map[Port]bool{}
	for _, t := range []struct{ file, proto, state string }{
		{"tcp", "tcp", "0A"}, {"tcp6", "tcp", "0A"}, {"udp", "udp", "07"}, {"udp6", "udp", "07"},
	} {
		b, err := s.ReadFile("/proc/net/" + t.file)
		if err != nil {
			continue
		}
		sc := bufio.NewScanner(bytes.NewReader(b))
		sc.Scan()
		for sc.Scan() {
			f := strings.Fields(sc.Text())
			if len(f) < 4 || f[3] != t.state {
				continue
			}
			host, port, ok := strings.Cut(f[1], ":")
			ip, ok2 := hexAddr(host, true)
			n, err := strconv.ParseUint(port, 16, 16)
			if !ok || !ok2 || err != nil || n == 0 {
				continue
			}
			p := Port{Proto: t.proto, Addr: ip.String(), Port: int(n), Scope: "address"}
			switch {
			case ip.IsUnspecified():
				p.Scope = "any"
			case ip.IsLoopback():
				p.Scope = "loopback"
			}
			if !seen[p] {
				seen[p] = true
				out = append(out, p)
			}
		}
	}
	sort.Slice(out, func(i, j int) bool {
		a, b := out[i], out[j]
		if a.Port != b.Port {
			return a.Port < b.Port
		}
		if a.Proto != b.Proto {
			return a.Proto < b.Proto
		}
		return a.Addr < b.Addr
	})
	if len(out) > maxPorts {
		out = out[:maxPorts]
	}
	return out
}

// hexAddr decodes an address from /proc/net: 8 hex digits (IPv4) or 32 (IPv6). The tcp, udp and
// route tables print each 32-bit word in host byte order (wordSwap, little-endian machines);
// ipv6_route prints plain network-order hex.
func hexAddr(h string, wordSwap bool) (netip.Addr, bool) {
	b, err := hex.DecodeString(h)
	if err != nil || (len(b) != 4 && len(b) != 16) {
		return netip.Addr{}, false
	}
	if wordSwap {
		for i := 0; i+4 <= len(b); i += 4 {
			b[i], b[i+1], b[i+2], b[i+3] = b[i+3], b[i+2], b[i+1], b[i]
		}
	}
	a, ok := netip.AddrFromSlice(b)
	return a.Unmap(), ok
}

// System is the real machine.
func System(read func(string) ([]byte, error), exists func(string) bool) Sources {
	return Sources{Interfaces: net.Interfaces, Addrs: func(i net.Interface) ([]net.Addr, error) { return i.Addrs() },
		ReadFile: read, Exists: exists, Now: time.Now}
}
