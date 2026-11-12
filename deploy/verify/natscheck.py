#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Talk to NATS with the Python standard library only (no nats CLI needed on a machine).

Ported from PR #27 and adapted to the NATS auth main has (contract §1, §12.9):
  * the hub NATS of a developer install has no auth (v0); `ping` says so (auth_required=False),
  * onemindd takes credentials only inside ONEMIND_NATS_URL (nats://TOKEN@host or user:pass@host),
  * per-node nkey users and TLS with the box CA (H-06) arrive through the node's NATS leaf, which
    listens on loopback; `leafz` reads that leaf's /leafz to see whether its link to the hub is up.

  natscheck.py ping  (URL | --env-file F) [--ca FILE] [--timeout S]
      connect, authenticate, PING/PONG; exit 0 if the server answered
  natscheck.py watch (URL | --env-file F) [--subject onemind.node.*.status] [--count N] [--timeout S]
      print heartbeats as they arrive; exit 0 once N distinct nodes sent a valid one (§2)
  natscheck.py leafz [--monitor 127.0.0.1:8222] [--timeout S]
      exit 0 if the local NATS server has at least one leaf connection

--env-file reads ONEMIND_NATS_URL from a KEY=VALUE file such as /etc/onemind/onemindd.env, so a
URL with credentials never shows in the process list. Output never prints credentials.
Exit codes: 0 ok, 1 check failed, 2 usage error.
"""

import argparse
import json
import re
import socket
import ssl
import sys
import time
import urllib.request
from urllib.parse import unquote, urlsplit

HEARTBEAT_SCHEMA = "onemind.node.status/v1"
SUBJECT_RE = re.compile(r"onemind\.node\.([A-Za-z0-9_-]{1,64})\.status")


def read_env_url(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("ONEMIND_NATS_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise ValueError("%s has no ONEMIND_NATS_URL" % path)


def safe_url(url):
    """The URL without credentials, for messages."""
    u = urlsplit(url if "://" in url else "nats://" + url)
    host = u.hostname or "127.0.0.1"
    if ":" in host:
        host = "[%s]" % host
    return "%s://%s:%d" % (u.scheme or "nats", host, u.port or 4222)


class Conn:
    def __init__(self, url, timeout, ca=None):
        u = urlsplit(url if "://" in url else "nats://" + url)
        if u.scheme not in ("nats", "tls"):
            raise ValueError("only nats:// and tls:// URLs are supported")
        self.host = u.hostname or "127.0.0.1"
        sock = socket.create_connection((self.host, u.port or 4222), timeout=timeout)
        self.sock, self.buf = sock, b""
        line = self.readline()
        if not line.startswith(b"INFO "):
            raise ConnectionError("not a NATS server (greeting %r)" % line[:40])
        self.info = json.loads(line[5:])
        if u.scheme == "tls" or self.info.get("tls_required"):
            ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
            self.sock = ctx.wrap_socket(sock, server_hostname=self.host)
            self.tls = True
        else:
            self.tls = False
        opts = {"verbose": False, "pedantic": False, "name": "onemind-natscheck", "lang": "python-stdlib",
                "version": "0.2.0", "protocol": 1, "tls_required": self.tls}
        user = unquote(u.username) if u.username else None
        if user and u.password is not None:
            opts.update(user=user, **{"pass": unquote(u.password)})
        elif user:
            opts["auth_token"] = user
        elif self.info.get("auth_required") and self.info.get("nonce"):
            raise ConnectionError("the server wants nkey or JWT credentials (H-06 per-node users); natscheck "
                                  "signs no nonces: check the node's leaf link instead (natscheck.py leafz)")
        self.sock.sendall(b"CONNECT " + json.dumps(opts).encode() + b"\r\nPING\r\n")
        while True:
            line = self.readline()
            if line == b"PONG":
                return
            if line.startswith(b"-ERR"):
                msg = line.decode(errors="replace")
                if "authorization" in msg.lower():
                    msg += " (wrong or missing credentials in ONEMIND_NATS_URL)"
                raise ConnectionError(msg)

    def readline(self):
        while b"\r\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("NATS closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\r\n", 1)
        return line

    def read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("NATS closed the connection")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def url_of(a):
    if a.env_file:
        return read_env_url(a.env_file)
    if not a.url:
        raise ValueError("give a NATS URL or --env-file")
    return a.url


def cmd_ping(a):
    url = url_of(a)
    c = Conn(url, a.timeout, a.ca)
    c.close()
    i = c.info
    print("ok: NATS %s at %s answered (tls=%s, auth_required=%s)" % (
        i.get("version"), safe_url(url), c.tls, bool(i.get("auth_required"))))
    return 0


def cmd_watch(a):
    url = url_of(a)
    c = Conn(url, a.timeout, a.ca)
    c.sock.sendall(("SUB %s 1\r\nPING\r\n" % a.subject).encode())
    seen, deadline = {}, time.time() + a.timeout
    try:
        while time.time() < deadline:
            c.sock.settimeout(max(0.1, deadline - time.time()))
            try:
                line = c.readline()
            except (socket.timeout, TimeoutError):
                break
            if line == b"PING":
                c.sock.sendall(b"PONG\r\n")
                continue
            if line.startswith(b"-ERR"):
                print(line.decode(errors="replace"), file=sys.stderr)
                return 1
            if not line.startswith(b"MSG "):
                continue
            parts = line.split()
            subject, size = parts[1].decode(errors="replace"), int(parts[-1])
            payload = c.read(size + 2)[:size]
            m = SUBJECT_RE.fullmatch(subject)
            try:
                hb = json.loads(payload)
            except ValueError:
                print("non-JSON message on %s" % subject, file=sys.stderr)
                continue
            if not (m and isinstance(hb, dict) and hb.get("schema") == HEARTBEAT_SCHEMA and hb.get("node_id") == m.group(1)):
                print("invalid heartbeat on %s (schema or node_id does not match the subject)" % subject, file=sys.stderr)
                continue
            nid = hb["node_id"]
            if nid not in seen:
                print("%-14s %-16s %-5s %-12s %-6s %s" % (nid, hb.get("hostname"), hb.get("role"), hb.get("board"),
                                                         hb.get("arch"), hb.get("observed_at")))
            seen[nid] = hb
            if len(seen) >= a.count:
                print("ok: %d node(s) heartbeating" % len(seen))
                return 0
    finally:
        c.close()
    print("timeout: saw %d of %d node(s) in %ss" % (len(seen), a.count, a.timeout), file=sys.stderr)
    return 1


def cmd_leafz(a):
    with urllib.request.urlopen("http://%s/leafz" % a.monitor, timeout=a.timeout) as r:
        lz = json.load(r)
    n = int(lz.get("leafnodes") or 0)
    names = sorted({str(x.get("name", "?")) for x in lz.get("leafs") or []})
    if n > 0:
        print("ok: %d leaf connection(s) (%s)" % (n, ", ".join(names)))
        return 0
    print("down: no leaf connection on %s" % a.monitor, file=sys.stderr)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    for name in ("ping", "watch"):
        p = sub.add_parser(name)
        p.add_argument("url", nargs="?", help="nats://[TOKEN@|USER:PASS@]host:4222 or tls://... (visible in ps)")
        p.add_argument("--env-file", help="read ONEMIND_NATS_URL from this KEY=VALUE file")
        p.add_argument("--ca", help="CA file for tls:// (the box CA)")
        p.add_argument("--timeout", type=float, default=5 if name == "ping" else 30)
        if name == "watch":
            p.add_argument("--subject", default="onemind.node.*.status")
            p.add_argument("--count", type=int, default=1)
    lz = sub.add_parser("leafz")
    lz.add_argument("--monitor", default="127.0.0.1:8222", help="the leaf's loopback monitoring address")
    lz.add_argument("--timeout", type=float, default=5)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    try:
        return {"ping": cmd_ping, "watch": cmd_watch, "leafz": cmd_leafz}[a.cmd](a)
    except (OSError, ConnectionError, ValueError) as e:
        print("fail: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
