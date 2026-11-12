// SPDX-License-Identifier: Apache-2.0

// Package fabric is the node side of the owner-approved join (contract
// §12.11; docs/leap/core/FABRIC.md §3.1; docs/architecture/NETWORKING.md §5.1):
// `onemind fabric join` on a new machine.
//
// The machine makes its own key, CSR and NATS nkey (no private key ever
// leaves it), asks the hub with the one-time join code, shows the short match
// code the owner compares on the approval card, and waits. After approval it
// collects its credentials once, proving with a signature that it holds the
// key in the CSR, then writes its identity, joins the mesh (mesh.Enroll),
// starts its NATS leaf and, on a worker, prepares the k3s agent to join over
// the mesh.
//
// The hub is reached over HTTPS pinned to the box CA fingerprint from the QR,
// so a machine on the LAN cannot pose as the hub.
package fabric

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/nats-io/nkeys"
)

// PollContext prefixes the string a node signs to prove it holds its key
// (core/onemind_core/fabric.py POLL_CONTEXT).
const PollContext = "onemind-join-poll:v1:"

// Ticket is what the owner's QR or the typed code carries.
type Ticket struct {
	Code  string // the one-time join code
	CASHA string // sha256 of the box CA certificate (DER), lower-case hex
	Role  string // worker | leaf
	Hub   string // https URL of the hub gateway
}

var (
	shaRe  = regexp.MustCompile(`^[0-9a-f]{64}$`)
	codeRe = regexp.MustCompile(`^[0-9A-Za-z]{4}-?[0-9A-Za-z]{4}-?[0-9A-Za-z]{4}$`)
)

// ParseQR reads `onemind-join:v1?code=…&ca=…&role=…[&hub=…]`.
func ParseQR(payload string) (*Ticket, error) {
	const prefix = "onemind-join:v1?"
	if !strings.HasPrefix(payload, prefix) {
		return nil, errors.New("not a OneMind join code (expected onemind-join:v1?…)")
	}
	q, err := url.ParseQuery(strings.TrimPrefix(payload, prefix))
	if err != nil {
		return nil, fmt.Errorf("join code: %w", err)
	}
	t := &Ticket{Code: q.Get("code"), CASHA: strings.ToLower(q.Get("ca")), Role: q.Get("role"), Hub: q.Get("hub")}
	return t, t.Validate()
}

// Validate checks every field before anything touches the network.
func (t *Ticket) Validate() error {
	if !codeRe.MatchString(t.Code) {
		return errors.New("join code must look like 7KQ4-M2XP-9D3F")
	}
	if !shaRe.MatchString(t.CASHA) {
		return errors.New("the box CA fingerprint must be 64 hex characters")
	}
	if t.Role != "" && t.Role != "worker" && t.Role != "leaf" {
		return fmt.Errorf("role must be worker or leaf, got %q", t.Role)
	}
	u, err := url.Parse(t.Hub)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || (u.Path != "" && u.Path != "/") {
		return fmt.Errorf("hub must be an https URL such as https://box.local, got %q", t.Hub)
	}
	return nil
}

// Identity is what the node generates locally.
type Identity struct {
	Key       *ecdsa.PrivateKey
	CSRPEM    []byte
	NkeySeed  []byte
	NkeyPub   string
	KeyPEM    []byte
	NodeID    string
	Hostname  string
	PublicDER []byte
}

// NewIdentity makes the node key, CSR and NATS user nkey.
func NewIdentity(nodeID, hostname string) (*Identity, error) {
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return nil, err
	}
	csr, err := x509.CreateCertificateRequest(rand.Reader, &x509.CertificateRequest{
		Subject: pkix.Name{CommonName: "node-" + nodeID},
	}, key)
	if err != nil {
		return nil, err
	}
	kder, err := x509.MarshalECPrivateKey(key)
	if err != nil {
		return nil, err
	}
	kp, err := nkeys.CreateUser()
	if err != nil {
		return nil, err
	}
	seed, _ := kp.Seed()
	pub, _ := kp.PublicKey()
	pubDER, _ := x509.MarshalPKIXPublicKey(&key.PublicKey)
	return &Identity{
		Key: key, CSRPEM: pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE REQUEST", Bytes: csr}),
		KeyPEM: pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: kder}),
		NkeySeed: seed, NkeyPub: pub, NodeID: nodeID, Hostname: hostname, PublicDER: pubDER,
	}, nil
}

