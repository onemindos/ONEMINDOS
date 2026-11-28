// SPDX-License-Identifier: Apache-2.0

// Package onemind is the Go client for the OneMind gateway API (sdk/openapi/onemind-v1.json).
//
// Types are generated from the OpenAPI document (internal/gen); the transport is hand-written so
// that retries, idempotency keys, approval read-back and the event stream behave the same in the
// Go, TypeScript and Python SDKs (docs/leap/dev/SDK.md). The standard library only.
//
//	c, err := onemind.FromEnv()           // ONEMIND_HUB + ONEMIND_TOKEN, or the §11.2 agent Secret
//	nodes, err := c.Nodes.List(ctx)
//	a, err := c.Actions.Request(ctx, onemind.ActionRequest{Type: onemind.ActionAppInstall, AppID: "ntfy"})
package onemind

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/rand/v2"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Version of this SDK.
const Version = "0.1.0"

const (
	defaultTimeout = 10 * time.Second
	maxBody        = 32 << 20
	retryBase      = 250 * time.Millisecond
	retryCap       = 4 * time.Second
)

// TokenProvider supplies the bearer token. Refresh is called once after a 401; returning true
// makes the client retry that request one time (later identity work: short-lived sessions).
type TokenProvider interface {
	Token(ctx context.Context) (string, error)
	Refresh(ctx context.Context) (bool, error)
}

type staticToken string

func (t staticToken) Token(context.Context) (string, error) { return string(t), nil }
func (staticToken) Refresh(context.Context) (bool, error)   { return false, nil }

// StaticToken is a TokenProvider for a fixed token.
func StaticToken(token string) TokenProvider { return staticToken(token) }

// Client talks to one gateway. It is safe for concurrent use.
type Client struct {
	base      *url.URL
	tokens    TokenProvider
	http      *http.Client
	timeout   time.Duration
	attempts  int
	principal string
	userAgent string
	trace     func(method, path string, status int, d time.Duration)
	warn      func(string)
	warnOnce  sync.Once
	sleep     func(context.Context, time.Duration) error
	offset    atomic.Int64 // hub clock minus local clock, from the Date header (ns)
	expiries  expiryMemo   // expires_at fixed per idempotency key

	Instance *InstanceService
	About    *AboutService
	Nodes    *NodesService
	Apps     *AppsService
	Actions  *ActionsService
	Work     *WorkService
	Audit    *AuditService
	Events   *EventsService
	Status   *StatusService
	Services *ServicesService
	Domains  *DomainsService
	Keyboard *KeyboardService
	Network  *NetworkService
}

// Option configures a Client.
type Option func(*Client)

// WithToken sets a static bearer token.
func WithToken(token string) Option { return func(c *Client) { c.tokens = StaticToken(token) } }

// WithTokenProvider sets a TokenProvider.
func WithTokenProvider(p TokenProvider) Option { return func(c *Client) { c.tokens = p } }

// WithHTTPClient replaces the HTTP client (custom TLS roots, a pinned CA, a test server).
func WithHTTPClient(h *http.Client) Option { return func(c *Client) { c.http = h } }

// WithNoRedirects keeps credentials and request bodies on the selected gateway.
func WithNoRedirects() Option {
	return func(c *Client) { c.http = withoutRedirects(c.http) }
}

func withoutRedirects(client *http.Client) *http.Client {
	h := *client
	h.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	return &h
}

// WithGatewayCA makes the client verify the gateway's TLS certificate against the given CA
// (PEM text) instead of the system roots, with TLS 1.2 or later. Verification stays on: this
// narrows what is trusted to that CA. It is what FromEnv uses for ONEMIND_GATEWAY_CA (the box CA
// an agent app's Secret carries). A later WithHTTPClient replaces it.
func WithGatewayCA(pem []byte) (Option, error) {
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(pem) {
		return nil, errors.New("onemind: the gateway CA is not a valid PEM certificate")
	}
	tr := http.DefaultTransport.(*http.Transport).Clone()
	tr.TLSClientConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
	return func(c *Client) { c.http = &http.Client{Transport: tr} }, nil
}

// WithTimeout sets the per-attempt timeout (default 10 s). A context deadline still applies.
func WithTimeout(d time.Duration) Option { return func(c *Client) { c.timeout = d } }

// WithRetries sets how many attempts a retryable call gets (default 3; 1 disables retries).
func WithRetries(n int) Option {
	return func(c *Client) {
		if n >= 1 {
			c.attempts = n
		}
	}
}

