# SPDX-License-Identifier: Apache-2.0
"""Desktop apps from Flathub (issue #1097, D-026, D-027): real gateway, real routes, real ledger.

The one stand-in is the box side (`FlatpakHost`), which the test injects as a small recording host holding one
local list of apps; the host client is also run against a socket that speaks the Go host service's protocol
(internal/host/flatpak.go), so the paths, verbs and answers it uses are the ones the Go side serves.
"""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from files_support import audit_events
from onemind_core.app import create_app
from onemind_core.desktopapps import DesktopAppsSettings, FlatpakHostError, HostFlatpakClient

OBSIDIAN = "md.obsidian.Obsidian"
CATALOG = [{"app_id": OBSIDIAN, "name": "Obsidian", "summary": "Knowledge base", "version": "1.8.9"},
           {"app_id": "org.gimp.GIMP", "name": "GIMP", "summary": "Images", "version": "2.10"}]


class RecordingHost:
    def __init__(self):
        self.installed: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail: FlatpakHostError | None = None
        self.up = True

    def status(self):
        if not self.up:
            return False, "flatpak_unavailable", "This box cannot run desktop apps yet: no host", []
        return True, "", "", list(self.installed.values())

    def search(self, q):
        self.calls.append(("search", q))
        return [a for a in CATALOG if q.lower() in (a["name"] + a["app_id"] + a["summary"]).lower()]

    def _do(self, kind, app_id):
        if self.fail:
            raise self.fail
        self.calls.append((kind, app_id))

    def install(self, app_id):
        self._do("install", app_id)
        self.installed[app_id] = {"app_id": app_id, "name": app_id, "installed": True, "update_available": False,
                                  "folder": f"/data/onemind/desktop-apps/{app_id}/files"}

    def update(self, app_id):
        self._do("update", app_id)
        self.installed[app_id]["update_available"] = False

    def remove(self, app_id):
        self._do("remove", app_id)
        del self.installed[app_id]

    def launch(self, app_id):
        self._do("launch", app_id)


