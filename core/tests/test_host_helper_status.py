# SPDX-License-Identifier: Apache-2.0
"""#875 mount-host-socket: `GET /v1/status` says whether the host helper is reachable, and no host
action starts while it is missing.

The gateway is not a k3s pod: in the image it is onemind-gateway.service (user onemind) and reaches
/run/onemind/host.sock (onemind-host.socket, 0660 root:onemind) directly. A real gateway talks over a
real Unix socket to the stand-in for `onemindd host serve` from test_hostlink.py.
"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time

from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
from onemind_core.osupdate import ENGINE
from test_hostlink import ask, box, host, link_settings, state  # noqa: F401  (box, host: fixtures)

MISSING = "host helper: missing"


def host_part(c) -> dict:
    r = c.get("/v1/status", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()["host"]


def test_a_reachable_helper_is_ok_and_names_the_box(box):
    h = host_part(box)
    assert h["helper"] == "reachable" and h["state"] == "ok" and h["observed_at"]
    assert h["summary"] == "host helper: reachable"
    assert h["hostname"] == "testbox"  # read from the host helper over the socket, not from the gateway


def test_no_socket_is_missing_and_never_ok(settings, clock, executor, tmp_path):
    path = tmp_path / "none.sock"
    app = create_app(link_settings(settings, path), clock=clock, executor=executor)
    with TestClient(app) as c:
        body = c.get("/v1/status", headers=OWNER).json()
        h = body["host"]
        assert h["helper"] == "missing" and h["state"] == "attention" and h["hostname"] is None
        assert h["summary"].startswith(MISSING)
        assert str(tmp_path) not in h["summary"] and "/run/" not in h["summary"]  # failure text is logged, never sent
        assert body["state"] != "ok"


def test_the_socket_removed_after_start_turns_missing(box, host):
    assert host_part(box)["helper"] == "reachable"
    host.close()  # stops the helper and removes the socket file
    assert not os.path.exists(host.path)
    h = host_part(box)
    assert h["helper"] == "missing" and h["state"] != "ok" and h["hostname"] is None


def test_a_helper_that_errors_is_missing(box, host):
    host.status_code = 500
    h = host_part(box)
    assert h["helper"] == "missing" and h["state"] != "ok"


def test_a_silent_socket_is_missing_without_holding_the_status_up(settings, clock, executor):
    d = tempfile.mkdtemp(prefix="hs")  # short: AF_UNIX paths are limited to about 100 bytes
    path = os.path.join(d, "host.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(4)  # accepts, never answers: a helper stuck before it serves
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                held.append(srv.accept()[0])
            except OSError:
                pass

    threading.Thread(target=accept, daemon=True).start()
    try:
        app = create_app(link_settings(settings, path), clock=clock, executor=executor)
        with TestClient(app) as c:
            t = time.monotonic()
            assert app.state.hostlink.probe().reachable is False
            assert time.monotonic() - t < 5  # a short probe, not the 10 s action timeout
            h = host_part(c)
            assert h["helper"] == "missing" and h["state"] != "ok"
    finally:
        stop.set()
        for s in held:
            s.close()
        srv.close()


def test_a_hostname_that_is_not_a_hostname_is_dropped(box, host):
    for bad in ("bad name\n<b>", "x" * 300, 42, "-lead"):
        host.hostname = bad
        h = host_part(box)
        assert h["helper"] == "reachable" and h["hostname"] is None, bad
    host.hostname = None  # an older helper that does not send it
    assert host_part(box)["hostname"] is None


def test_no_host_action_starts_while_the_helper_is_missing(box, host):
    host.close()
    inst = box.get("/v1/os/updates", headers=OWNER).json()["install"]
    assert inst == ENGINE  # a plain sentence, no path, no traceback
    r = ask(box)
    assert r.status_code == 201, r.text
    done = box.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert done.status_code == 200, done.text
    a = state(box, r.json()["id"])
    assert a["state"] == "failed" and a["result"]["message"] == ENGINE["message"]
    assert a["result"]["steps"][0]["result"] == "engine_unreachable"
    assert host.posts == []  # nothing reached a host
    for leak in ("Traceback", "Errno", "/run/", host.path):
        assert leak not in a["result"]["message"]