// WithPrincipal names the caller's principal id, so an approve whose reply was lost can be
// confirmed by reading the action back (decided_by must be this id).
func WithPrincipal(id string) Option { return func(c *Client) { c.principal = id } }

// WithTrace calls fn after each HTTP attempt with the method, path, status (0 on a network
// error) and duration. It never receives headers or bodies, so it cannot leak the token.
func WithTrace(fn func(method, path string, status int, d time.Duration)) Option {
	return func(c *Client) { c.trace = fn }
}

// WithWarn receives one-time warnings (plain http to a non-local hub). Default: stderr.
func WithWarn(fn func(string)) Option { return func(c *Client) { c.warn = fn } }

// WithUserAgent sets the User-Agent prefix (the CLI passes "onemind-cli/<version>").
func WithUserAgent(ua string) Option { return func(c *Client) { c.userAgent = ua } }

// New returns a client for the gateway at baseURL (absolute http or https URL).
func New(baseURL string, opts ...Option) (*Client, error) {
	u, err := url.Parse(strings.TrimRight(strings.TrimSpace(baseURL), "/"))
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return nil, fmt.Errorf("onemind: hub URL must be an absolute http(s) URL, got %q", baseURL)
	}
	c := &Client{
		base: u, tokens: StaticToken(""), http: &http.Client{}, timeout: defaultTimeout, attempts: 3,
		userAgent: "onemind-sdk-go/" + Version,
		warn:      func(s string) { fmt.Fprintln(os.Stderr, "onemind: warning:", s) },
		sleep: func(ctx context.Context, d time.Duration) error {
			t := time.NewTimer(d)
			defer t.Stop()
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-t.C:
				return nil
			}
		},
	}
	for _, o := range opts {
		o(c)
	}
	c.Instance = &InstanceService{c}
	c.About = &AboutService{c}
	c.Nodes = &NodesService{c}
	c.Apps = &AppsService{c}
	c.Actions = &ActionsService{c}
	c.Work = &WorkService{c}
	c.Audit = &AuditService{c}
	c.Events = &EventsService{c}
	c.Status = &StatusService{c}
	c.Services = &ServicesService{c}
	c.Domains = &DomainsService{c}
	c.Keyboard = &KeyboardService{c}
	c.Network = &NetworkService{c}
	return c, nil
}

// FromEnv builds a client from ONEMIND_HUB and ONEMIND_TOKEN (the CLI's names), else from
// ONEMIND_GATEWAY_URL and ONEMIND_AGENT_TOKEN (the Secret an agent app gets, contract §11.2). When
// ONEMIND_GATEWAY_CA (PEM text) is set, the client trusts that CA for the gateway (see WithGatewayCA).
func FromEnv(opts ...Option) (*Client, error) {
	hub, token := os.Getenv("ONEMIND_HUB"), os.Getenv("ONEMIND_TOKEN")
	if hub == "" {
		hub, token = os.Getenv("ONEMIND_GATEWAY_URL"), os.Getenv("ONEMIND_AGENT_TOKEN")
	}
	if hub == "" {
		return nil, errors.New("onemind: set ONEMIND_HUB (and ONEMIND_TOKEN) or ONEMIND_GATEWAY_URL")
	}
	base := []Option{WithToken(token)}
	if ca := strings.TrimSpace(os.Getenv("ONEMIND_GATEWAY_CA")); ca != "" { // the box CA (hardening H-05)
		o, err := WithGatewayCA([]byte(ca))
		if err != nil {
			return nil, err
		}
		base = append(base, o)
	}
	return New(hub, append(base, opts...)...)
}

// HubNow is the hub's clock as last seen in a Date header (local time before the first call).
func (c *Client) HubNow() time.Time { return time.Now().Add(time.Duration(c.offset.Load())) }

// BaseURL is the hub URL without a trailing slash.
func (c *Client) BaseURL() string { return c.base.String() }

// String never includes the token.
func (c *Client) String() string {
	p := c.principal
	if p == "" {
		p = "?"
	}
	return fmt.Sprintf("OneMind(hub=%s, principal=%s)", c.base, p)
}

func (c *Client) checkTransport() {
	if c.base.Scheme != "http" {
		return
	}
	h := c.base.Hostname()
	if h == "localhost" || net.ParseIP(h).IsLoopback() {
		return
	}
	c.warnOnce.Do(func() {
		if c.warn != nil {
			c.warn("talking to " + c.base.Host + " over plain http: the token crosses the network unencrypted")
		}
	})
}

