#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Talk to NATS with the standard library only (no nats CLI needed on a node).

  python3 -I natscheck.py ping  nats://[token@]host:4222
      connect, authenticate, PING/PONG; exit 0 if the server answered
  python3 -I natscheck.py watch nats://host:4222 [--subject onemind.node.*.status] [--count 3] [--timeout 30]
      print heartbeats as they arrive; exit 0 after --count distinct nodes, 1 on timeout

Exit codes: 0 ok, 1 check failed, 2 usage error.
"""

import argparse
import json
import socket
import sys
import time
from urllib.parse import urlsplit


def connect(url, timeout):
    u = urlsplit(url if "://" in url else "nats://" + url)
    if u.scheme != "nats":
        raise ValueError("only nats:// URLs are supported")
    s = socket.create_connection((u.hostname or "127.0.0.1", u.port or 4222), timeout=timeout)
    f = s.makefile("rb")
    info = f.readline()
    if not info.startswith(b"INFO "):
        raise ConnectionError("not a NATS server (greeting %r)" % info[:40])
    opts = {"verbose": False, "pedantic": False, "name": "onemind-natscheck", "lang": "python-stdlib",
            "version": "0.1.0", "protocol": 1}
    if u.username and u.password is not None:
        opts.update(user=u.username, **{"pass": u.password})
    elif u.username:
        opts["auth_token"] = u.username
    s.sendall(b"CONNECT " + json.dumps(opts).encode() + b"\r\nPING\r\n")
    while True:
        line = f.readline().rstrip(b"\r\n")
        if not line:
            raise ConnectionError("connection closed during handshake")
        if line == b"PONG":
            return s, f, json.loads(info[5:])
        if line.startswith(b"-ERR"):
            raise ConnectionError(line.decode(errors="replace"))


def cmd_ping(a):
    s, _, info = connect(a.url, a.timeout)
    s.close()
    print("ok: NATS %s answered (server_name=%s, auth_required=%s)" % (info.get("version"), info.get("server_name"), info.get("auth_required", False)))
    return 0


def cmd_watch(a):
    s, f, _ = connect(a.url, a.timeout)
    s.sendall(("SUB %s 1\r\nPING\r\n" % a.subject).encode())
    seen = {}
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        s.settimeout(max(0.1, deadline - time.time()))
        try:
            line = f.readline()
        except socket.timeout:
            break
        if not line:
            break
        line = line.rstrip(b"\r\n")
        if line == b"PING":
            s.sendall(b"PONG\r\n")
            continue
        if line.startswith(b"-ERR"):
            print(line.decode(errors="replace"), file=sys.stderr)
            return 1
        if not line.startswith(b"MSG "):
            continue
        parts = line.split()
        size = int(parts[-1])
        payload = f.read(size + 2)[:size]
        try:
            hb = json.loads(payload)
        except ValueError:
            print("non-JSON message on %s" % parts[1].decode(), file=sys.stderr)
            continue
        nid = hb.get("node_id", "?")
        if nid not in seen:
            print("%-14s %-12s %-6s %-12s %-6s %s" % (nid, hb.get("hostname"), hb.get("role"), hb.get("board"), hb.get("arch"), hb.get("observed_at")))
        seen[nid] = hb
        if len(seen) >= a.count:
            s.close()
            print("ok: %d node(s) heartbeating" % len(seen))
            return 0
    s.close()
    print("timeout: saw %d of %d node(s) in %ss" % (len(seen), a.count, a.timeout), file=sys.stderr)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("ping")
    p.add_argument("url")
    p.add_argument("--timeout", type=float, default=5)
    w = sub.add_parser("watch")
    w.add_argument("url")
    w.add_argument("--subject", default="onemind.node.*.status")
    w.add_argument("--count", type=int, default=1)
    w.add_argument("--timeout", type=float, default=30)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    try:
        return cmd_ping(a) if a.cmd == "ping" else cmd_watch(a)
    except (OSError, ConnectionError, ValueError) as e:
        print("fail: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
