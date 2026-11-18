// SPDX-License-Identifier: Apache-2.0

//go:build linux

package rescue

import (
	"bytes"
	"testing"
	"time"
)

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