// request is one logical API call.
type request struct {
	method      string
	path        string // with query string
	body        any
	retry       bool // safe to retry (GET, or POST with an idempotency key)
	oneTime     bool // consuming the response makes a replay unsafe
	headers     map[string]string
	noRedirects bool
}

// Do performs one API call and decodes a 2xx JSON body into out (which may be nil, *any or
// *json.RawMessage to keep the gateway's bytes). It is how the CLI's --json passes bodies through.
func (c *Client) Do(ctx context.Context, method, path string, body, out any) error {
	_, err := c.do(ctx, request{method: method, path: path, body: body, retry: method == http.MethodGet}, out)
	return err
}

// DoWithStepUp sends a write with a single-use proof bound to this operation.
func (c *Client) DoWithStepUp(ctx context.Context, method, path, grant string, body, out any) error {
	_, err := c.do(ctx, request{method: method, path: path, body: body,
		headers: map[string]string{"OneMind-Step-Up": grant}, noRedirects: true}, out)
	return err
}

// DoIdempotent is Do for a call that changes something (POST, PUT, DELETE) and carries an Idempotency-Key
// header. The gateway answers a repeat with the same key with the first result instead of acting twice, so the
// call is retried on a dropped connection or a 503 like a GET. Use it where the key cannot go in the body, such
// as a DELETE.
func (c *Client) DoIdempotent(ctx context.Context, method, path, key string, body, out any) error {
	if key == "" {
		return errors.New("onemind: DoIdempotent needs an idempotency key")
	}
	_, err := c.do(ctx, request{method: method, path: path, body: body, retry: true, headers: map[string]string{"Idempotency-Key": key}}, out)
	return err
}

// DoWithHeaders is Do that also sends extra request headers (If-Match, Idempotency-Key, ...) and returns
// the response headers (ETag, Link, ...), so a caller can do a read-change-write with If-Match or follow
// a Link rel="next" page. A GET is retried like Do's; a write is retried only when headers carries an
// Idempotency-Key. On an error the headers are those of the last answer (nil if none came).
func (c *Client) DoWithHeaders(ctx context.Context, method, path string, headers map[string]string, body, out any) (http.Header, error) {
	_, keyed := headers["Idempotency-Key"]
	return c.do(ctx, request{method: method, path: path, body: body, retry: method == http.MethodGet || keyed, headers: headers}, out)
}

// DoOnceWithHeaders sends a request whose response may consume one-time material.
func (c *Client) DoOnceWithHeaders(ctx context.Context, method, path string, headers map[string]string, body, out any) error {
	_, err := c.do(ctx, request{method: method, path: path, body: body, oneTime: true, headers: headers}, out)
	return err
}

func (c *Client) do(ctx context.Context, r request, out any) (http.Header, error) {
	c.checkTransport()
	var payload []byte
	if r.body != nil {
		var err error
		if payload, err = json.Marshal(r.body); err != nil {
			return nil, err
		}
	}
	attempts := 1
	if r.retry {
		attempts = c.attempts
	}
	refreshed := false
	var last error
	for i := 0; i < attempts; i++ {
		if i > 0 {
			wait := backoff(i)
			var e *Error
			if errors.As(last, &e) && e.RetryAfter > 0 {
				wait = e.RetryAfter
			}
			if err := c.sleep(ctx, wait); err != nil {
				return nil, last
			}
		}
		hdr, status, err := c.once(ctx, r, payload, out)
		if err == nil {
			return hdr, nil
		}
		last = err
		if status == http.StatusUnauthorized && !refreshed && !r.oneTime {
			refreshed = true
			if ok, _ := c.tokens.Refresh(ctx); ok {
				i--
				continue
			}
		}
		if !retryable(status, err) || ctx.Err() != nil {
			return hdr, err
		}
	}
	return nil, last
}

func retryable(status int, err error) bool {
	switch status {
	case 0:
		return errors.Is(err, ErrNetwork)
	case http.StatusTooManyRequests, http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return true
	}
	return false
}

func backoff(attempt int) time.Duration {
	ceil := retryBase << (attempt - 1)
	if ceil > retryCap || ceil <= 0 {
		ceil = retryCap
	}
	return time.Duration(rand.Int64N(int64(ceil)) + 1) // full jitter
}

