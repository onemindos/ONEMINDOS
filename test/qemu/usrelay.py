#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One guest connection -> the host's channel server (CRITERIA-UPDATE-SIGNED.md). QEMU's user network runs this
once per connection (`guestfwd=tcp:10.0.2.100:8000-cmd:python3 -I usrelay.py <port>`): stdin and stdout are the
guest's TCP stream, which is copied to and from 127.0.0.1:<port> on the host. Standard library only.

  python3 -I usrelay.py <port>
"""
import os, socket, sys, threading


def pump_in(sock):
    """Guest -> server, until the guest closes its side."""
    while True:
        data = os.read(0, 65536)
        if not data:
            break
        sock.sendall(data)
    try:
        sock.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def main(argv=None):
    port = int((argv or sys.argv[1:])[0])
    sock = socket.create_connection(("127.0.0.1", port))
    threading.Thread(target=pump_in, args=(sock,), daemon=True).start()
    while True:                                     # server -> guest, until the server closes
        data = sock.recv(65536)
        if not data:
            break
        view = memoryview(data)
        while view:
            n = os.write(1, view)
            view = view[n:]
    return 0


if __name__ == "__main__":
    sys.exit(main())
