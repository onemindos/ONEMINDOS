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
	"slices"
	"strconv"
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
	Role  string // worker | leaf (a machine ticket); empty for other kinds
	Hub   string // https URL of the hub gateway

	// From the QR (docs/architecture/FABRIC.md §4.2). Version is 1 or 2 (0 for a typed --code);
	// Kind is the v2 kind or the v1 role; Alt (away address) and MDNS exist only in v2.
	Version int
	Kind    string
	Alt     string
	MDNS    string
}

var (
	shaRe  = regexp.MustCompile(`^[0-9a-f]{64}$`)
	codeRe = regexp.MustCompile(`^[0-9A-Za-z]{4}-?[0-9A-Za-z]{4}-?[0-9A-Za-z]{4}$`)
)

// JoinQRMaxLen is the longest join QR any parser accepts.
const JoinQRMaxLen = 640

// JoinKinds are the v2 `kind` values; the first two are machines (`onemind fabric join`).
var JoinKinds = []string{"worker", "leaf", "phone", "desktop", "browser", "sensor"}

// JoinQRError is a refused join QR. Reason is the same word in Python, Go and TypeScript
// (sdk/testdata/join-qr/vectors.json "reasons").
type JoinQRError struct {
	Reason string
	Msg    string
}

func (e *JoinQRError) Error() string { return e.Msg }

var (
	qrPrefixRe   = regexp.MustCompile(`^onemind-join:v([0-9]+)\?`)
	qrKeyRe      = regexp.MustCompile(`^[a-z]+$`)
	qrValueRe    = regexp.MustCompile(`^[A-Za-z0-9._~%:/-]+$`)
	qrCodeV2Re   = regexp.MustCompile(`^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$`)
	qrHostPortRe = regexp.MustCompile(`^([A-Za-z0-9.-]{1,253})(?::([1-9][0-9]{0,4}))?$`)
	qrLabelRe    = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$`)
	qrDigitsRe   = regexp.MustCompile(`^[0-9]+$`)
	qrOctetRe    = regexp.MustCompile(`^(?:0|[1-9][0-9]{0,2})$`)
	qrMDNSRe     = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.local$`)
	qrFields     = map[int][]string{1: {"code", "ca", "role", "hub"}, 2: {"hub", "alt", "mdns", "ca", "code", "kind"}}
	qrRequired   = map[int][]string{1: {"code", "ca", "hub"}, 2: {"hub", "ca", "code", "kind"}}
)

func qrErr(reason, format string, a ...any) error {
	return &JoinQRError{Reason: reason, Msg: fmt.Sprintf(format, a...)}
}

// qrUnescape is strict percent-decoding: every '%' starts two hex digits and the result is
// printable ASCII (url.QueryUnescape would also turn '+' into a space).
func qrUnescape(v string) (string, bool) {
	var b strings.Builder
	for i := 0; i < len(v); i++ {
		c := v[i]
		if c == '%' {
			if i+2 >= len(v) {
				return "", false
			}
			n, err := hex.DecodeString(v[i+1 : i+3])
			if err != nil {
				return "", false
			}
			c, i = n[0], i+2
		}
		if c < 0x21 || c > 0x7e {
			return "", false
		}
		b.WriteByte(c)
	}
	return b.String(), true
}

// qrHTTPS turns https://host[:port][/] into https://host[:port] (host lower-cased). No userinfo,
// path, query or fragment; a DNS name or a dotted-quad IPv4 address (no IPv6 literal).
func qrHTTPS(v string) (string, bool) {
	rest, ok := strings.CutPrefix(v, "https://")
	if !ok {
		return "", false
	}
	rest = strings.TrimSuffix(rest, "/")
	m := qrHostPortRe.FindStringSubmatch(rest)
	if m == nil {
		return "", false
	}
	if m[2] != "" {
		if p, err := strconv.Atoi(m[2]); err != nil || p > 65535 {
			return "", false
		}
	}
	host := strings.ToLower(m[1])
	labels := strings.Split(host, ".")
	for _, l := range labels {
		if !qrLabelRe.MatchString(l) {
			return "", false
		}
	}
	if qrDigitsRe.MatchString(labels[len(labels)-1]) {
		if len(labels) != 4 {
			return "", false
		}
		for _, l := range labels {
			if n, err := strconv.Atoi(l); !qrOctetRe.MatchString(l) || err != nil || n > 255 {
				return "", false
			}
		}
	}
	out := "https://" + host
	if m[2] != "" {
		out += ":" + m[2]
	}
	return out, true
}

