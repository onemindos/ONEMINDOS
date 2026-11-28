// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"time"
)

// The passkey step for the terminal (SEC-TERM-01, D-014). The passkeys live in the gateway
// (core/onemind_core/identity), so the console asks the gateway on this box, over loopback:
//
//	POST /v1/auth/rescue/options  makes a single-use challenge (120 s) for the owner's passkeys
//	POST /v1/auth/rescue/verify   checks the browser's assertion and audits it
//	POST /v1/auth/rescue/kit      checks the printed kit's owner key typed at the box (D-028: no passkey left)
//
// The console forwards the owner's own credential, so the gateway applies its owner check too. A fresh
// assertion is needed once, to start a session; it is never remembered between sessions.

// ErrReauthUnavailable means the gateway could not be asked (down, or answered with an error that is not a
// refusal). The terminal fails closed: a 503, no shell.
var ErrReauthUnavailable = errors.New("the passkey check is not available (is the gateway running?)")

// ErrNoPasskey means the gateway has no owner passkey registered, so there is nothing to step up with.
var ErrNoPasskey = errors.New("no owner passkey is registered on this box")

// Challenger is the optional second half of a Reauther: it makes the passkey challenge the page signs.
type Challenger interface {
	// Challenge returns the gateway's JSON answer (challenge_id, publicKey options) for the browser.
	Challenge(r *http.Request) ([]byte, error)
}

// GatewayReauth asks the gateway on loopback. Build it with NewGatewayReauth.
type GatewayReauth struct {
	base   string
	client *http.Client
}

// NewGatewayReauth refuses any address that is not loopback: it carries the owner's token, which must
// never leave the box.
func NewGatewayReauth(gatewayURL string, client *http.Client) (*GatewayReauth, error) {
	u, err := url.Parse(gatewayURL)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return nil, fmt.Errorf("gateway url %q is not an http(s) URL", gatewayURL)
	}
	h := u.Hostname()
	if ip := net.ParseIP(h); h != "localhost" && (ip == nil || !ip.IsLoopback()) {
		return nil, fmt.Errorf("gateway url %q is not loopback: the owner token would leave the box", gatewayURL)
	}
	if client == nil {
		client = &http.Client{Timeout: 10 * time.Second}
	}
	return &GatewayReauth{base: u.Scheme + "://" + u.Host, client: client}, nil
}

// call POSTs to the gateway as the caller. Host is the browser's, so the gateway derives the same
// WebAuthn relying party (rp id and origin) the passkey was registered for.
func (g *GatewayReauth) call(r *http.Request, path string, body []byte) (int, []byte, error) {
	req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, g.base+path, bytes.NewReader(body))
	if err != nil {
		return 0, nil, ErrReauthUnavailable
	}
	req.Host = r.Host
	req.Header.Set("Authorization", "Bearer "+presented(r))
	req.Header.Set("Content-Type", "application/json")
	resp, err := g.client.Do(req)
	if err != nil {
		return 0, nil, ErrReauthUnavailable
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	if err != nil {
		return 0, nil, ErrReauthUnavailable
	}
	return resp.StatusCode, b, nil
}

// Challenge implements Challenger.
func (g *GatewayReauth) Challenge(r *http.Request) ([]byte, error) {
	code, b, err := g.call(r, "/v1/auth/rescue/options", nil)
	switch {
	case err != nil:
		return nil, err
	case code == http.StatusOK:
		return b, nil
	case code == http.StatusConflict:
		return nil, ErrNoPasskey
	case code == http.StatusUnauthorized || code == http.StatusForbidden:
		return nil, ErrNoFreshAuth
	}
	return nil, ErrReauthUnavailable
}

// Fresh implements Reauther. The request body is {"webauthn": <assertion>} or, for an owner at the box with no
// passkey (D-028), {"kit_key": "<printed owner key>"}; the gateway must accept it. The kit key is taken only from a
// loopback client (a browser on the box, or an SSH tunnel to it): from the LAN the owner token alone never gets here.
func (g *GatewayReauth) Fresh(r *http.Request) (string, error) {
	in, err := io.ReadAll(http.MaxBytesReader(nil, r.Body, 16<<10))
	if err != nil {
		return "", ErrNoFreshAuth
	}
	var body struct {
		WebAuthn map[string]any `json:"webauthn"`
		KitKey   string         `json:"kit_key"`
	}
	if json.Unmarshal(in, &body) != nil {
		return "", ErrNoFreshAuth
	}
	var path string
	var out []byte
	switch {
	case len(body.WebAuthn) > 0 && body.KitKey == "":
		path = "/v1/auth/rescue/verify"
		out, _ = json.Marshal(map[string]any{"credential": body.WebAuthn})
	case body.KitKey != "" && len(body.WebAuthn) == 0:
		if !loopbackClient(r) {
			return "", ErrNoFreshAuth
		}
		path = "/v1/auth/rescue/kit"
		out, _ = json.Marshal(map[string]any{"kit_key": body.KitKey})
	default:
		return "", ErrNoFreshAuth
	}
	code, b, err := g.call(r, path, out)
	switch {
	case err != nil:
		return "", err
	case code == http.StatusOK:
		var v struct {
			CredentialID string `json:"credential_id"`
		}
		if json.Unmarshal(b, &v) != nil || v.CredentialID == "" {
			return "", ErrReauthUnavailable
		}
		return v.CredentialID, nil
	case code >= 400 && code < 500 && code != http.StatusTooManyRequests:
		return "", ErrNoFreshAuth
	}
	return "", ErrReauthUnavailable
}

// loopbackClient reports whether the request came from this box itself.
func loopbackClient(r *http.Request) bool {
	ip := net.ParseIP(clientIP(r))
	return ip != nil && ip.IsLoopback()
}
