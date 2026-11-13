#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""An in-memory imitation of a OneMind hub, used only to test deploy/verify (ported from PR #27).

It is NOT the gateway (that is core/). It answers the HTTP API that verify.sh checks (contract §3,
§7, §11.3 /mcp, §11.4 catalog fields) and runs a tiny NATS server (§1, §12.9) that publishes
heartbeats and a hash-chained onemind.audit stream, so verify.sh can be tested end to end without
Docker. --bug breaks one rule on purpose; the tests check that verify.sh then FAILs the right line.
The real gateway is checked by verify.sh against the compose hub and in tests/e2e-systemd/run.sh.

  python3 -I mock_gateway.py --owner TOKEN --agent TOKEN [--bug NAME] [--nats-token T] [--audit-file F]

Prints "ready http=<port> nats=<port>" once both listen (ports are picked by the OS).
"""

import argparse
import hashlib
import json
import socket
import socketserver
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BUGS = {
    "none": "a correct hub",
    "no-auth": "every request is the owner, even without a token",
    "agent-can-approve": "an agent may approve",
    "no-expiry": "expires_at is ignored",
    "deny-not-cancelled": "deny leaves the action pending",
    "no-idempotency": "the same idempotency key makes a new action",
    "params-changed": "the stored params differ from the request",
    "install-fails": "an approved install ends failed",
    "no-online-node": "every node is offline",
    "leak-ip": "nodes carry an IP address",
    "bad-board": "a board value outside the contract",
    "owner-on-mcp": "a person may use /mcp",
    "mcp-approve-tool": "/mcp offers an approve tool",
    "bad-audit-chain": "one audit hash is wrong",
    "bad-heartbeat": "heartbeats name another node than their subject",
    "no-dashboard": "no dashboard at /",
    "hostile-ids": "node ids that are Python code (verify.sh must treat them as data)",
}
HOSTILE = "x' or __import__('os').system('touch {marker}') or '"


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def now():
    return datetime.now(timezone.utc)


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def subject_match(pattern, subject):
    p, s = pattern.split("."), subject.split(".")
    for i, tok in enumerate(p):
        if tok == ">":
            return len(s) > i
        if i >= len(s) or (tok != "*" and tok != s[i]):
            return False
    return len(p) == len(s)


def heartbeat(node_id, hostname, role, board, arch):
    """A §2 heartbeat (same keys as internal/heartbeat.Status)."""
    return {"schema": "onemind.node.status/v1", "node_id": node_id, "hostname": hostname, "role": role,
            "board": board, "arch": arch,
            "os": {"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"},
            "kernel": "6.12.0", "cpu_model": "mock", "cpus": 4, "mem_total_mb": 8000, "mem_available_mb": 4000,
            "disk_total_gb": 100.0, "disk_free_gb": 50.0, "tpm2": False, "secure_boot": "unknown",
            "k3s": {"present": True, "role": "server" if role == "hub" else "agent", "ready": True},
            "rauc": {"present": False, "booted_slot": None, "slots": []},
            "gpu": {"nvidia": False, "model": None}, "uptime_s": 100, "agent_version": "0.0.0-mock",
            "observed_at": iso(now())}


class Hub:
    def __init__(self, owner, agent, bug, marker, audit_file):
        self.bug, self.audit_file = bug, audit_file
        self.tokens = {owner: {"id": "owner", "kind": "person", "role": "owner"},
                       agent: {"id": "dev-agent", "kind": "agent", "role": "agent"}}
        self.lock = threading.RLock()
        self.actions, self.by_key, self.installed = {}, {}, set()
        self.prev, self.seq = "0" * 64, 0
        self.subs = []  # (pattern, sid, conn)
        hub_id = HOSTILE.format(marker=marker) if bug == "hostile-ids" else "3f9c2a1b7d4e"
        self.hub_id = hub_id
        self.nodes = [heartbeat(hub_id, "mock-hub", "hub", "bad-board" == bug and "raspberrypi" or "vm", "arm64"),
                      heartbeat("a1b2c3d4e5f6", "mock-node", "node", "rpi5", "arm64")]
        if bug == "leak-ip":
            self.nodes[1]["ip"] = "192.0.2.10"
        self.apps = [{"id": "ntfy", "name": "ntfy", "version": "2.0.0", "description": "push notifications",
                      "category": "tools", "icon": "icon.svg", "license": "Apache-2.0", "source": "https://example.invalid/ntfy",
                      "archs": ["amd64", "arm64"], "requires": {"gpu": False}, "web_port": 80,
                      "links": [], "tier": "community", "scan": {"scanned_at": iso(now()), "result": "pass"}}]

    # ---- NATS side ----
    def publish(self, subject, payload):
        data = payload.encode() if isinstance(payload, str) else payload
        with self.lock:
            subs = [(sid, c) for pat, sid, c in self.subs if subject_match(pat, subject)]
        for sid, c in subs:
            try:
                c.sendall(b"MSG %s %s %d\r\n%s\r\n" % (subject.encode(), sid.encode(), len(data), data))
            except OSError:
                pass

    def audit(self, event, action, principal):
        with self.lock:
            self.seq += 1
            rec = {"seq": self.seq, "ts": iso(now()), "event": event, "action_id": action["id"],
                   "action_type": action["type"], "principal": {"id": principal["id"], "kind": principal["kind"]}}
            h = hashlib.sha256((self.prev + canon(rec)).encode()).hexdigest()
            if self.bug == "bad-audit-chain" and self.seq == 3:
                h = "f" * 64
            rec.update(prev_hash=self.prev, hash=h)
            self.prev = h
            if self.audit_file:
                with open(self.audit_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")
        self.publish("onemind.audit", json.dumps(rec))

    def heartbeats(self):
        while True:
            for n in self.nodes:
                if self.bug == "hostile-ids" and n["node_id"] == self.hub_id:
                    continue  # not a valid subject token; the HTTP side carries it
                hb = dict(n, observed_at=iso(now()))
                if self.bug == "bad-heartbeat":
                    hb["node_id"] = "someone-else"
                self.publish("onemind.node.%s.status" % n["node_id"], json.dumps(hb))
            time.sleep(1)

    # ---- actions ----
    def create(self, who, body):
        with self.lock:
            key = body.get("idempotency_key")
            if key in self.by_key and self.bug != "no-idempotency":
                return 200, self.actions[self.by_key[key]]
            params = dict(body.get("params") or {})
            if self.bug == "params-changed":
                params["extra"] = True
            a = {"id": str(uuid.uuid4()), "type": body.get("type"), "params": params, "state": "awaiting_approval",
                 "requested_by": {"id": who["id"], "kind": who["kind"]}, "decided_by": None,
                 "expires_at": body.get("expires_at") or iso(now() + timedelta(minutes=15)), "result": None}
            self.actions[a["id"]] = a
            self.by_key[key] = a["id"]
        self.audit("action.requested", a, who)
        return 201, a

    def decide(self, who, aid, verb):
        with self.lock:
            a = self.actions.get(aid)
            if a is None:
                return 404, {"error": "not_found", "message": "no such action"}
            owner = who["kind"] == "person" and who["role"] == "owner"
            if not owner and not (self.bug == "agent-can-approve" and verb == "approve"):
                return 403, {"error": "permission_denied", "message": "only the owner decides"}
            if a["state"] != "awaiting_approval":
                return 409, {"error": "conflict", "message": "action is " + a["state"]}
            if verb == "deny":
                if self.bug != "deny-not-cancelled":
                    a["state"] = "cancelled"
                a["decided_by"] = {"id": who["id"], "kind": who["kind"]}
                event = "action.denied"
            else:
                exp = datetime.strptime(a["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if exp < now() and self.bug != "no-expiry":
                    a["state"] = "expired"
                    return 409, {"error": "expired", "message": "expires_at has passed"}
                a["decided_by"] = {"id": who["id"], "kind": who["kind"]}
                app = a["params"].get("app_id")
                if self.bug == "install-fails":
                    a.update(state="failed", result={"error": "mock failure"})
                else:
                    a["state"] = "succeeded"
                    (self.installed.add if a["type"] == "app.install" else self.installed.discard)(app)
                event = "action.approved"
        self.audit(event, a, who)
        return 200, a


def http_handler(hub):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, obj=None, ctype="application/json", headers=None):
            body = b"" if obj is None else (obj.encode() if isinstance(obj, str) else json.dumps(obj).encode())
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def who(self):
            if hub.bug == "no-auth":
                return hub.tokens[next(iter(hub.tokens))]
            h = self.headers.get("Authorization", "")
            return hub.tokens.get(h[7:]) if h.startswith("Bearer ") else None

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/healthz":
                return self.send(200, {"ok": True})
            if p == "/openapi.json":
                return self.send(200, {"openapi": "3.1.0", "paths": {"/v1/actions": {}}})
            if not p.startswith("/v1/"):
                if hub.bug == "no-dashboard":
                    return self.send(404, {"error": "not_found"})
                return self.send(200, "<!doctype html><html><body>mock dashboard</body></html>", "text/html")
            who = self.who()
            if not who:
                return self.send(401, {"error": "unauthenticated", "message": "missing or unknown token"})
            if p == "/v1/instance":
                return self.send(200, {"name": "mock hub", "version": "0.0.0", "hub_node_id": hub.hub_id})
            last = iso(now())
            status = "offline" if hub.bug == "no-online-node" else "online"
            nodes = [dict(n, status=status, last_seen=last) for n in hub.nodes]
            if p == "/v1/nodes":
                return self.send(200, nodes)
            if p.startswith("/v1/nodes/"):
                m = [n for n in nodes if n["node_id"] == p[len("/v1/nodes/"):]]
                return self.send(200, m[0]) if m else self.send(404, {"error": "not_found", "message": "no such node"})
            if p == "/v1/apps":
                with hub.lock:
                    return self.send(200, [dict(a, installed=a["id"] in hub.installed,
                                                status="installed" if a["id"] in hub.installed else "available")
                                           for a in hub.apps])
            if p == "/v1/actions":
                with hub.lock:
                    return self.send(200, list(hub.actions.values()))
            if p.startswith("/v1/actions/"):
                a = hub.actions.get(p[len("/v1/actions/"):])
                return self.send(200, a) if a else self.send(404, {"error": "not_found", "message": "no such action"})
            return self.send(404, {"error": "not_found", "message": p})

        def do_POST(self):
            p = self.path.split("?")[0]
            who = self.who()
            if not who:
                return self.send(401, {"error": "unauthenticated", "message": "missing or unknown token"})
            if p == "/mcp":
                return self.mcp(who)
            if p == "/v1/actions":
                return self.send(*hub.create(who, self.body()))
            parts = p.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "actions"] and parts[3] in ("approve", "deny"):
                return self.send(*hub.decide(who, parts[2], parts[3]))
            return self.send(404, {"error": "not_found", "message": p})

        def mcp(self, who):
            if who["kind"] != "agent" and hub.bug != "owner-on-mcp":
                return self.send(403, {"error": "permission_denied", "message": "MCP is for agent principals"})
            msg = self.body()
            if "id" not in msg:
                return self.send(202)
            m, rid = msg.get("method"), msg["id"]
            if m == "initialize":
                res = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                       "serverInfo": {"name": "mock-onemind", "version": "0"}}
            elif m == "tools/list":
                names = ["list_nodes", "list_apps", "request_action"] + (["approve_action"] if hub.bug == "mcp-approve-tool" else [])
                res = {"tools": [{"name": n, "inputSchema": {"type": "object"}} for n in names]}
            elif m == "tools/call" and (msg.get("params") or {}).get("name") == "request_action":
                args = msg["params"].get("arguments") or {}
                _, a = hub.create(who, {"type": args.get("type"), "params": {"app_id": args.get("app_id")},
                                        "idempotency_key": "mcp-" + uuid.uuid4().hex})
                sc = {"action_id": a["id"], "state": a["state"]}
                res = {"content": [{"type": "text", "text": json.dumps(sc)}], "structuredContent": sc}
            else:
                return self.send(200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown"}})
            return self.send(200, {"jsonrpc": "2.0", "id": rid, "result": res}, headers={"Mcp-Session-Id": "mock-session"})

    return H


def nats_handler(hub, token, nkey):
    class N(socketserver.StreamRequestHandler):
        def handle(self):
            c = self.request
            info = {"server_id": "MOCK", "server_name": "mock-hub", "version": "2.15.2", "proto": 1,
                    "max_payload": 1048576, "auth_required": bool(token or nkey)}
            if nkey:
                info["nonce"] = "bW9jay1ub25jZQ"
            c.sendall(b"INFO " + json.dumps(info).encode() + b"\r\n")
            try:
                while True:
                    line = self.rfile.readline()
                    if not line:
                        break
                    op = line.split(b" ", 1)[0].strip().upper()
                    if op == b"CONNECT":
                        opts = json.loads(line[8:])
                        if (token and opts.get("auth_token") != token) or nkey:
                            c.sendall(b"-ERR 'Authorization Violation'\r\n")
                            break
                    elif op == b"PING":
                        c.sendall(b"PONG\r\n")
                    elif op == b"SUB":
                        parts = line.split()
                        with hub.lock:
                            hub.subs.append((parts[1].decode(), parts[-1].decode(), c))
                    elif op == b"PUB":
                        parts = line.split()
                        data = self.rfile.read(int(parts[-1]) + 2)[:-2]
                        hub.publish(parts[1].decode(), data)
            except OSError:
                pass
            finally:
                with hub.lock:
                    hub.subs = [s for s in hub.subs if s[2] is not c]
    return N


class TCP(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--owner", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--bug", choices=sorted(BUGS), default="none")
    ap.add_argument("--marker", default="/nonexistent/onemind-verify-marker", help="file the hostile-ids payload would create")
    ap.add_argument("--nats-token", default="", help="NATS requires this token (auth_token)")
    ap.add_argument("--nats-nkey", action="store_true", help="NATS asks for nkey auth (sends a nonce, refuses everyone)")
    ap.add_argument("--audit-file", default="")
    a = ap.parse_args()
    hub = Hub(a.owner, a.agent, a.bug, a.marker, a.audit_file)
    web = ThreadingHTTPServer(("127.0.0.1", 0), http_handler(hub))
    web.daemon_threads = True
    nats = TCP(("127.0.0.1", 0), nats_handler(hub, a.nats_token, a.nats_nkey))
    for target in (web.serve_forever, nats.serve_forever, hub.heartbeats):
        threading.Thread(target=target, daemon=True).start()
    print("ready http=%d nats=%d" % (web.server_address[1], nats.server_address[1]), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    socket.setdefaulttimeout(None)
    sys.exit(main())
