// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"strings"
	"testing"
)

// The usage text: the groups from before the split, plus fabric and mesh (NET-P2).
const wantUsage = `usage:
  onemind node info [--root DIR] [--arch amd64|arm64] [--agent URL]
  onemind nodes --hub URL [--token TOKEN] [--json]
  onemind fabric join 'onemind-join:v1?…' [--hub-addr IP] [--timeout 20m]
  onemind fabric ticket [--hub URL] [--role worker|leaf] [--ttl 15m] [--token T] [--json]
  onemind fabric approve ACTION_ID [--hub URL] [--token T]
  onemind fabric status [--hub URL] [--token T] [--json]
  onemind mesh status [--json] [--leaf-monitor 127.0.0.1:8222]
  onemind update status [--config FILE] [--json]
  onemind update check  [--config FILE]
  onemind update apply  [--config FILE] [--no-reboot]
  onemind version
`

func TestUsageUnchanged(t *testing.T) {
	if got := Usage(); got != wantUsage {
		t.Fatalf("usage changed:\n%s", got)
	}
}

func TestPathsUniqueAndUsageMatchesPath(t *testing.T) {
	seen := map[string]bool{}
	for _, c := range Commands() {
		key := strings.Join(c.Path, " ")
		if seen[key] {
			t.Errorf("command %q registered twice", key)
		}
		seen[key] = true
		if !strings.HasPrefix(c.Usage, "onemind "+key) {
			t.Errorf("usage %q does not start with its path %q", c.Usage, key)
		}
		if c.Run == nil {
			t.Errorf("%q has no Run", key)
		}
	}
}

func TestDispatch(t *testing.T) {
	cases := []struct {
		args []string
		code int
		out  string
	}{
		{nil, 2, ""},
		{[]string{"node"}, 2, ""},
		{[]string{"update"}, 2, ""},
		{[]string{"update", "nope"}, 2, ""},
		{[]string{"nodez"}, 2, ""},
		{[]string{"version"}, 0, "onemind "},
		{[]string{"version", "extra"}, 0, "onemind "},
		{[]string{"nodes"}, 1, ""}, // --hub missing
	}
	for _, c := range cases {
		t.Setenv("ONEMIND_HUB", "")
		var out, errb bytes.Buffer
		code := Run(c.args, Env{Stdout: &out, Stderr: &errb})
		if code != c.code || !strings.HasPrefix(out.String(), c.out) {
			t.Errorf("%v: exit %d out %q err %q", c.args, code, out.String(), errb.String())
		}
		if code == 2 && errb.String() != wantUsage {
			t.Errorf("%v: stderr %q, want usage", c.args, errb.String())
		}
	}
}

func TestCustomGroupPlugsIn(t *testing.T) {
	saved := groups
	defer func() { groups = saved }()
	groups = append(append([]func() []Command{}, saved...), func() []Command {
		return []Command{{Path: []string{"node", "info", "deep"}, Usage: "onemind node info deep", Run: func(env *Env, args []string) error {
			env.Stdout.Write([]byte(strings.Join(args, ",")))
			return nil
		}}}
	})
	var out, errb bytes.Buffer
	if code := Run([]string{"node", "info", "deep", "a", "b"}, Env{Stdout: &out, Stderr: &errb}); code != 0 || out.String() != "a,b" {
		t.Fatalf("longest path must win: exit %d out %q", code, out.String())
	}
}
