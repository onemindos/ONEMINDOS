// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"unicode/utf8"
)

// CanonicalJSON encodes a value decoded with json.Decoder.UseNumber exactly
// as the gateway's signer does: Python's
//
//	json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
//
// (core/onemind_core/backups/jobs.py). Signed jobs (contract §12.11) are
// verified over these bytes, so both sides must agree byte for byte:
// keys sorted by code point, no spaces, every character outside printable
// ASCII written as a lower-case \uXXXX escape (surrogate pairs above
// U+FFFF), and \b \f \n \r \t in their short form. Floats are refused:
// their text differs between languages and no job needs one.
func CanonicalJSON(v any) ([]byte, error) {
	var b bytes.Buffer
	if err := writeCanonical(&b, v); err != nil {
		return nil, err
	}
	return b.Bytes(), nil
}

var integerRe = regexp.MustCompile(`^-?(0|[1-9][0-9]*)$`)

func writeCanonical(b *bytes.Buffer, v any) error {
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		b.WriteString(strconv.FormatBool(x))
	case json.Number:
		if !integerRe.MatchString(string(x)) {
			return fmt.Errorf("number %s: only integers are allowed in signed jobs", x)
		}
		b.WriteString(string(x))
	case string:
		return writeCanonicalString(b, x)
	case []any:
		b.WriteByte('[')
		for i, e := range x {
			if i > 0 {
				b.WriteByte(',')
			}
			if err := writeCanonical(b, e); err != nil {
				return err
			}
		}
		b.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys) // byte order of valid UTF-8 = code point order
		b.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				b.WriteByte(',')
			}
			if err := writeCanonicalString(b, k); err != nil {
				return err
			}
			b.WriteByte(':')
			if err := writeCanonical(b, x[k]); err != nil {
				return err
			}
		}
		b.WriteByte('}')
	default:
		return fmt.Errorf("unsupported JSON value %T", v)
	}
	return nil
}

func writeCanonicalString(b *bytes.Buffer, s string) error {
	if !utf8.ValidString(s) {
		return fmt.Errorf("string is not valid UTF-8")
	}
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			switch {
			case r >= 0x20 && r <= 0x7e:
				b.WriteRune(r)
			case r < 0x10000:
				fmt.Fprintf(b, `\u%04x`, r)
			default:
				n := r - 0x10000
				fmt.Fprintf(b, `\u%04x\u%04x`, 0xd800|((n>>10)&0x3ff), 0xdc00|(n&0x3ff))
			}
		}
	}
	b.WriteByte('"')
	return nil
}

// decodeUseNumber parses one JSON value, keeping numbers as their text.
func decodeUseNumber(data []byte) (any, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	var v any
	if err := dec.Decode(&v); err != nil {
		return nil, err
	}
	if dec.More() {
		return nil, fmt.Errorf("trailing data after the JSON value")
	}
	return v, nil
}
