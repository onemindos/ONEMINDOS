#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""TLS handshake to a NATS leafnode port: read the plaintext INFO, then upgrade to TLS
and verify the server certificate against the lab CA. Exit 0 on a verified handshake."""
import socket, ssl, sys
host, port, ca = sys.argv[1], int(sys.argv[2]), sys.argv[3]
s = socket.create_connection((host, port), timeout=10)
info = b""
while not info.endswith(b"\r\n"):
    c = s.recv(1)
    if not c: break
    info += c
ctx = ssl.create_default_context(cafile=ca)
t = ctx.wrap_socket(s, server_hostname=host)
print("INFO tls_required=%s" % (b'"tls_required":true' in info), "|", t.version(), t.cipher()[0],
      "| cert subject", dict(x[0] for x in t.getpeercert()["subject"]).get("commonName"))
t.close()