func (c *Client) once(ctx context.Context, r request, payload []byte, out any) (http.Header, int, error) {
	actx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	var body io.Reader
	if payload != nil {
		body = bytes.NewReader(payload)
	}
	req, err := http.NewRequestWithContext(actx, r.method, c.base.String()+r.path, body)
	if err != nil {
		return nil, 0, err
	}
	if r.oneTime {
		// The standard transport treats an Idempotency-Key as permission to replay a rewindable body.
		req.GetBody = nil
	}
	token, err := c.tokens.Token(ctx)
	if err != nil {
		return nil, 0, err
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.userAgent)
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	for k, v := range r.headers {
		req.Header.Set(k, v)
	}
	start := time.Now()
	client := c.http
	if r.noRedirects {
		client = withoutRedirects(client)
	}
	resp, err := client.Do(req)
	if err != nil {
		c.traceCall(r, 0, start)
		return nil, 0, &Error{Code: "network", Message: redact(err.Error(), token), cause: ErrNetwork}
	}
	defer resp.Body.Close()
	c.traceCall(r, resp.StatusCode, start)
	if d, err := http.ParseTime(resp.Header.Get("Date")); err == nil {
		c.offset.Store(int64(time.Until(d)))
	}
	raw, err := io.ReadAll(io.LimitReader(resp.Body, maxBody))
	if err != nil {
		return resp.Header, 0, &Error{Code: "network", Message: "reading the response: " + redact(err.Error(), token), cause: ErrNetwork}
	}
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		return resp.Header, resp.StatusCode, apiError(resp, raw)
	}
	if out != nil && resp.StatusCode != http.StatusNoContent {
		if err := json.Unmarshal(raw, out); err != nil {
			return resp.Header, resp.StatusCode, &Error{Status: resp.StatusCode, Code: "unexpected_response",
				Message: "the hub did not answer with the expected JSON (a proxy in the way?)"}
		}
	}
	return resp.Header, resp.StatusCode, nil
}

func (c *Client) traceCall(r request, status int, start time.Time) {
	if c.trace != nil {
		path, _, _ := strings.Cut(r.path, "?")
		c.trace(r.method, path, status, time.Since(start))
	}
}

func redact(s, token string) string {
	if token != "" {
		s = strings.ReplaceAll(s, token, "[redacted]")
	}
	return s
}

func apiError(resp *http.Response, raw []byte) error {
	var body struct {
		Error      string   `json:"error"`
		Message    string   `json:"message"`
		Reason     string   `json:"reason"`
		RetryAfter *float64 `json:"retry_after_s"`
	}
	e := &Error{Status: resp.StatusCode}
	if json.Unmarshal(raw, &body) == nil && body.Error != "" {
		e.Code, e.Message, e.Reason = body.Error, body.Message, body.Reason
	} else {
		e.Code, e.Message = "unexpected_response", fmt.Sprintf("HTTP %d without the OneMind error body", resp.StatusCode)
		if resp.StatusCode == http.StatusNotFound {
			e.Code = "not_found"
		}
	}
	if s := resp.Header.Get("Retry-After"); s != "" {
		if n, err := strconv.Atoi(s); err == nil {
			e.RetryAfter = time.Duration(n) * time.Second
		}
	} else if body.RetryAfter != nil {
		e.RetryAfter = time.Duration(*body.RetryAfter * float64(time.Second))
	}
	return e
}

// ---- simple resources ------------------------------------------------------------------------

// Healthz is GET /healthz (no token needed).
func (c *Client) Healthz(ctx context.Context) (bool, error) {
	var v struct {
		OK bool `json:"ok"`
	}
	err := c.Do(ctx, http.MethodGet, "/healthz", nil, &v)
	return v.OK, err
}

// InstanceService is GET /v1/instance.
type InstanceService struct{ c *Client }

// Get is operation instance.get.
func (s *InstanceService) Get(ctx context.Context) (*Instance, error) {
	var v Instance
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/instance", nil, &v)
}

// AboutService is GET /v1/os/about (About this box).
type AboutService struct{ c *Client }

// Get is operation os.about: the device facts of every node the hub knows, never a serial or an address.
func (s *AboutService) Get(ctx context.Context) (*About, error) {
	var v About
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/os/about", nil, &v)
}

// StatusService is GET /v1/status (FD-01): what needs attention, per source.
type StatusService struct{ c *Client }

