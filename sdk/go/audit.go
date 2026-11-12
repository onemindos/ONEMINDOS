// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// AuditService is /v1/audit (contract §12.16): read-only.
type AuditService struct{ c *Client }

// AuditQuery filters GET /v1/audit/events. Zero values are left out.
type AuditQuery struct {
	AfterSeq, BeforeSeq int
	Event               string // comma = OR, `*` glob, e.g. "action.*"
	PrincipalID         string
	ActionID            string
	Since, Until        string // RFC 3339
	Limit               int    // default 100, at most 500
}

func (q AuditQuery) values() url.Values {
	v := url.Values{}
	if q.AfterSeq > 0 {
		v.Set("after_seq", strconv.Itoa(q.AfterSeq))
	}
	if q.BeforeSeq > 0 {
		v.Set("before_seq", strconv.Itoa(q.BeforeSeq))
	}
	for k, s := range map[string]string{"event": q.Event, "principal_id": q.PrincipalID, "action_id": q.ActionID, "since": q.Since, "until": q.Until} {
		if s != "" {
			v.Set(k, s)
		}
	}
	if q.Limit > 0 {
		v.Set("limit", strconv.Itoa(q.Limit))
	}
	return v
}

var linkNext = regexp.MustCompile(`<([^>]+)>;\s*rel="next"`)

// List is operation audit.events.list. more is true when the gateway sent a Link rel="next";
// continue with AfterSeq set to the last record's Seq.
func (s *AuditService) List(ctx context.Context, q AuditQuery) (recs []AuditRecord, more bool, err error) {
	path := "/v1/audit/events"
	if enc := q.values().Encode(); enc != "" {
		path += "?" + enc
	}
	hdr, err := s.c.do(ctx, request{method: http.MethodGet, path: path, retry: true}, &recs)
	if err != nil {
		return nil, false, err
	}
	return recs, linkNext.MatchString(hdr.Get("Link")), nil
}

// Get is operation audit.events.get.
func (s *AuditService) Get(ctx context.Context, seq int) (*AuditRecord, error) {
	var v AuditRecord
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/audit/events/"+strconv.Itoa(seq), nil, &v)
}

// Verify is operation audit.verify: the gateway recomputes its own chain.
func (s *AuditService) Verify(ctx context.Context) (*AuditVerify, error) {
	var v AuditVerify
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/audit/verify", nil, &v)
}

// ---- offline verification --------------------------------------------------------------------

// Genesis is the prev_hash of the first audit record.
const Genesis = "0000000000000000000000000000000000000000000000000000000000000000"

// ChainResult is the outcome of VerifyChain, shaped like GET /v1/audit/verify.
type ChainResult struct {
	OK          bool       `json:"ok"`
	Records     int        `json:"records"`
	Head        *AuditHead `json:"head"`
	FirstBadSeq *int       `json:"first_bad_seq"`
	Reason      string     `json:"reason"`
}

// VerifyChain checks a JSONL audit log with the exact rule of core/onemind_core/audit.py:
// hash = sha256(prev_hash + canonical_json(record without prev_hash and hash)), canonical JSON
// being sorted keys, no whitespace, UTF-8 (Python's json.dumps(..., ensure_ascii=False)).
// A file alone proves only that the chain is self-consistent; a rewrite of the whole log is
// caught only by a checkpoint kept off the box.
func VerifyChain(r io.Reader) ChainResult {
	prev, n := Genesis, 0
	var head *AuditHead
	bad := func(reason string) ChainResult {
		s := n + 1
		return ChainResult{Records: n, Head: head, FirstBadSeq: &s, Reason: reason}
	}
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 64*1024), 16<<20)
	for sc.Scan() {
		line := bytes.TrimSpace(sc.Bytes())
		if len(line) == 0 {
			continue
		}
		dec := json.NewDecoder(bytes.NewReader(line))
		dec.UseNumber()
		var rec map[string]any
		if err := dec.Decode(&rec); err != nil {
			return bad(fmt.Sprintf("seq %d: not a JSON audit record", n+1))
		}
		gotPrev, _ := rec["prev_hash"].(string)
		gotHash, _ := rec["hash"].(string)
		delete(rec, "prev_hash")
		delete(rec, "hash")
		if gotPrev != prev {
			return bad(fmt.Sprintf("seq %d: prev_hash does not match the previous record", n+1))
		}
		seq, ok := rec["seq"].(json.Number)
		if !ok || seq.String() != strconv.Itoa(n+1) {
			return bad(fmt.Sprintf("seq %v out of order (expected %d)", rec["seq"], n+1))
		}
		sum := sha256.Sum256([]byte(prev + CanonicalJSON(rec)))
		if hex.EncodeToString(sum[:]) != gotHash {
			return bad(fmt.Sprintf("seq %d: hash mismatch (record changed after it was written)", n+1))
		}
		prev, n = gotHash, n+1
		head = &AuditHead{Seq: n, Hash: gotHash}
	}
	if err := sc.Err(); err != nil {
		return bad("reading the log: " + err.Error())
	}
	return ChainResult{OK: true, Records: n, Head: head, Reason: "ok"}
}

// CanonicalJSON renders a value decoded with UseNumber exactly as Python's
// json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).
func CanonicalJSON(v any) string {
	var b strings.Builder
	canon(&b, v)
	return b.String()
}

func canon(b *strings.Builder, v any) {
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		if x {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case json.Number:
		b.WriteString(x.String()) // the file was written by Python: keep its literal
	case string:
		pyString(b, x)
	case []any:
		b.WriteByte('[')
		for i, e := range x {
			if i > 0 {
				b.WriteByte(',')
			}
			canon(b, e)
		}
		b.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys) // UTF-8 byte order = code point order = Python's str order
		b.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				b.WriteByte(',')
			}
			pyString(b, k)
			b.WriteByte(':')
			canon(b, x[k])
		}
		b.WriteByte('}')
	default:
		raw, _ := json.Marshal(x)
		b.Write(raw)
	}
}

func pyString(b *strings.Builder, s string) {
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		default:
			if r < 0x20 {
				fmt.Fprintf(b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
}