@pytest.fixture
def box(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        c.clock, c.n, c.svc = clock, 0, app.state.desktop_apps
        c.svc.host = RecordingHost()
        yield c


def ask(c, kind, app_id=OBSIDIAN, who=OWNER):
    c.n += 1
    return c.post("/v1/actions", headers=who, json={
        "type": f"desktop.app.{kind}", "params": {"app_id": app_id}, "idempotency_key": f"da{c.n}",
        "expires_at": (c.clock.now + timedelta(hours=1)).isoformat()})


def approve(c, r, who=OWNER):
    assert r.status_code == 201, r.text
    return c.post(f"/v1/actions/{r.json()['id']}/approve", headers=who)


def settled(c, r):
    """The approved action ends on a worker thread; wait for it."""
    import time
    for _ in range(100):
        a = c.get(f"/v1/actions/{r.json()['id']}", headers=OWNER).json()
        if a["state"] in ("succeeded", "failed", "outcome_unknown"):
            return a
        time.sleep(0.05)
    raise AssertionError("the action never ended")


def test_the_owner_finds_obsidian_approves_the_install_and_it_is_listed(box):
    found = box.get("/v1/desktop-apps/search?q=obsidian", headers=OWNER).json()["results"]
    assert [a["app_id"] for a in found] == [OBSIDIAN]
    r = ask(box, "install")
    assert r.json()["state"] == "awaiting_approval" and box.svc.host.installed == {}   # nothing before the approval
    assert box.post(f"/v1/actions/{r.json()['id']}/approve", headers=ADULT).status_code == 403
    assert box.svc.host.installed == {}
    approve(box, r)
    done = settled(box, r)
    assert done["state"] == "succeeded" and "sandboxed" in done["result"]["message"]
    view = box.get("/v1/desktop-apps", headers=OWNER).json()
    assert view["service"]["available"] and view["service"]["remote"] == "flathub" and view["service"]["sandbox"]
    assert [a["app_id"] for a in view["installed"]] == [OBSIDIAN]
    assert view["stream"] == {"app_id": "desktop-apps", "installed": False}


def test_update_and_remove_are_approvals_too(box):
    approve(box, ask(box, "install"))
    box.svc.host.installed[OBSIDIAN]["update_available"] = True
    up = ask(box, "update")
    approve(box, up)
    assert settled(box, up)["state"] == "succeeded" and ("update", OBSIDIAN) in box.svc.host.calls
    rm = ask(box, "remove")
    assert OBSIDIAN in box.svc.host.installed              # still there until approved
    approve(box, rm)
    assert settled(box, rm)["state"] == "succeeded" and box.svc.host.installed == {}
    assert "stays" in settled(box, rm)["result"]["message"]


def test_an_agent_may_ask_but_never_approve_and_others_are_out(box):
    r = ask(box, "install", who=AGENT)
    assert r.status_code == 201
    assert box.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
    assert box.svc.host.installed == {}
    assert ask(box, "install", who=ADULT).status_code == 403
    for who in (ADULT, AGENT):
        assert box.get("/v1/desktop-apps", headers=who).status_code == 403
        assert box.get("/v1/desktop-apps/search?q=ob", headers=who).status_code == 403
        assert box.post(f"/v1/desktop-apps/{OBSIDIAN}/launch", headers=who).status_code == 403


def test_requests_are_refused_not_filed_when_they_could_not_run(box):
    assert ask(box, "remove").json()["reason"] == "not_installed"
    assert ask(box, "update").json()["reason"] == "not_installed"
    approve(box, ask(box, "install"))
    assert ask(box, "install").json()["reason"] == "already_installed"
    assert ask(box, "update").json()["reason"] == "up_to_date"
    box.svc.host.up = False
    assert ask(box, "remove").json()["reason"] == "flatpak_unavailable"
    body = box.get("/v1/desktop-apps", headers=OWNER).json()
    assert body["service"]["available"] is False and body["service"]["reason"] == "flatpak_unavailable"
    assert box.get("/v1/desktop-apps/search?q=ob", headers=OWNER).status_code in (200, 409)


def test_an_id_that_is_not_an_application_id_never_reaches_the_host(box):
    for bad in ("obsidian", "--user", "a.b", "md.obsidian.Obsidian --system", "../x.y.z"):
        assert ask(box, "install", bad).status_code == 422
    assert box.post("/v1/desktop-apps/--user/launch", headers=OWNER).status_code == 404
    assert box.svc.host.calls == []


def test_a_stale_card_is_refused_at_approval(box):
    r = ask(box, "install")
    box.svc.host.installed[OBSIDIAN] = {"app_id": OBSIDIAN}   # installed by other means meanwhile
    assert approve(box, r).status_code == 409 and ("install", OBSIDIAN) not in box.svc.host.calls


def test_a_host_failure_ends_the_action_failed_with_the_reason(box):
    r = ask(box, "install")
    box.svc.host.fail = FlatpakHostError("host_error", "The host service could not do it; see the box's journal.")
    approve(box, r)
    done = settled(box, r)
    assert done["state"] == "failed" and "journal" in done["result"]["message"]
    assert box.svc.host.installed == {}


def test_launch_needs_an_installed_app_and_separate_owner_approval(box, settings):
    r = box.post(f"/v1/desktop-apps/{OBSIDIAN}/launch", headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "not_installed"
    install = ask(box, "install")
    approve(box, install)
    assert settled(box, install)["state"] == "succeeded"
    path = f"/v1/desktop-apps/{OBSIDIAN}/launch"
    headers = {**OWNER, "Idempotency-Key": "launch-once"}
    request = box.post(path, headers=headers)
    assert request.status_code == 202 and request.json()["state"] == "awaiting_approval"
    assert request.json()["type"] == "desktop.app.launch"
    action_path = request.headers["location"]
    replay = box.post(path, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == request.json()["id"]
    assert box.post(f"{action_path}/approve", headers=AGENT).status_code == 403
    assert ("launch", OBSIDIAN) not in box.svc.host.calls
    assert box.post(f"{action_path}/approve", headers=OWNER).status_code == 200
    assert settled(box, request)["state"] == "succeeded"
    assert box.svc.host.calls.count(("launch", OBSIDIAN)) == 1
    assert "desktopapp.launched" in [e["event"] for e in audit_events(settings)]


def test_the_host_client_speaks_the_host_protocol():
    short = Path(tempfile.mkdtemp(prefix="om", dir="/tmp"))  # a Unix socket path is limited to about 100 bytes
    sock = str(short / "host.sock")
    seen: list[tuple[str, str]] = []
    answers = [(200, {"available": False, "unavailable_reason": "Flatpak is not installed", "installed": []}),
               (200, {"available": True, "unavailable_reason": None, "installed": [{"app_id": OBSIDIAN}]}),
               (200, {"results": CATALOG}), (200, {"ok": "true"}), (409, {"error": "refused", "reason": "not_installed", "message": "x"}),
               (200, {"ok": "true"}), (500, {"error": "internal", "reason": "flatpak_update", "message": "x"}), (200, {"ok": "true"})]
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(sock)
    srv.listen(8)

    def serve():
        for status, doc in answers:
            c, _ = srv.accept()
            data = b""
            while b"\r\n\r\n" not in data:
                data += c.recv(65536)
            seen.append(tuple(data.split(b"\r\n")[0].decode().split()[:2]))
            body = json.dumps(doc).encode()
            c.sendall(b"HTTP/1.1 %d X\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
                      % (status, len(body)) + body)
            c.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    host = HostFlatpakClient(DesktopAppsSettings(host_socket=short / "host.sock", host_timeout_s=5, read_timeout_s=5))
    ok, reason, msg, _ = host.status()
    assert not ok and reason == "flatpak_unavailable" and "Flatpak is not installed" in msg
    ok, _, _, apps = host.status()
    assert ok and apps == [{"app_id": OBSIDIAN}]
    assert host.search("obs idian")[0]["app_id"] == OBSIDIAN
    host.install(OBSIDIAN)
    with pytest.raises(FlatpakHostError) as e:
        host.remove(OBSIDIAN)
    assert e.value.reason == "not_installed"
    host.launch(OBSIDIAN)
    with pytest.raises(FlatpakHostError) as e2:
        host.update(OBSIDIAN)
    assert e2.value.reason == "host_error"
    host.remove(OBSIDIAN)
    t.join(5)
    srv.close()
    shutil.rmtree(short, ignore_errors=True)
    assert seen == [("GET", "/v1/flatpak"), ("GET", "/v1/flatpak"), ("GET", "/v1/flatpak/search?q=obs%20idian"),
                    ("POST", f"/v1/flatpak/apps/{OBSIDIAN}/install"), ("DELETE", f"/v1/flatpak/apps/{OBSIDIAN}"),
                    ("POST", f"/v1/flatpak/apps/{OBSIDIAN}/launch"), ("POST", f"/v1/flatpak/apps/{OBSIDIAN}/update"),
                    ("DELETE", f"/v1/flatpak/apps/{OBSIDIAN}")]


def test_no_socket_means_unavailable_with_a_reason(tmp_path):
    ok, reason, msg, _ = HostFlatpakClient(DesktopAppsSettings(host_socket=tmp_path / "none.sock")).status()
    assert (ok, reason) == (False, "flatpak_unavailable") and "host service" in msg
