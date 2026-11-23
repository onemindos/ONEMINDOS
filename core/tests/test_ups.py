# SPDX-License-Identifier: Apache-2.0
"""IMG-06 (#244): GET /v1/system/ups reads the UPS from upsd (NUT's protocol) and never fails a box without one.

A tiny stand-in for upsd answers LIST VAR on a loopback port in this test only; the gateway is pointed at it with
ONEMIND_UPS_ADDR. The real upsd runs in the image (onemind-ups.service)."""

import socket
import threading

import pytest

from conftest import ADULT, OWNER, make_client
from onemind_core.identity.scopes import required_scopes
from onemind_core.routers.ups import ADDR_ENV


def fake_upsd(answer: str):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    seen: list[str] = []

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                seen.append(conn.recv(1024).decode())
                conn.sendall(answer.encode())

    threading.Thread(target=serve, daemon=True).start()
    return srv, seen


def listing(**v: str) -> str:
    body = "".join(f'VAR onemind {k} "{x}"\n' for k, x in v.items())
    return f"BEGIN LIST VAR onemind\n{body}END LIST VAR onemind\n"


def get(settings, clock, monkeypatch, answer: str | None, headers=OWNER):
    if answer is None:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()  # nothing listens there: a box without a UPS
        monkeypatch.setenv(ADDR_ENV, f"127.0.0.1:{port}")
        return make_client(settings, clock).get("/v1/system/ups", headers=headers), []
    srv, seen = fake_upsd(answer)
    monkeypatch.setenv(ADDR_ENV, f"127.0.0.1:{srv.getsockname()[1]}")
    try:
        return make_client(settings, clock).get("/v1/system/ups", headers=headers), seen
    finally:
        srv.close()


def test_a_box_without_a_ups_says_so(settings, clock, monkeypatch):
    r, _ = get(settings, clock, monkeypatch, None)
    assert r.status_code == 200
    assert r.json() == {"present": False, "state": "none", "flags": [], "battery_percent": None,
                        "runtime_seconds": None, "load_percent": None, "model": None}


def test_on_mains_with_the_battery_facts(settings, clock, monkeypatch):
    r, seen = get(settings, clock, monkeypatch, listing(**{
        "ups.status": "OL CHRG", "battery.charge": "97", "battery.runtime": "1830", "ups.load": "21.6",
        "device.mfr": "APC", "device.model": "Back-UPS ES 700"}))
    assert seen == ["LIST VAR onemind\n"]          # a read, never a command or a login
    assert r.json() == {"present": True, "state": "online", "flags": ["OL", "CHRG"], "battery_percent": 97,
                        "runtime_seconds": 1830, "load_percent": 22, "model": "APC Back-UPS ES 700"}


@pytest.mark.parametrize(("flags", "state"), [("OB DISCHRG", "on_battery"), ("OB LB", "low_battery"),
                                              ("OL FSD", "low_battery"), ("", "unknown")])
def test_battery_states(settings, clock, monkeypatch, flags, state):
    r, _ = get(settings, clock, monkeypatch, listing(**{"ups.status": flags, "battery.charge": "5"}))
    assert r.json()["state"] == state


def test_a_driver_with_no_fresh_data_is_present_but_unknown(settings, clock, monkeypatch):
    r, _ = get(settings, clock, monkeypatch, "ERR DATA-STALE\n")
    assert r.status_code == 200
    assert (r.json()["present"], r.json()["state"]) == (True, "unknown")


def test_household_reads_it_with_the_nodes_scope(settings, clock, monkeypatch):
    r, _ = get(settings, clock, monkeypatch, None, headers=ADULT)
    assert r.status_code == 200
    assert required_scopes("GET", "/v1/system/ups") == ("nodes:read",)
