// SPDX-License-Identifier: Apache-2.0

//go:build linux

package rescue

import (
	"bytes"
	"os"
	"regexp"
	"strings"
	"testing"
	"time"
)

// The pty starts the shell through os.Executable(), which in a test is this binary: act as the helper here.
func TestMain(m *testing.M) {
	if len(os.Args) > 1 && os.Args[1] == ShellHelperCommand {
		os.Exit(RunShellHelper(os.Args[2:]))
	}
	os.Exit(m.Run())
}

// runInPTY types a command into a fresh rescue shell and returns the output up to marker.
func runInPTY(t *testing.T, command, marker string) []byte {
	t.Helper()
	s, err := PTY{Shell: "/bin/sh"}.Spawn()
	if err != nil {
		t.Skipf("no pty here: %v", err)
	}
	defer s.Close()
	if _, err := s.Write([]byte(command + "\n")); err != nil {
		t.Fatal(err)
	}
	got := make(chan []byte, 1)
	go func() {
		var all []byte
		buf := make([]byte, 256)
		for {
			n, err := s.Read(buf)
			all = append(all, buf[:n]...)
			if bytes.Contains(all, []byte(marker)) || err != nil {
				got <- all
				return
			}
		}
	}()
	select {
	case b := <-got:
		return b
	case <-time.After(10 * time.Second):
		t.Fatal("no output from the shell")
	}
	return nil
}

// The shell holds no capability and cannot gain one, even when the console runs as root with capabilities
// (as the rescue unit does with CAP_DAC_READ_SEARCH). Meaningful when the test runs as root, e.g. in a container.
func TestPTYShellHasNoCapabilities(t *testing.T) {
	out := runInPTY(t, "grep -E '^(CapInh|CapPrm|CapEff|CapAmb|NoNewPrivs):' /proc/self/status; echo caps-$((1+1))", "caps-2")
	// The first line follows the prompt, so match the field anywhere; the echoed command has no "Cap...:".
	field := func(name string) string {
		m := regexp.MustCompile(name + `:\s+([0-9a-f]+)`).FindSubmatch(out)
		if m == nil {
			t.Fatalf("%s missing from /proc/self/status:\n%s", name, out)
		}
		return string(m[1])
	}
	for _, name := range []string{"CapInh", "CapPrm", "CapEff", "CapAmb"} {
		if v := field(name); strings.Trim(v, "0") != "" {
			t.Errorf("%s = %s in the rescue shell, want none", name, v)
		}
	}
	if v := field("NoNewPrivs"); v != "1" {
		t.Errorf("NoNewPrivs = %s in the rescue shell, want 1", v)
	}
}

// A real shell on a real pseudo-terminal: what is typed runs, the output comes back, Close ends it.
func TestPTYRunsAShell(t *testing.T) {
	s, err := PTY{Shell: "/bin/sh"}.Spawn()
	if err != nil {
		t.Skipf("no pty here: %v", err)
	}
	defer s.Close()
	if _, err := s.Write([]byte("echo rescue-$((20+22))\n")); err != nil {
		t.Fatal(err)
	}
	got := make(chan []byte, 1)
	go func() {
		var all []byte
		buf := make([]byte, 256)
		for {
			n, err := s.Read(buf)
			all = append(all, buf[:n]...)
			if bytes.Contains(all, []byte("rescue-42")) || err != nil {
				got <- all
				return
			}
		}
	}()
	select {
	case b := <-got:
		if !bytes.Contains(b, []byte("rescue-42")) {
			t.Fatalf("output = %q", b)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("no output from the shell")
	}
	_ = s.Close()
	select {
	case <-s.Done():
	case <-time.After(10 * time.Second):
		t.Fatal("the shell survived Close")
	}
}
