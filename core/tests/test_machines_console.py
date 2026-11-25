# SPDX-License-Identifier: Apache-2.0
"""The machine console broker (MACH-01 part 4, #281; docs/umbrel2/machines.md MACH-4).

Real gateway, real ticket route, real WebSocket through the app. The display is a scripted one,
because there is no KVM here; the kubectl-proxy upstream is covered by what it can be checked on
without a cluster (its URL, a missing proxy, a proxy that never reports a port).
"""

from __future__ import annotations

import asyncio
import json
import stat
import struct
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import OWNER
from onemind_core.machines.console import (
    CLOSE_SUPERSEDED, CLOSE_TOO_SLOW, ConsoleBroker, KubectlProxyUpstream, Session, ViewOnlyFilter, vnc_url,
)
from test_machines_actions import VM, box, done  # noqa: F401  (the fixture and helpers of the action tests)


class Display:
    """A scripted VNC display: what it should say, and what the browser sent it."""

    def __init__(self, says=(b"RFB 003.008\n",)):
        self.says, self.got, self.closed = list(says), [], False
        self.gate = asyncio.Event()

    async def recv(self):
        await asyncio.sleep(0)  # a socket read always gives the loop a turn
        if self.says:
            return self.says.pop(0)
        await self.gate.wait()
        return None

    async def send(self, data):
        self.got.append(data)

    async def close(self):
        self.closed = True
        self.gate.set()


class Scripted:
    def __init__(self):
        self.opened: list[Display] = []

    async def open(self, machine):
        d = Display()
        self.opened.append(d)
        return d


@pytest.fixture
def running(box):  # noqa: F811
    box.report()
    done(box, "machine.create", VM)
    done(box, "machine.start", {"name": "win"})
    box.display = Scripted()
    box.app.state.machine_console.upstream = box.display
    box.ticket = lambda name="win": box.post(f"/v1/machines/{name}/console", headers=OWNER).json()["ticket"]
    return box


def eventually(check, seconds=2.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.01)
    return check()


def refused(c, url):
    with pytest.raises(WebSocketDisconnect) as e, c.websocket_connect(url):
        pass
    return e.value.code


def test_the_owner_opens_the_screen_and_the_ticket_works_once(running):
    t = running.ticket()
    with running.websocket_connect(f"/v1/machines/win/console/ws?ticket={t}", subprotocols=["binary"]) as ws:
        assert ws.receive_bytes() == b"RFB 003.008\n"
        ws.send_bytes(b"RFB 003.008\n")
        ws.send_bytes(struct.pack(">BBHH", 5, 0, 10, 10)[:6])  # a pointer move: an owner with hands may
    assert running.display.opened[0].got == [b"RFB 003.008\n", struct.pack(">BBHH", 5, 0, 10, 10)[:6]]
    assert eventually(lambda: running.display.opened[0].closed)  # let go in the background, after the audit line
    assert refused(running, f"/v1/machines/win/console/ws?ticket={t}") == 1008  # used already


def test_wrong_machine_expired_missing_or_cross_site_tickets_are_refused(running):
    base = "/v1/machines/win/console/ws"
    assert refused(running, base) == 1008
    assert refused(running, f"{base}?ticket=nope") == 1008
    t = running.ticket()
    assert refused(running, f"/v1/machines/other/console/ws?ticket={t}") == 1008  # bound to win, and spent
    t = running.ticket()
    running.clock.advance(61)
    assert refused(running, f"{base}?ticket={t}") == 1008
    t = running.ticket()
    with pytest.raises(WebSocketDisconnect) as e, running.websocket_connect(f"{base}?ticket={t}", headers={"origin": "https://evil.example"}):
        pass
    assert e.value.code == 1008
    assert running.display.opened == []  # nothing reached a display


def test_a_box_without_a_runtime_says_so_and_a_failing_display_is_a_plain_close(running):
    running.app.state.machine_console.upstream = None
    assert refused(running, f"/v1/machines/win/console/ws?ticket={running.ticket()}") == 1013

    class Broken:
        async def open(self, machine):
            raise OSError("no cluster")
    running.app.state.machine_console.upstream = Broken()
    assert refused(running, f"/v1/machines/win/console/ws?ticket={running.ticket()}") == 1011


def test_a_second_console_takes_over_and_the_first_is_closed(running):
    url = lambda: f"/v1/machines/win/console/ws?ticket={running.ticket()}"  # noqa: E731
    with running.websocket_connect(url()) as first:
        assert first.receive_bytes()
        with running.websocket_connect(url()) as second:
            assert second.receive_bytes()
            with pytest.raises(WebSocketDisconnect) as e:
                first.receive_bytes()
            assert e.value.code == CLOSE_SUPERSEDED
    assert running.app.state.machine_console.controlling == {}


def handshake(*msgs: bytes) -> list[bytes]:
    return [b"RFB 003.008\n", b"\x01", b"\x01", *msgs]


KEY, POINTER, CUT = struct.pack(">BBxxI", 4, 1, 65), struct.pack(">BBHH", 5, 1, 4, 4), b"\x06\0\0\0" + struct.pack(">I", 3) + b"abc"
UPDATE, ENCODINGS, PIXEL = struct.pack(">BBHHHH", 3, 0, 0, 0, 9, 9), b"\x02\0" + struct.pack(">H", 2) + struct.pack(">ii", 0, 1), b"\0" * 20


