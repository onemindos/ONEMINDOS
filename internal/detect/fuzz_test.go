// SPDX-License-Identifier: Apache-2.0

package detect

// Native Go fuzz targets for the parsers that fill the heartbeat (docs/testing/PROPERTY-AND-FUZZ.md).
// `go test ./...` runs the seed corpus; `go test -fuzz=<Target> -fuzztime=30s ./internal/detect`
// explores.

import (
	"bytes"
	"encoding/json"
	"sort"
	"strconv"
	"strings"
	"testing"
)

// FuzzParseRAUC: whatever `rauc status --output-format=json` prints (a newer RAUC, a truncated
// pipe, garbage), ParseRAUC never panics and returns the contract §2 shape: present, slots a JSON
// array (never null), every slot named, the slots of each entry sorted by name, and no device path
// (often /dev/disk/by-id/... with the disk serial) anywhere in the encoded object.
func FuzzParseRAUC(f *testing.F) {
	f.Add([]byte(`{"compatible":"onemind-vm","booted":"A","slots":[{"rootfs.1":{"class":"rootfs","device":"/dev/disk/by-id/ata-SERIAL-part3","bootname":"B","state":"inactive","boot_status":"good","slot_status":{"bundle":{"version":"0.1.1"}}}},{"rootfs.0":{"class":"rootfs","device":"/dev/sda2","bootname":"A","state":"booted","boot_status":"good"}}]}`))
	f.Add([]byte(`{"booted":"","slots":null}`))
	f.Add([]byte(`{"slots":[{}, {"b":{}, "a":{}}]}`))
	f.Add([]byte(`{"slots":[{"x":{"slot_status":{"bundle":{"version":7}}}}]}`))
	f.Add([]byte(`not json`))
	f.Add([]byte{})
	f.Fuzz(func(t *testing.T, data []byte) {
		r := ParseRAUC(data)
		if !r.Present || r.Slots == nil {
			t.Fatalf("present=%v slots=nil:%v", r.Present, r.Slots == nil)
		}
		var rs raucStatus
		if json.Unmarshal(data, &rs) == nil {
			i := 0
			for _, m := range rs.Slots { // each entry's slots, in name order
				names := make([]string, 0, len(m))
				for n := range m {
					names = append(names, n)
				}
				sort.Strings(names)
				for _, n := range names {
					if r.Slots[i].Name != n {
						t.Fatalf("slot %d is %q, want %q", i, r.Slots[i].Name, n)
					}
					i++
				}
			}
			if i != len(r.Slots) {
				t.Fatalf("%d slots in, %d out", i, len(r.Slots))
			}
		} else if r.BootedSlot != nil || len(r.Slots) != 0 {
			t.Fatalf("unparsable input produced data: %+v", r)
		}
		b, err := json.Marshal(r)
		if err != nil {
			t.Fatal(err)
		}
		if bytes.Contains(b, []byte(`"device"`)) || !bytes.Contains(b, []byte(`"slots":[`)) {
			t.Fatalf("encoding %s", b)
		}
	})
}

// FuzzParseKV: the os-release / key=value parser never panics; every key it returns is trimmed,
// holds no '=' or newline and does not start with '#'; and its result is stable: writing the map
// back as KEY="value" lines (Go quoting) and parsing that again gives the same map.
func FuzzParseKV(f *testing.F) {
	f.Add([]byte("ID=debian\nVERSION_ID=\"13\"\nPRETTY_NAME=\"Debian GNU/Linux 13 (trixie)\"\n# comment\n\nONEMIND_VERSION='0.1.0'\n"))
	f.Add([]byte("A=\"unterminated\nB=\"esc\\\"aped\"\n=novalue\nnoequals\n  K  =  v  \r\n"))
	f.Add([]byte("X=\"\\u00e9\\x00\"\nX=second\n"))
	f.Fuzz(func(t *testing.T, data []byte) {
		if len(data) > 4096 {
			return // keeps every rewritten line under bufio.Scanner's 64 KiB token limit
		}
		m := parseKV(data, "=")
		for k := range m {
			if k != strings.TrimSpace(k) || strings.HasPrefix(k, "#") || strings.Contains(k, "=") || strings.ContainsAny(k, "\n") {
				t.Fatalf("bad key %q", k)
			}
		}
		keys := make([]string, 0, len(m))
		for k := range m {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		var out bytes.Buffer
		for _, k := range keys {
			out.WriteString(k + "=" + strconv.Quote(m[k]) + "\n")
		}
		again := parseKV(out.Bytes(), "=")
		if len(again) != len(m) {
			t.Fatalf("round trip lost keys:\n%q\n%q", m, again)
		}
		for k, v := range m {
			if again[k] != v {
				t.Fatalf("round trip %q: %q -> %q (written %q)", k, v, again[k], out.String())
			}
		}
	})
}
