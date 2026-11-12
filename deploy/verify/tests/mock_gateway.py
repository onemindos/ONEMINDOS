#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""A tiny in-memory imitation of the contract section 3 gateway, used only to test verify.sh.

It is NOT the gateway (that lives in core/). It copies the behaviour of core/ that
verify.sh checks (action "state" field, synchronous approve, stale_precondition on a
second install, 409 expired), so the tests prove that verify.sh passes a correct hub
and fails a broken one. --bug breaks one rule on purpose. The real gateway is checked
by running verify.sh against the compose hub and in tests/e2e-systemd/run.sh.

  python3 -I mock_gateway.py --port 18080 --owner OWNER --agent AGENT [--bug agent-can-approve]
"""

import argparse
import json
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BUGS = ("none", "agent-can-approve", "no-auth", "no-expiry", "no-online-node", "leak-ip", "install-fails", "double-install")


def now():
    return datetime.now(timezone.utc)


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class State:
    def __init__(self, tokens, bug):
        self.tokens = tokens
        self.bug = bug
        self.lock = threading.Lock()
        self.actions = {}
        self.by_key = {}
        self.installed = set()
        last = now().strftime("%Y-%m-%dT%H:%M:%SZ")
        node = {"schema": "onemind.node.status/v1", "node_id": "3f9c2a1b7d4e", "hostname": "mock-hub", "role": "hub",
                "board": "vm", "arch": "arm64", "status": "offline" if bug == "no-online-node" else "online", "last_seen": last}
        if bug == "leak-ip":
            node["ip_address"] = "192.0.2.10"
        self.nodes = [node]
        self.apps = [{"id": "uptime-kuma", "name": "Uptime Kuma", "version": "2.5.9", "description": "x", "category": "monitoring",
                      "icon": "icon.svg", "license": "MIT", "source": "https://example.invalid", "archs": ["amd64", "arm64"],
                      "requires": {"gpu": False, "minMemoryMb": 256}, "web_port": 3001}]


def make_handler(st):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, obj, ctype="application/json"):
            body = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def err(self, code, name, msg=""):
            self.send(code, {"error": name, "message": msg or name})

        def principal(self):
            if st.bug == "no-auth":
                return st.tokens[next(iter(st.tokens))]
            h = self.headers.get("Authorization", "")
            if not h.startswith("Bearer "):
                return None
            return st.tokens.get(h[7:])

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/healthz":
                return self.send(200, {"ok": True})
            if p == "/openapi.json":
                return self.send(200, {"openapi": "3.1.0", "paths": {}})
            if p == "/" or not p.startswith("/v1/"):
                return self.send(200, "<!doctype html><html><body>mock</body></html>", "text/html")
            if not self.principal():
                return self.err(401, "unauthenticated")
            if p == "/v1/instance":
                return self.send(200, {"name": "mock", "version": "0.0.0", "hub_node_id": "3f9c2a1b7d4e"})
            if p == "/v1/nodes":
                return self.send(200, st.nodes)
            if p.startswith("/v1/nodes/"):
                n = [x for x in st.nodes if x["node_id"] == p.rsplit("/", 1)[1]]
                return self.send(200, n[0]) if n else self.err(404, "not_found")
            if p == "/v1/apps":
                return self.send(200, [dict(a, installed=a["id"] in st.installed,
                                            status="installed" if a["id"] in st.installed else "available") for a in st.apps])
            if p == "/v1/actions":
                return self.send(200, list(st.actions.values()))
            if p.startswith("/v1/actions/"):
                a = st.actions.get(p.rsplit("/", 1)[1])
                return self.send(200, a) if a else self.err(404, "not_found")
            return self.err(404, "not_found")

        def do_POST(self):
            p = self.path.split("?")[0]
            who = self.principal()
            if not who:
                return self.err(401, "unauthenticated")
            if p == "/v1/actions":
                if who["role"] not in ("owner", "agent"):
                    return self.err(403, "permission_denied")
                b = self.body()
                with st.lock:
                    key = b.get("idempotency_key")
                    if key in st.by_key:
                        return self.send(200, st.actions[st.by_key[key]])
                    app = (b.get("params") or {}).get("app_id")
                    installed = app in st.installed
                    if st.bug != "double-install" and ((b.get("type") == "app.install") == installed):
                        return self.err(409, "stale_precondition", "app %r is %s" % (app, "installed" if installed else "not installed"))
                    aid = str(uuid.uuid4())
                    a = {"id": aid, "type": b.get("type"), "params": b.get("params"), "state": "awaiting_approval",
                         "requested_by": {"id": who["id"], "kind": who["kind"]}, "expires_at": b.get("expires_at")}
                    st.actions[aid] = a
                    st.by_key[key] = aid
                return self.send(201, a)
            parts = p.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "actions"] and parts[3] in ("approve", "deny"):
                a = st.actions.get(parts[2])
                if not a:
                    return self.err(404, "not_found")
                if who["role"] != "owner" and not (st.bug == "agent-can-approve" and parts[3] == "approve"):
                    return self.err(403, "permission_denied")
                if a["state"] != "awaiting_approval":
                    return self.err(409, "conflict")
                if parts[3] == "deny":
                    a["state"] = "cancelled"
                    return self.send(200, a)
                if st.bug != "no-expiry" and parse_ts(a["expires_at"]) < now():
                    a["state"] = "expired"
                    return self.err(409, "expired")
                # like core/: approve runs the executor and returns the final action
                if st.bug == "install-fails":
                    a["state"] = "failed"
                    return self.send(200, a)
                a["state"] = "succeeded"
                app = (a.get("params") or {}).get("app_id")
                if a["type"] == "app.install":
                    st.installed.add(app)
                else:
                    st.installed.discard(app)
                return self.send(200, a)
            return self.err(404, "not_found")

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--owner", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--bug", choices=BUGS, default="none")
    a = ap.parse_args()
    tokens = {a.owner: {"id": "owner", "kind": "person", "role": "owner"},
              a.agent: {"id": "dev-agent", "kind": "agent", "role": "agent"}}
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(State(tokens, a.bug)))
    print("mock gateway on %s:%d bug=%s" % (a.host, a.port, a.bug), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