// Proof signs the poll context for request id with the node key (base64 DER).
func (id *Identity) Proof(requestID string) (string, error) {
	h := sha256.Sum256([]byte(PollContext + requestID))
	sig, err := ecdsa.SignASN1(rand.Reader, id.Key, h[:])
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(sig), nil
}

// PinnedClient talks HTTPS to the hub and accepts only a chain that contains
// the CA whose sha256 is pin and whose leaf is valid for the hub's name.
// hubAddr (optional) dials that IP instead of resolving the hub's name
// (like curl --resolve; for LANs where mDNS does not work).
func PinnedClient(pin, hubHost, hubAddr string, timeout time.Duration) (*http.Client, *CAHolder) {
	holder := &CAHolder{}
	tc := &tls.Config{
		MinVersion:         tls.VersionTLS12,
		InsecureSkipVerify: true, // replaced by VerifyConnection below: pin, then normal verification
		VerifyConnection: func(cs tls.ConnectionState) error {
			var ca *x509.Certificate
			for _, c := range cs.PeerCertificates {
				sum := sha256.Sum256(c.Raw)
				if hex.EncodeToString(sum[:]) == pin && c.IsCA {
					ca = c
				}
			}
			if ca == nil || len(cs.PeerCertificates) == 0 {
				return errors.New("the hub did not present the box CA from the join code (wrong hub, or someone in between)")
			}
			pool := x509.NewCertPool()
			pool.AddCert(ca)
			if _, err := cs.PeerCertificates[0].Verify(x509.VerifyOptions{Roots: pool, DNSName: hubHost}); err != nil {
				return fmt.Errorf("hub certificate: %w", err)
			}
			holder.CA = ca
			return nil
		},
	}
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	tr := &http.Transport{TLSClientConfig: tc, Proxy: nil, DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
		if hubAddr != "" {
			_, port, _ := net.SplitHostPort(addr)
			addr = net.JoinHostPort(hubAddr, port)
		}
		return dialer.DialContext(ctx, network, addr)
	}}
	return &http.Client{Transport: tr, Timeout: timeout}, holder
}

// CAHolder receives the pinned CA certificate seen in the handshake.
type CAHolder struct{ CA *x509.Certificate }

// PEM is the CA as PEM.
func (h *CAHolder) PEM() []byte {
	if h.CA == nil {
		return nil
	}
	return pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: h.CA.Raw})
}

// NodeFacts is what the approval card shows (no serials, MAC or IP addresses).
type NodeFacts struct {
	NodeID   string            `json:"node_id"`
	Hostname string            `json:"hostname"`
	Board    string            `json:"board"`
	Arch     string            `json:"arch"`
	OS       map[string]string `json:"os"`
}

// Accepted is the hub's answer to the join request.
type Accepted struct {
	RequestID string `json:"join_request_id"`
	MatchCode string `json:"match_code"`
	Role      string `json:"role"`
	Poll      string `json:"poll"`
}

// Credentials are delivered once after approval (§12.11).
type Credentials struct {
	Role     string `json:"role"`
	NodeCert string `json:"node_cert"`
	CACert   string `json:"ca_cert"`
	NATS     struct {
		URL        string `json:"url"`
		Account    string `json:"account"`
		UserPubkey string `json:"user_pubkey"`
	} `json:"nats"`
	Mesh *MeshBlock `json:"mesh,omitempty"`
	K3s  *struct {
		ServerURL string `json:"server_url"`
		Token     string `json:"token"`
	} `json:"k3s,omitempty"`
}

// MeshBlock mirrors mesh.Bundle (kept here to decode extra fields such as tags).
type MeshBlock struct {
	ControlURL   string   `json:"control_url"`
	ControlAddrs []string `json:"control_addrs"`
	CASHA256     string   `json:"ca_sha256"`
	AuthKey      string   `json:"auth_key"`
	Hostname     string   `json:"hostname"`
	HubMeshIP    string   `json:"hub_mesh_ip"`
	Tags         []string `json:"tags"`
	ShieldsUp    bool     `json:"shields_up"`
}

// PollResult is one poll answer.
type PollResult struct {
	State       string       `json:"state"`
	MatchCode   string       `json:"match_code"`
	Credentials *Credentials `json:"credentials"`
}

// APIError is the gateway's error body.
type APIError struct {
	Status  int
	Code    string `json:"error"`
	Message string `json:"message"`
	Reason  string `json:"reason"`
}

