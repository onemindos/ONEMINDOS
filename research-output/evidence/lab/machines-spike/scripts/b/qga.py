#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""LAB-machines-spike option B: minimal QEMU guest agent client.
  qga.py <command> ['<json arguments>']   e.g. qga.py guest-fsfreeze-freeze"""
import json, os, random, socket, sys

def main():
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(float(os.environ.get("QGA_TIMEOUT", "60")))
    s.connect(os.environ.get("QGA_SOCK", "/run/vm/qga.sock"))
    f = s.makefile("rwb")

    def send(msg):
        f.write(json.dumps(msg).encode() + b"\n"); f.flush()

    def read():
        while True:
            line = f.readline()
            if not line:
                raise SystemExit("qga: connection closed")
            line = line.replace(b"\xff", b"").strip()
            if line:
                return json.loads(line)

    sid = random.randint(1, 2**31)            # flush stale replies left by an earlier client
    send({"execute": "guest-sync-delimited", "arguments": {"id": sid}})
    while read().get("return") != sid:
        pass
    msg = {"execute": sys.argv[1]}
    if len(sys.argv) > 2:
        msg["arguments"] = json.loads(sys.argv[2])
    send(msg)
    print(json.dumps(read()))

if __name__ == "__main__":
    main()
