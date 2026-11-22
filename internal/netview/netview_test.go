// SPDX-License-Identifier: Apache-2.0

package netview

import (
	"errors"
	"net"
	"reflect"
	"testing"
	"time"
)

// Fixtures use RFC 5737 documentation addresses and the documentation MAC range (00-00-5E-00-53-xx, RFC 7042).
const (
	// 192.0.2.1 and 198.51.100.7 as /proc prints them (host order, little-endian words).
	gw4      = "010200C0"
	tcpTable = `  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 1 0
   1: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 2 1 0
   2: 0A0200C0:01BB 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 3 1 0
   3: 0A0200C0:C350 0100007F:1F90 01 00000000:00000000 00:00000000 00000000     0        0 4 1 0
   4: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 5 1 0
`
	tcp6Table = `  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000000000000000000000000000:0016 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 1 0
   1: 00000000000000000000000001000000:1F90 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 2 1 0
`
	udpTable = `  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode ref pointer drops
   0: 00000000:14E9 00000000:0000 07 00000000:00000000 00:00000000 00000000     0        0 1 2 0 0
`
	routeTable = `Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask		MTU	Window	IRTT
eth0	00000000	` + gw4 + `	0003	0	0	100	00000000	0	0	0
eth0	000200C0	00000000	0001	0	0	100	00FFFFFF	0	0	0
`
	route6Table = `00000000000000000000000000000000 00 00000000000000000000000000000000 00 20010db8000000000000000000000001 00000400 00000001 00000000 00000003     eth0
fe800000000000000000000000000000 40 00000000000000000000000000000000 00 00000000000000000000000000000000 00000100 00000001 00000000 00000001     eth0
`
	wirelessTable = `Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
wlan0: 0000   60.  -50.  -256        0      0      0      0      0        0
`
)

func fixture() Sources {
	files := map[string]string{
		"/sys/class/net/lo/type":           "772\n",
		"/sys/class/net/lo/operstate":      "unknown\n",
		"/sys/class/net/eth0/type":         "1\n",
		"/sys/class/net/eth0/operstate":    "up\n",
		"/sys/class/net/wlan0/operstate":   "down\n",
		"/sys/class/net/cni0/operstate":    "up\n",
		"/proc/net/tcp":                    tcpTable,
		"/proc/net/tcp6":                   tcp6Table,
		"/proc/net/udp":                    udpTable,
		"/proc/net/route":                  routeTable,
		"/proc/net/ipv6_route":             route6Table,
		"/proc/net/wireless":               wirelessTable,
		"/run/systemd/resolve/resolv.conf": "nameserver 192.0.2.53\nnameserver 2001:db8::53\nnameserver not-an-ip\nsearch example.test\n",
		"/etc/resolv.conf":                 "nameserver 127.0.0.53\n",
	}
	exists := map[string]bool{
		"/sys/class/net/eth0/device": true, "/sys/class/net/wlan0/phy80211": true, "/sys/class/net/cni0/bridge": true,
	}
	mac := func(s string) net.HardwareAddr { m, _ := net.ParseMAC(s); return m }
	ifs := []net.Interface{
		{Name: "wlan0", MTU: 1500, HardwareAddr: mac("00:00:5e:00:53:02")},
		{Name: "lo", MTU: 65536, Flags: net.FlagLoopback},
		{Name: "eth0", MTU: 1500, HardwareAddr: mac("00:00:5e:00:53:01")},
		{Name: "cni0", MTU: 1450, HardwareAddr: mac("00:00:5e:00:53:03")},
	}
	addrs := map[string][]string{
		"eth0": {"192.0.2.10/24", "2001:db8::10/64"}, "lo": {"127.0.0.1/8", "::1/128"}, "cni0": {"198.51.100.1/24"},
	}
	return Sources{
		Interfaces: func() ([]net.Interface, error) { return ifs, nil },
		Addrs: func(i net.Interface) ([]net.Addr, error) {
			var out []net.Addr
			for _, a := range addrs[i.Name] {
				_, n, _ := net.ParseCIDR(a)
				ip, _, _ := net.ParseCIDR(a)
				n.IP = ip
				out = append(out, n)
			}
			return out, nil
		},
		ReadFile: func(p string) ([]byte, error) {
			if s, ok := files[p]; ok {
				return []byte(s), nil
			}
			return nil, errors.New("missing")
		},
		Exists: func(p string) bool { return exists[p] },
		Now:    func() time.Time { return time.Date(2026, 11, 20, 12, 0, 0, 0, time.UTC) },
	}
}

