// SPDX-License-Identifier: Apache-2.0

// Package mcpbridge is `onemind mcp`: a stdio MCP server that forwards every message to the
// gateway's POST /mcp (docs/leap/dev/MCP.md §7). It is a dumb pipe on purpose: all checks stay
// in the gateway. Claude Code, Claude Desktop and other hosts start it as a local command, so the
// agent token lives in the OneMind config (or ONEMIND_TOKEN), never in the client's config file.
//
// Wire rules: one JSON-RPC message per stdin line, forwarded in order; each answer written as one
// line on stdout; HTTP 202 (a notification) writes nothing; 401/403/429 become a JSON-RPC error
// for that id plus a hint on stderr. Logs go to stderr and carry only method, id, status and
// duration: never the token, never a message body. Standard library only.
package mcpbridge

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// MaxMessage is the gateway's body limit; a longer line is refused locally.
const MaxMessage = 256 * 1024

// Config is where to forward to.
type Config struct {
	Hub   string // base URL, e.g. https://hub.local:8443
	Token string
	HTTP  *http.Client
	// Log receives one line per message (method, id, status, duration). Nil: no log.
	Log     func(format string, args ...any)
	Timeout time.Duration // per message, default 60 s
}

// Bridge forwards messages. Use Run for the stdio loop or Send for one message.
type Bridge struct {
	cfg       Config
	version   string // negotiated protocol revision, sent as MCP-Protocol-Version
	sessionID string
}

// New returns a bridge for cfg.
func New(cfg Config) *Bridge {
	if cfg.HTTP == nil {
		cfg.HTTP = &http.Client{}
	}
	if cfg.Timeout <= 0 {
		cfg.Timeout = 60 * time.Second
	}
	cfg.Hub = strings.TrimRight(cfg.Hub, "/")
	return &Bridge{cfg: cfg}
}

type envelope struct {
	ID     json.RawMessage `json:"id,omitempty"`
	Method string          `json:"method,omitempty"`
	Result json.RawMessage `json:"result,omitempty"`
}

// Run reads newline-delimited JSON-RPC from in and writes answers to out until in ends or ctx
// is cancelled. Messages are handled one at a time, so answers keep the order of requests.
func (b *Bridge) Run(ctx context.Context, in io.Reader, out io.Writer) error {
	rd := bufio.NewReaderSize(in, 64*1024)
	w := bufio.NewWriter(out)
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		line, err := readLine(rd)
		if len(bytes.TrimSpace(line)) > 0 {
			for _, ans := range b.Send(ctx, bytes.TrimSpace(line)) {
				w.Write(ans)
				w.WriteByte('\n')
			}
			if ferr := w.Flush(); ferr != nil {
				return ferr
			}
		}
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
	}
}

var errTooLong = errors.New("message too long")

func readLine(rd *bufio.Reader) ([]byte, error) {
	var buf []byte
	for {
		chunk, err := rd.ReadSlice('\n')
		if len(buf)+len(chunk) > MaxMessage+1 {
			// Skip the rest of this line, then report it.
			for errors.Is(err, bufio.ErrBufferFull) {
				_, err = rd.ReadSlice('\n')
			}
			return []byte(`{"jsonrpc":"2.0","method":"__too_long__"}`), err
		}
		buf = append(buf, chunk...)
		if errors.Is(err, bufio.ErrBufferFull) {
			continue
		}
		return buf, err
	}
}

func rpcError(id json.RawMessage, code int, msg string) []byte {
	if len(id) == 0 {
		id = json.RawMessage("null")
	}
	b, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": id, "error": map[string]any{"code": code, "message": msg}})
	return b
}

func (b *Bridge) log(format string, args ...any) {
	if b.cfg.Log != nil {
		b.cfg.Log(format, args...)
	}
}

