// SPDX-License-Identifier: Apache-2.0

package fabric

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type qrVectors struct {
	Reasons []string `json:"reasons"`
	Valid   []struct {
		Name    string `json:"name"`
		Payload string `json:"payload"`
		Expect  struct {
			Version int    `json:"version"`
			Code    string `json:"code"`
			CA      string `json:"ca"`
			Hub     string `json:"hub"`
			Kind    string `json:"kind"`
			Alt     string `json:"alt"`
			MDNS    string `json:"mdns"`
		} `json:"expect"`
	} `json:"valid"`
	Hostile []struct {
		Name    string `json:"name"`
		Payload string `json:"payload"`
		Reason  string `json:"reason"`
	} `json:"hostile"`
}

// The shared vectors (FABRIC §4.3): Python (core/tests/test_join_qr.py) and TypeScript
// (sdk/ts/test/joinqr.test.ts) run the same file, so all three parsers agree on every payload.
func TestParseQRSharedVectors(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("..", "..", "sdk", "testdata", "join-qr", "vectors.json"))
	if err != nil {
		t.Fatal(err)
	}
	var v qrVectors
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatal(err)
	}
	if len(v.Valid) < 10 || len(v.Hostile) < 50 {
		t.Fatalf("vectors file too small: %d valid, %d hostile", len(v.Valid), len(v.Hostile))
	}
	for _, c := range v.Valid {
		tk, err := ParseQR(c.Payload)
		if err != nil {
			t.Errorf("%s: refused: %v", c.Name, err)
			continue
		}
		e := c.Expect
		if tk.Version != e.Version || tk.Code != e.Code || tk.CASHA != e.CA || tk.Hub != e.Hub ||
			tk.Kind != e.Kind || tk.Alt != e.Alt || tk.MDNS != e.MDNS {
			t.Errorf("%s: got %+v, want %+v", c.Name, *tk, e)
		}
		if tk.IsMachine() && tk.Validate() != nil {
			t.Errorf("%s: parsed machine ticket fails Validate: %v", c.Name, tk.Validate())
		}
	}
	for _, c := range v.Hostile {
		_, err := ParseQR(c.Payload)
		var qe *JoinQRError
		if !errors.As(err, &qe) {
			t.Errorf("%s: want reason %q, got %v", c.Name, c.Reason, err)
		} else if qe.Reason != c.Reason {
			t.Errorf("%s: reason %q, want %q (%s)", c.Name, qe.Reason, c.Reason, qe.Msg)
		}
	}
}

func TestTicketIsMachine(t *testing.T) {
	for kind, want := range map[string]bool{"worker": true, "leaf": true, "phone": false, "desktop": false, "browser": false, "sensor": false} {
		if got := (&Ticket{Version: 2, Kind: kind}).IsMachine(); got != want {
			t.Errorf("v2 %s: IsMachine %v", kind, got)
		}
	}
	if !(&Ticket{Version: 1}).IsMachine() || (&Ticket{Version: 2}).IsMachine() {
		t.Error("a v1 ticket without a role is a machine ticket; a v2 one always names its kind")
	}
}

// Bytes that are not valid UTF-8 cannot come from the JSON vectors, so pin them here: any byte at
// or above 0x80 is `charset`, checked before the length (Go counts bytes, Python code points).
func TestParseQRRefusesNonASCIIBeforeLength(t *testing.T) {
	base := "onemind-join:v2?hub=https%3A%2F%2Fbox1.local&ca=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef&code=7KQ4-M2XP-9D3F&kind=worker"
	for _, p := range []string{"\xff", base + "\x80", "\xc3" + base, base + strings.Repeat("\u00e9", 300), strings.Repeat("\xfe", 700)} {
		_, err := ParseQR(p)
		var qe *JoinQRError
		if !errors.As(err, &qe) || qe.Reason != "charset" {
			t.Errorf("%q (%d bytes): want charset, got %v", p[:min(len(p), 20)], len(p), err)
		}
	}
}