func TestCollectInterfaces(t *testing.T) {
	v, err := fixture().Collect()
	if err != nil {
		t.Fatal(err)
	}
	if v.Schema != Schema || !v.At.Equal(time.Date(2026, 11, 20, 12, 0, 0, 0, time.UTC)) {
		t.Fatalf("header: %+v", v)
	}
	var names, kinds []string
	for _, i := range v.Interfaces {
		names, kinds = append(names, i.Name), append(kinds, i.Kind)
	}
	if !reflect.DeepEqual(names, []string{"cni0", "eth0", "lo", "wlan0"}) || !reflect.DeepEqual(kinds, []string{"bridge", "ethernet", "loopback", "wifi"}) {
		t.Fatalf("names %v kinds %v", names, kinds)
	}
	eth := v.Interfaces[1]
	if eth.State != "up" || eth.MAC != "00:00:5e:00:53:01" || eth.MTU != 1500 || !reflect.DeepEqual(eth.Addresses, []string{"192.0.2.10/24", "2001:db8::10/64"}) {
		t.Fatalf("eth0: %+v", eth)
	}
	if lo := v.Interfaces[2]; lo.MAC != "" {
		t.Fatalf("loopback must carry no MAC: %+v", lo)
	}
	wl := v.Interfaces[3]
	if wl.Wifi == nil || wl.Wifi.SignalDBm == nil || *wl.Wifi.SignalDBm != -50 || wl.State != "down" {
		t.Fatalf("wlan0: %+v", wl)
	}
	if eth.Wifi != nil {
		t.Fatal("only Wi-Fi interfaces carry a wifi object")
	}
}

func TestCollectGatewaysAndDNS(t *testing.T) {
	v, _ := fixture().Collect()
	want := []Gateway{{Interface: "eth0", Via: "192.0.2.1", Family: "ipv4"}, {Interface: "eth0", Via: "2001:db8::1", Family: "ipv6"}}
	if !reflect.DeepEqual(v.Gateways, want) {
		t.Fatalf("gateways %+v", v.Gateways)
	}
	if !reflect.DeepEqual(v.DNS, []string{"192.0.2.53", "2001:db8::53"}) {
		t.Fatalf("dns %v (upstream servers, not the stub, and no junk)", v.DNS)
	}
}

func TestCollectPorts(t *testing.T) {
	v, _ := fixture().Collect()
	want := []Port{
		{"tcp", "0.0.0.0", 22, "any"}, {"tcp", "::", 22, "any"},
		{"tcp", "192.0.2.10", 443, "address"}, {"udp", "0.0.0.0", 5353, "any"},
		{"tcp", "127.0.0.1", 8080, "loopback"}, {"tcp", "::1", 8080, "loopback"},
	}
	if len(v.Ports) != len(want) {
		t.Fatalf("ports %+v", v.Ports)
	}
	for _, w := range want {
		found := false
		for _, p := range v.Ports {
			found = found || p == w
		}
		if !found {
			t.Errorf("missing %+v in %+v", w, v.Ports)
		}
	}
	for i := 1; i < len(v.Ports); i++ {
		if v.Ports[i-1].Port > v.Ports[i].Port {
			t.Fatalf("not sorted by port: %+v", v.Ports)
		}
	}
}

func TestCollectSurvivesMissingSources(t *testing.T) {
	s := fixture()
	s.ReadFile = func(string) ([]byte, error) { return nil, errors.New("denied") }
	v, err := s.Collect()
	if err != nil || len(v.Interfaces) != 4 || len(v.Ports) != 0 || len(v.Gateways) != 0 || len(v.DNS) != 0 {
		t.Fatalf("%+v %v", v, err)
	}
	for _, i := range v.Interfaces {
		if i.State != "unknown" {
			t.Fatalf("an unreadable state is reported as unknown: %+v", i)
		}
	}
	s.Interfaces = func() ([]net.Interface, error) { return nil, errors.New("netlink") }
	if _, err := s.Collect(); err == nil {
		t.Fatal("no interface list is an error")
	}
}

func TestHexAddrRejectsGarbage(t *testing.T) {
	for _, h := range []string{"", "zz", "0102", "010203040506070809"} {
		if _, ok := hexAddr(h, true); ok {
			t.Errorf("%q accepted", h)
		}
	}
}
