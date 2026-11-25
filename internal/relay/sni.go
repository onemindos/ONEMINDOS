// SPDX-License-Identifier: Apache-2.0

package relay

import (
	"bytes"
	"crypto/sha256"
	"crypto/tls"
	"errors"
	"io"
	"net"
	"time"
)

func sha256Sum(b []byte) [32]byte { return sha256.Sum256(b) }

var errStop = errors.New("hello captured")

// peekConn lets crypto/tls read a ClientHello from a buffer and refuses every write, so the
// handshake can never answer the client.
type peekConn struct {
	net.Conn
	r io.Reader
}

func (c peekConn) Read(p []byte) (int, error)  { return c.r.Read(p) }
func (c peekConn) Write([]byte) (int, error)   { return 0, errStop }
func (c peekConn) SetDeadline(time.Time) error { return nil }

// PeekServerName reads the TLS ClientHello from conn and returns the server name and the exact
// bytes read, which the caller must send upstream first. It uses crypto/tls's own parser (the
// handshake is aborted in GetConfigForClient, before any key is touched), and never decrypts:
// the ClientHello is sent in the clear by design. An empty name means the client sent none.
func PeekServerName(conn net.Conn, timeout time.Duration) (name string, read []byte, err error) {
	_ = conn.SetReadDeadline(time.Now().Add(timeout))
	defer conn.SetReadDeadline(time.Time{}) //nolint:errcheck
	var buf bytes.Buffer
	var got *tls.ClientHelloInfo
	srv := tls.Server(peekConn{Conn: conn, r: io.TeeReader(io.LimitReader(conn, 16*1024), &buf)}, &tls.Config{
		GetConfigForClient: func(h *tls.ClientHelloInfo) (*tls.Config, error) {
			got = &tls.ClientHelloInfo{ServerName: h.ServerName}
			return nil, errStop
		},
	})
	_ = srv.Handshake()
	if got == nil {
		return "", nil, errors.New("not a TLS ClientHello")
	}
	return got.ServerName, buf.Bytes(), nil
}