// Get is operation status.get. A source the gateway could not read is "unknown", never "ok".
func (s *StatusService) Get(ctx context.Context) (*StatusView, error) {
	var v StatusView
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/status", nil, &v)
}

// ServicesService is GET /v1/system/services (#623): the service cards, owner only.
type ServicesService struct{ c *Client }

// List is operation system.services.list: every systemd unit the OS ships with its plain name, risk and
// systemd state. A unit the image's registry does not list has Known false. Read only.
func (s *ServicesService) List(ctx context.Context) (*ServicesView, error) {
	var v ServicesView
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/system/services", nil, &v)
}

// NetworkService is /v1/network: this box's network facts, owner only.
type NetworkService struct{ c *Client }

// Firewall is operation network.firewall (GET /v1/network/firewall, P-09 part 1): the live firewall checked
// and explained in plain words, read only. Available is false, with a reason, when the host service cannot
// be reached; an unknown firewall is never reported as safe.
func (s *NetworkService) Firewall(ctx context.Context) (*FirewallView, error) {
	var v FirewallView
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/network/firewall", nil, &v)
}

// Allow is operation network.firewall.allow (POST /v1/network/firewall/allow, P-09 part 2): it files a
// firewall.allow action for one port from the home network ("lan") or the mesh ("mesh"). It only asks: an owner
// approves it with a passkey, and the rule then stays pending until it is confirmed. Retried calls carry one
// idempotency key so a retry never files twice.
func (s *NetworkService) Allow(ctx context.Context, proto string, port int, scope, reason string) (*Action, error) {
	body := map[string]any{"proto": proto, "port": port, "scope": scope, "idempotency_key": "sdk-" + strconv.FormatInt(time.Now().UnixNano(), 36)}
	if reason != "" {
		body["reason"] = reason
	}
	var v Action
	return &v, s.c.Do(ctx, http.MethodPost, "/v1/network/firewall/allow", body, &v)
}

// ConfirmAllow is operation network.firewall.allow.confirm: keep a pending rule (owner only).
func (s *NetworkService) ConfirmAllow(ctx context.Context, id string) error {
	return s.c.Do(ctx, http.MethodPost, "/v1/network/firewall/allow/"+url.PathEscape(id)+"/confirm", nil, nil)
}

// RemoveAllow is operation network.firewall.allow.remove: take a rule away, pending or confirmed (owner only).
func (s *NetworkService) RemoveAllow(ctx context.Context, id string) error {
	return s.c.Do(ctx, http.MethodDelete, "/v1/network/firewall/allow/"+url.PathEscape(id), nil, nil)
}

// NodesService is /v1/nodes.
type NodesService struct{ c *Client }

// List is operation nodes.list.
func (s *NodesService) List(ctx context.Context) ([]Node, error) {
	var v []Node
	return v, s.c.Do(ctx, http.MethodGet, "/v1/nodes", nil, &v)
}

// Usage is operation monitoring.usage (GET /v1/usage): CPU, memory and disk per machine and per app.
func (s *NodesService) Usage(ctx context.Context) (*Usage, error) {
	var v Usage
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/usage", nil, &v)
}

// Get is operation nodes.get.
func (s *NodesService) Get(ctx context.Context, id string) (*Node, error) {
	var v Node
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/nodes/"+url.PathEscape(id), nil, &v)
}

// AppsService is /v1/apps.
type AppsService struct{ c *Client }

// List is operation apps.list.
func (s *AppsService) List(ctx context.Context) ([]CatalogApp, error) {
	var v []CatalogApp
	return v, s.c.Do(ctx, http.MethodGet, "/v1/apps", nil, &v)
}

// Get returns one catalog entry (from apps.list until GET /v1/apps/{id} exists).
// System is operation apps.system: the Built in area, every system app with its on/off switch, version,
// licence and update channel. A switched-off app is listed only here, not by List.
func (s *AppsService) System(ctx context.Context) ([]SystemApp, error) {
	var v []SystemApp
	return v, s.c.Do(ctx, http.MethodGet, "/v1/system-apps", nil, &v)
}

func (s *AppsService) Get(ctx context.Context, id string) (*CatalogApp, error) {
	apps, err := s.List(ctx)
	if err != nil {
		return nil, err
	}
	for i := range apps {
		if apps[i].Id == id {
			return &apps[i], nil
		}
	}
	return nil, &Error{Status: 404, Code: "not_found", Message: fmt.Sprintf("app %q is not in the catalog", id)}
}