// Send forwards one message and returns the lines to write (none for a notification).
func (b *Bridge) Send(ctx context.Context, msg []byte) [][]byte {
	var env envelope
	if err := json.Unmarshal(msg, &env); err != nil {
		return [][]byte{rpcError(nil, -32700, "parse error: not a JSON object")}
	}
	if env.Method == "__too_long__" {
		return [][]byte{rpcError(nil, -32600, fmt.Sprintf("message longer than %d bytes", MaxMessage))}
	}
	isRequest := env.Method != "" && len(env.ID) > 0
	start := time.Now()
	status, ctype, body, sid, err := b.post(ctx, msg)
	b.log("mcp %s id=%s status=%d %s", dash(env.Method), dash(string(env.ID)), status, time.Since(start).Round(time.Millisecond))
	if err != nil {
		b.log("mcp: cannot reach the hub (%v); run `onemind mcp doctor`", redactURL(err))
		if isRequest {
			return [][]byte{rpcError(env.ID, -32000, "OneMind hub unreachable; run `onemind mcp doctor`")}
		}
		return nil
	}
	if sid != "" {
		b.sessionID = sid
	}
	switch {
	case status == http.StatusAccepted:
		return nil
	case status == http.StatusUnauthorized || status == http.StatusForbidden:
		hint := "agent token revoked, wrong, or not an agent token, or agents are paused; run `onemind mcp doctor`"
		b.log("mcp: HTTP %d: %s", status, hint)
		if isRequest {
			return [][]byte{rpcError(env.ID, -32001, fmt.Sprintf("OneMind refused the agent (HTTP %d): %s", status, hint))}
		}
		return nil
	case status == http.StatusTooManyRequests:
		if isRequest {
			return [][]byte{rpcError(env.ID, -32002, "rate limited by OneMind; slow down and retry later")}
		}
		return nil
	}
	if strings.HasPrefix(ctype, "text/event-stream") {
		return sseData(body)
	}
	if !json.Valid(body) {
		if isRequest {
			return [][]byte{rpcError(env.ID, -32603, fmt.Sprintf("hub answered HTTP %d without JSON", status))}
		}
		return nil
	}
	var compact bytes.Buffer
	_ = json.Compact(&compact, body)
	if env.Method == "initialize" && status == http.StatusOK {
		var r struct {
			Result struct {
				ProtocolVersion string `json:"protocolVersion"`
			} `json:"result"`
		}
		if json.Unmarshal(body, &r) == nil {
			b.version = r.Result.ProtocolVersion
		}
	}
	return [][]byte{compact.Bytes()}
}

func (b *Bridge) post(ctx context.Context, msg []byte) (int, string, []byte, string, error) {
	pctx, cancel := context.WithTimeout(ctx, b.cfg.Timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(pctx, http.MethodPost, b.cfg.Hub+"/mcp", bytes.NewReader(msg))
	if err != nil {
		return 0, "", nil, "", err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	if b.cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+b.cfg.Token)
	}
	if b.version != "" {
		req.Header.Set("MCP-Protocol-Version", b.version)
	}
	if b.sessionID != "" {
		req.Header.Set("Mcp-Session-Id", b.sessionID)
	}
	resp, err := b.cfg.HTTP.Do(req)
	if err != nil {
		return 0, "", nil, "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	return resp.StatusCode, resp.Header.Get("Content-Type"), body, resp.Header.Get("Mcp-Session-Id"), err
}

// sseData returns each `data:` payload of an SSE body as one line.
func sseData(body []byte) [][]byte {
	var out [][]byte
	var data []string
	flush := func() {
		if len(data) > 0 {
			var c bytes.Buffer
			joined := []byte(strings.Join(data, "\n"))
			if json.Compact(&c, joined) == nil {
				out = append(out, c.Bytes())
			}
			data = nil
		}
	}
	for _, line := range strings.Split(strings.ReplaceAll(string(body), "\r\n", "\n"), "\n") {
		if line == "" {
			flush()
			continue
		}
		if v, ok := strings.CutPrefix(line, "data:"); ok {
			data = append(data, strings.TrimPrefix(v, " "))
		}
	}
	flush()
	return out
}

func dash(s string) string {
	if s == "" {
		return "-"
	}
	return s
}

// redactURL keeps network errors short; they never contain the token (it is a header).
func redactURL(err error) string {
	s := err.Error()
	if i := strings.LastIndex(s, ": "); i >= 0 {
		return s[i+2:]
	}
	return s
}