// ParseQR reads `onemind-join:v2?hub=…[&alt=…][&mdns=…]&ca=…&code=…&kind=…` and the older
// `onemind-join:v1?code=…&ca=…[&role=…]&hub=…` exactly as core/onemind_core/fabric.py
// parse_join_qr and sdk/ts parseJoinQR do (sdk/testdata/join-qr/vectors.json). Errors are
// *JoinQRError.
func ParseQR(payload string) (*Ticket, error) {
	if len(payload) > JoinQRMaxLen {
		return nil, qrErr("length", "a join QR is at most %d characters", JoinQRMaxLen)
	}
	m := qrPrefixRe.FindStringSubmatch(payload)
	if m == nil {
		return nil, qrErr("prefix", "not a OneMind join code (expected onemind-join:v2?…)")
	}
	if m[1] != "1" && m[1] != "2" {
		return nil, qrErr("version", "unsupported join QR version v%s (this build reads v1 and v2)", m[1])
	}
	version := int(m[1][0] - '0')
	fields := map[string]string{}
	for _, part := range strings.Split(payload[len(m[0]):], "&") {
		key, raw, eq := strings.Cut(part, "=")
		value, ok := "", false
		if eq && qrKeyRe.MatchString(key) && qrValueRe.MatchString(raw) {
			value, ok = qrUnescape(raw)
		}
		if !ok {
			return nil, qrErr("syntax", "join QR is malformed (expected key=value pairs joined by &)")
		}
		if !slices.Contains(qrFields[version], key) {
			return nil, qrErr("unknown_field", "join QR v%d has no field %q", version, key)
		}
		if _, dup := fields[key]; dup {
			return nil, qrErr("duplicate", "join QR repeats the field %q", key)
		}
		fields[key] = value
	}
	for _, key := range qrRequired[version] {
		if _, ok := fields[key]; !ok {
			return nil, qrErr("missing_field", "join QR v%d needs the field %q", version, key)
		}
	}
	t := &Ticket{Version: version, Code: fields["code"], CASHA: fields["ca"]}
	if version == 1 {
		t.Kind, t.CASHA = fields["role"], strings.ToLower(t.CASHA)
		if !codeRe.MatchString(t.Code) {
			return nil, qrErr("code", "join code must look like 7KQ4-M2XP-9D3F")
		}
	} else if !qrCodeV2Re.MatchString(t.Code) {
		return nil, qrErr("code", "join code must look like 7KQ4-M2XP-9D3F (Crockford, upper case, two dashes)")
	}
	if !shaRe.MatchString(t.CASHA) {
		return nil, qrErr("ca", "the box CA fingerprint must be 64 lower-case hex characters")
	}
	if version == 1 {
		if t.Kind != "" && t.Kind != "worker" && t.Kind != "leaf" {
			return nil, qrErr("role", "role must be worker or leaf")
		}
	} else {
		t.Kind = fields["kind"]
		if !slices.Contains(JoinKinds, t.Kind) {
			return nil, qrErr("kind", "kind must be one of %s", strings.Join(JoinKinds, ", "))
		}
	}
	var ok bool
	if t.Hub, ok = qrHTTPS(fields["hub"]); !ok {
		return nil, qrErr("hub", "hub must be an https URL such as https://box.local (no user, path or query)")
	}
	if v, has := fields["alt"]; has {
		if t.Alt, ok = qrHTTPS(v); !ok {
			return nil, qrErr("alt", "alt must be an https URL such as https://box.example.net (no user, path or query)")
		}
	}
	if v, has := fields["mdns"]; has {
		if !qrMDNSRe.MatchString(v) {
			return nil, qrErr("mdns", "mdns must be one lower-case name ending in .local, such as box1.local")
		}
		t.MDNS = v
	}
	if t.IsMachine() {
		t.Role = t.Kind
	}
	return t, nil
}

// IsMachine reports whether the ticket is for `onemind fabric join` (worker or leaf, or a v1
// ticket without a role, whose role the hub decides).
func (t *Ticket) IsMachine() bool {
	return t.Kind == "worker" || t.Kind == "leaf" || (t.Version < 2 && t.Kind == "")
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
		KeyPEM:   pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: kder}),
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
	// RelayAddrs is the owner's relay, for away. Unused today: the relay has no link back to the hub yet,
	// so no client dials it. It is kept apart from ControlAddrs so it can never become the home address.
	RelayAddrs []string `json:"relay_addrs,omitempty"`
	CASHA256   string   `json:"ca_sha256"`
	AuthKey    string   `json:"auth_key"`
	Hostname   string   `json:"hostname"`
	HubMeshIP  string   `json:"hub_mesh_ip"`
	Tags       []string `json:"tags"`
	ShieldsUp  bool     `json:"shields_up"`
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
	if pub, ok := cert.PublicKey.(*ecdsa.PublicKey); !ok || !pub.Equal(&id.Key.PublicKey) {
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
