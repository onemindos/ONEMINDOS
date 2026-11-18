// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"
)

// auditGenesis is the prev_hash of the first line.
var auditGenesis = strings.Repeat("0", 64)

// Audit is the rescue console's own append-only, hash-chained log. The line
// format is the gateway's (core/onemind_core/audit.py): every line is JSON with
// seq, ts, event, principal, action_id, data, prev_hash and
// hash = sha256(prev_hash + canonical_json(line without prev_hash and hash)),
// so `onemind-audit-verify` checks this file too.
//
// It is a separate file on purpose. The gateway's chain belongs to the
// gateway's user and its process holds the sequence counter; a second writer
// would fork it. The console must also work with the gateway down, which is
// exactly when a shell is most likely to be wanted. A later change can
// publish these lines on the audit subject once the hub is reachable.
//
// It fails closed: a file that does not verify is never appended to.
type Audit struct {
	mu   sync.Mutex
	path string
	now  func() time.Time
	seq  int
	last string
}

// OpenAudit reads and verifies the chain at path (created on the first append).
func OpenAudit(path string, now func() time.Time) (*Audit, error) {
	if now == nil {
		now = time.Now
	}
	a := &Audit{path: path, now: now, last: auditGenesis}
	n, last, err := verifyAuditFile(path)
	if err != nil {
		return nil, err
	}
	a.seq, a.last = n, last
	return a, nil
}

// canonicalJSON is Python's json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False).
func canonicalJSON(v any) (string, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil { // map keys are sorted by encoding/json
		return "", err
	}
	s := strings.TrimSuffix(buf.String(), "\n")
	// Go escapes these two; Python with ensure_ascii=False does not.
	s = strings.NewReplacer("\\u2028", "\u2028", "\\u2029", "\u2029").Replace(s)
	return s, nil
}

func chainHash(prev string, body map[string]any) (string, error) {
	c, err := canonicalJSON(body)
	if err != nil {
		return "", err
	}
	d := sha256.Sum256([]byte(prev + c))
	return hex.EncodeToString(d[:]), nil
}

// Append writes one line and syncs it before returning. A returned error means
// the event is NOT on disk: callers that must not act unrecorded stop there.
func (a *Audit) Append(event string, principal map[string]any, data map[string]any) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if data == nil {
		data = map[string]any{}
	}
	body := map[string]any{
		"seq":       a.seq + 1,
		"ts":        a.now().UTC().Format("2006-01-02T15:04:05.000000Z"),
		"event":     event,
		"principal": principal,
		"action_id": nil,
		"data":      data,
	}
	h, err := chainHash(a.last, body)
	if err != nil {
		return err
	}
	rec := map[string]any{}
	for k, v := range body {
		rec[k] = v
	}
	rec["prev_hash"], rec["hash"] = a.last, h
	line, err := canonicalJSON(rec)
	if err != nil {
		return err
	}
	f, err := os.OpenFile(a.path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	_, werr := f.WriteString(line + "\n")
	if werr == nil {
		werr = f.Sync()
	}
	if cerr := f.Close(); werr == nil {
		werr = cerr
	}
	if werr != nil {
		return werr
	}
	a.seq, a.last = body["seq"].(int), h
	return nil
}

// verifyAuditFile checks the whole chain; a missing file is an empty chain.
func verifyAuditFile(path string) (n int, last string, err error) {
	last = auditGenesis
	f, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return 0, last, nil
	}
	if err != nil {
		return 0, "", err
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for line := 1; sc.Scan(); line++ {
		if len(bytes.TrimSpace(sc.Bytes())) == 0 {
			continue
		}
		var rec map[string]any
		dec := json.NewDecoder(bytes.NewReader(sc.Bytes()))
		dec.UseNumber()
		if err := dec.Decode(&rec); err != nil {
			return 0, "", fmt.Errorf("audit line %d: not JSON", line)
		}
		prev, _ := rec["prev_hash"].(string)
		got, _ := rec["hash"].(string)
		delete(rec, "prev_hash")
		delete(rec, "hash")
		if prev != last {
			return 0, "", fmt.Errorf("audit line %d: prev_hash does not match the previous line", line)
		}
		if seq, ok := rec["seq"].(json.Number); !ok || seq.String() != fmt.Sprint(n+1) {
			return 0, "", fmt.Errorf("audit line %d: seq out of order", line)
		}
		want, err := chainHash(prev, rec)
		if err != nil || want != got {
			return 0, "", fmt.Errorf("audit line %d: hash mismatch (line was altered)", line)
		}
		last = got
		n++
	}
	return n, last, sc.Err()
}