func (e *APIError) Error() string {
	s := fmt.Sprintf("hub answered %d %s: %s", e.Status, e.Code, e.Message)
	if e.Reason != "" {
		s += " (" + e.Reason + ")"
	}
	return s
}

// Client speaks the join routes.
type Client struct {
	HTTP *http.Client
	Hub  string // base URL, no trailing slash
}

func (c *Client) do(ctx context.Context, method, path string, body any, headers map[string]string, out any) error {
	var rd io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return err
		}
		rd = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.Hub+path, rd)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("OneMind-API-Version", "1")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode >= 300 {
		e := &APIError{Status: resp.StatusCode}
		_ = json.Unmarshal(raw, e)
		return e
	}
	return json.Unmarshal(raw, out)
}

// Request files the join request.
func (c *Client) Request(ctx context.Context, code string, id *Identity, facts NodeFacts) (*Accepted, error) {
	var a Accepted
	err := c.do(ctx, http.MethodPost, "/v1/fabric/join-requests", map[string]any{
		"join_code": code, "node": facts, "csr_pem": string(id.CSRPEM), "nats_pubkey": id.NkeyPub,
	}, nil, &a)
	if err != nil {
		return nil, err
	}
	if a.RequestID == "" || !strings.HasPrefix(a.Poll, "/v1/fabric/join-requests/") {
		return nil, errors.New("hub sent an unexpected join answer")
	}
	return &a, nil
}

// Poll asks once.
func (c *Client) Poll(ctx context.Context, code string, id *Identity, requestID string) (*PollResult, error) {
	proof, err := id.Proof(requestID)
	if err != nil {
		return nil, err
	}
	var r PollResult
	err = c.do(ctx, http.MethodGet, "/v1/fabric/join-requests/"+url.PathEscape(requestID), nil,
		map[string]string{"OneMind-Join-Code": code, "OneMind-Join-Proof": proof}, &r)
	return &r, err
}

// Wait polls until the credentials arrive, the owner denies, or ctx ends.
// Transient errors (hub restarting, 503 while the mesh coordinator is busy)
// are retried.
func (c *Client) Wait(ctx context.Context, code string, id *Identity, requestID string, every time.Duration) (*Credentials, error) {
	if every <= 0 {
		every = 3 * time.Second
	}
	for {
		r, err := c.Poll(ctx, code, id, requestID)
		var ae *APIError
		switch {
		case err == nil && r.Credentials != nil:
			return r.Credentials, nil
		case err == nil && r.State == "delivered":
			return nil, errors.New("the credentials were already collected (by another run of this command?)")
		case err == nil && (r.State == "denied" || r.State == "expired" || r.State == "failed"):
			return nil, fmt.Errorf("join %s", r.State)
		case errors.As(err, &ae) && ae.Status != http.StatusServiceUnavailable && ae.Status != http.StatusTooManyRequests:
			return nil, err
		}
		select {
		case <-ctx.Done():
			return nil, fmt.Errorf("waiting for approval: %w", ctx.Err())
		case <-time.After(every):
		}
	}
}

// Check verifies the delivered credentials belong to this node and this box.
func (cr *Credentials) Check(id *Identity, pin string) (*x509.Certificate, error) {
	caBlock, _ := pem.Decode([]byte(cr.CACert))
	certBlock, _ := pem.Decode([]byte(cr.NodeCert))
	if caBlock == nil || certBlock == nil {
		return nil, errors.New("credentials: certificate missing")
	}
	sum := sha256.Sum256(caBlock.Bytes)
	if hex.EncodeToString(sum[:]) != pin {
		return nil, errors.New("credentials: CA is not the pinned box CA")
	}
	ca, err := x509.ParseCertificate(caBlock.Bytes)
	if err != nil {
		return nil, err
	}
	cert, err := x509.ParseCertificate(certBlock.Bytes)
	if err != nil {
		return nil, err
	}
	if !cert.PublicKey.(*ecdsa.PublicKey).Equal(&id.Key.PublicKey) {
		return nil, errors.New("credentials: the certificate is not for this node's key")
	}
	pool := x509.NewCertPool()
	pool.AddCert(ca)
	if _, err := cert.Verify(x509.VerifyOptions{Roots: pool, KeyUsages: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}}); err != nil {
		return nil, fmt.Errorf("credentials: node certificate: %w", err)
	}
	if cr.NATS.UserPubkey != id.NkeyPub {
		return nil, errors.New("credentials: NATS account is for another key")
	}
	return cert, nil
}
