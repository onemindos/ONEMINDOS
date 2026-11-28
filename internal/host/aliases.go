// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"fmt"
	"net"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"
)

// FirstBootAlias is the name every box has answered to since the first boot; a rename keeps it.
const FirstBootAlias = "onemind"

// MergeAliases is the list of names (labels, without .local) the box keeps publishing after a rename from
// previous to next: what was published before, the name it had until now, and onemind. The new name itself
// is the host name, so avahi publishes it already; invalid lines are dropped.
func MergeAliases(existing []string, previous, next string) []string {
	set := map[string]bool{FirstBootAlias: true}
	for _, n := range append(existing, previous) {
		n = strings.ToLower(strings.TrimSpace(n))
		if hostnameRe.MatchString(n) {
			set[n] = true
		}
	}
	delete(set, next)
	out := make([]string, 0, len(set))
	for n := range set {
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}

// ReadAliases reads the alias list: one label per line, invalid lines ignored. No file: no aliases.
func ReadAliases(file string) []string {
	if file == "" {
		file = DefaultAliasesFile
	}
	b, err := os.ReadFile(file)
	if err != nil {
		return nil
	}
	var out []string
	for _, l := range strings.Split(string(b), "\n") {
		if l = strings.ToLower(strings.TrimSpace(l)); hostnameRe.MatchString(l) {
			out = append(out, l)
		}
	}
	return out
}

// primaryAddr is the IPv4 address the box uses to reach the LAN (no packet is sent: a UDP "connect" only picks a route).
func primaryAddr() (string, error) {
	c, err := net.Dial("udp4", "192.0.2.1:9")
	if err != nil {
		return "", err
	}
	defer c.Close()
	return c.LocalAddr().(*net.UDPAddr).IP.String(), nil
}

// RunAliases is `onemindd host mdns-aliases`: it publishes <alias>.local for every saved alias at the box's
// current address (avahi-publish -a), and starts them again when the address or the list changes, until ctx ends.
// avahi publishes only the host name, so without this onemind.local and the old name would stop answering.
func RunAliases(ctx context.Context, file string, poll time.Duration) error {
	var cmds []*exec.Cmd
	stop := func() {
		for _, c := range cmds {
			if c.Process != nil {
				_ = c.Process.Kill()
				_ = c.Wait()
			}
		}
		cmds = nil
	}
	defer stop()
	lastKey := ""
	for {
		names := ReadAliases(file)
		addr, err := primaryAddr()
		key := addr + "|" + strings.Join(names, ",")
		if err == nil && key != lastKey {
			stop()
			for _, n := range names {
				c := exec.CommandContext(ctx, "avahi-publish", "-a", "-R", n+".local", addr)
				if err := c.Start(); err != nil {
					return fmt.Errorf("avahi-publish %s.local: %w", n, err)
				}
				cmds = append(cmds, c)
			}
			lastKey = key
		}
		select {
		case <-ctx.Done():
			return nil
		case <-time.After(poll):
		}
	}
}