def test_view_only_drops_keys_pointer_and_clipboard_but_keeps_the_picture_flowing():
    f = ViewOnlyFilter()
    sent = b"".join(handshake(PIXEL, ENCODINGS, KEY, UPDATE, POINTER, CUT, UPDATE))
    passed = f.feed(sent)
    assert passed == b"".join(handshake(PIXEL, ENCODINGS, UPDATE, UPDATE))


def test_view_only_filter_survives_messages_split_across_frames():
    f, out = ViewOnlyFilter(), b""
    stream = b"".join(handshake(KEY, UPDATE))
    for i in range(0, len(stream), 3):
        out += f.feed(stream[i:i + 3])
    assert out == b"".join(handshake(UPDATE))


@pytest.mark.parametrize("bad", [[b"RFB 003.008\n", b"\x02"], handshake(b"\x63")])
def test_view_only_fails_closed_on_what_it_cannot_place(bad):
    with pytest.raises(ViewOnlyFilter.Refused):
        ViewOnlyFilter().feed(b"".join(bad))


def test_view_only_through_the_real_route(running):
    t = running.ticket()
    with running.websocket_connect(f"/v1/machines/win/console/ws?ticket={t}&view=1") as ws:
        ws.receive_bytes()
        for m in handshake(KEY, UPDATE):
            ws.send_bytes(m)
        ws.send_bytes(POINTER)
        ws.send_bytes(CUT)
    got = b"".join(running.display.opened[0].got)
    assert got == b"".join(handshake(UPDATE)) and KEY not in got and POINTER not in got and CUT not in got


def test_a_garbled_view_only_client_is_cut_off(running):
    t = running.ticket()
    with running.websocket_connect(f"/v1/machines/win/console/ws?ticket={t}&view=1") as ws:
        ws.receive_bytes()
        ws.send_bytes(b"RFB 003.008\n")
        ws.send_bytes(b"\x05")  # asks for a password screen: not understood, so refused
        with pytest.raises(WebSocketDisconnect):
            ws.receive_bytes()


class StubWS:
    """A browser that never reads: send_bytes blocks until the test lets go."""

    def __init__(self):
        from starlette.websockets import WebSocketState
        self.application_state, self.closed_with, self.sent = WebSocketState.CONNECTED, None, []
        self.release, self.hold = asyncio.Event(), asyncio.Event()

    async def send_bytes(self, data):
        await self.release.wait()
        self.sent.append(data)

    async def receive(self):
        await self.hold.wait()
        return {"type": "websocket.disconnect"}

    async def close(self, code=1000, reason=None):
        from starlette.websockets import WebSocketState
        self.closed_with, self.application_state = code, WebSocketState.DISCONNECTED


def test_a_client_that_cannot_keep_up_is_cut_at_the_byte_cap_not_buffered_forever():
    async def go():
        ws = StubWS()
        display = Display(says=[b"x" * 600] * 5)
        broker = ConsoleBroker(lambda t, n: {}, None, lambda *a: None, high_water=1000)
        await asyncio.wait_for(broker._pump(Session(ws, False), display), 5)
        return ws
    ws = asyncio.run(go())
    assert ws.closed_with == CLOSE_TOO_SLOW and ws.sent == []


def test_a_client_that_keeps_up_is_never_cut():
    async def go():
        ws = StubWS()
        ws.release.set()
        display = Display(says=[b"x" * 600] * 50)
        broker = ConsoleBroker(lambda t, n: {}, None, lambda *a: None, high_water=1000)
        task = asyncio.create_task(broker._pump(Session(ws, False), display))
        await asyncio.sleep(0.2)
        ws.hold.set()
        await asyncio.wait_for(task, 5)
        return ws
    ws = asyncio.run(go())
    assert ws.closed_with == 1000 and len(ws.sent) == 50


def test_audit_records_who_opened_and_closed_but_no_screen_or_keys(running):
    t = running.ticket()
    with running.websocket_connect(f"/v1/machines/win/console/ws?ticket={t}") as ws:
        ws.receive_bytes()
        ws.send_bytes(KEY)
    path = running.app.state.settings.audit_path

    def console_lines():
        return [x for x in map(json.loads, path.read_text().splitlines()) if x["event"].startswith("machines.console.")]
    assert eventually(lambda: len(console_lines()) >= 2)
    events = console_lines()
    assert [x["event"] for x in events[-2:]] == ["machines.console.opened", "machines.console.closed"]
    assert events[-2]["principal"]["role"] == "owner" and events[-2]["data"] == {"machine": "win", "view_only": False}
    assert "RFB" not in json.dumps(events) and str(KEY) not in json.dumps(events)


def test_the_kubectl_proxy_upstream_asks_kubevirts_vnc_subresource_and_cleans_up(tmp_path):
    assert vnc_url(8001, "win") == "ws://127.0.0.1:8001/apis/subresources.kubevirt.io/v1/namespaces/machines/virtualmachineinstances/win/vnc"
    silent = tmp_path / "kubectl"
    silent.write_text("#!/bin/sh\nexec sleep 30\n")
    silent.chmod(silent.stat().st_mode | stat.S_IXUSR)

    async def go(kubectl):
        with pytest.raises((RuntimeError, OSError, asyncio.TimeoutError)):
            await KubectlProxyUpstream(str(kubectl), start_timeout_s=0.5).open("win")
    asyncio.run(go(silent))
    asyncio.run(go(tmp_path / "no-such-kubectl"))
