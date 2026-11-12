#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Plaintext leafnode CONNECT (no TLS) to a TLS-required leaf port; print what the hub answers."""
import json, socket, sys
host, port, user, pw = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
s = socket.create_connection((host, port), timeout=10)
info = s.recv(4096).split(b"\r\n")[0]
s.sendall(b"CONNECT " + json.dumps({"user": user, "pass": pw, "tls_required": False, "name": "neg-plain"}).encode() + b"\r\nPING\r\n")
try:
    resp = s.recv(4096)
except Exception as e:
    resp = repr(e).encode()
print("tls_required_in_INFO=%s answer=%r" % (b'"tls_required":true' in info, resp[:120]))
