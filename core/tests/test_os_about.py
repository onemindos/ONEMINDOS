# SPDX-License-Identifier: Apache-2.0
"""About this box (UMB-P14, #432): device facts from real heartbeats, never a serial or an address.

Real gateway, real route. The heartbeat is the shape `onemindd` sends (internal/heartbeat).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app

HB = {"schema": "onemind.node.status/v1", "node_id": "box0123456789", "hostname": "beelink", "role": "hub",
      "board": "x86_64-efi", "arch": "amd64",
      "os": {"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"},
      "kernel": "6.12.48-amd64", "cpu_model": "Intel(R) N100", "cpus": 4,
      "mem_total_mb": 15800, "mem_available_mb": 9000, "disk_total_gb": 476.94, "disk_free_gb": 400.0,
      "uptime_s": 93784, "agent_version": "0.1.1",
      "rauc": {"present": True, "booted_slot": "A", "slots": [
          {"name": "rootfs.0", "bootname": "A", "state": "booted", "device": "/dev/disk/by-id/ata-SERIAL123-part2"}]},
      "update": {"channel": "security", "current_version": "0.1.1", "available_version": None, "state": "idle",
                 "last_check": None, "last_result": ""}}


@pytest.fixture
def box(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        def report(**changes):
            hb = {**HB, **changes}
            assert app.state.registry.ingest(f"onemind.node.{hb['node_id']}.status", json.dumps(hb).encode())
        c.report, c.clock = report, clock
        yield c


def test_about_reports_the_device_facts(box):
    box.report()
    r = box.get("/v1/os/about", headers=OWNER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["node_count"] == 1 and body["hub_node_id"] == box.app.state.settings.node_id
    [n] = body["nodes"]
    assert n["hostname"] == "beelink" and n["board"] == "x86_64-efi" and n["kernel"] == "6.12.48-amd64"
    assert n["os_pretty"] == "Debian GNU/Linux 13 (trixie)" and n["os_version_id"] == "13"
    assert n["onemind_version"] == "0.1.1" and n["booted_slot"] == "A" and n["status"] == "online"
    assert n["cpu_model"] == "Intel(R) N100" and n["cpus"] == 4 and n["mem_total_mb"] == 15800
    assert n["disk_total_gb"] == 476.9 and n["uptime_s"] == 93784


def test_about_needs_a_login(box):
    assert box.get("/v1/os/about").status_code == 401


def test_about_never_passes_on_a_serial_or_an_address(box):
    # The registry drops top-level serial/ip keys; nested ones and the slot device path must not leak either.
    box.report(serial="SN-777", ip="203.0.113.9", mac="aa:bb:cc:dd:ee:ff", net={"addresses": ["192.0.2.7"]},
               os={"id": "debian", "version_id": "13", "pretty": "Debian 13", "serial_number": "SN-888"})
    text = box.get("/v1/os/about", headers=OWNER).text
    for secret in ("SN-777", "SN-888", "203.0.113.9", "192.0.2.7", "aa:bb:cc", "SERIAL123"):
        assert secret not in text
    assert set(box.get("/v1/os/about", headers=OWNER).json()["nodes"][0]) <= {
        "node_id", "hostname", "role", "board", "arch", "status", "last_seen", "os_pretty", "os_id",
        "os_version_id", "onemind_version", "agent_version", "booted_slot", "kernel", "cpu_model", "cpus",
        "mem_total_mb", "mem_available_mb", "disk_total_gb", "disk_free_gb", "uptime_s"}


def test_about_rechecks_hostile_heartbeat_fields(box):
    box.report(hostname=["x"], kernel="k" * 5000, cpus=-3, mem_total_mb="lots", disk_total_gb=float("inf"),
               uptime_s=True, os="nope", update={"current_version": 7}, rauc="nope")
    [n] = box.get("/v1/os/about", headers=OWNER).json()["nodes"]
    assert n["hostname"] is None and len(n["kernel"]) == 128 and n["cpus"] is None
    assert n["mem_total_mb"] is None and n["disk_total_gb"] is None and n["uptime_s"] is None
    assert n["os_pretty"] is None and n["onemind_version"] is None and n["booted_slot"] is None


def test_hub_comes_first_and_nodes_are_counted(box):
    hub = box.app.state.settings.node_id
    box.report(node_id="aaa-first", hostname="zzz")
    box.report(node_id=hub, hostname="hubbox")
    body = box.get("/v1/os/about", headers=OWNER).json()
    assert body["node_count"] == 2 and [n["node_id"] for n in body["nodes"]] == [hub, "aaa-first"]


def test_spoofed_ids_cannot_push_real_nodes_out_of_the_list(box):
    hub = box.app.state.settings.node_id
    for i in range(100):  # a LAN device inventing ids that sort before the real ones
        box.report(node_id=f"aa-fake-{i:03}", hostname="fake")
    box.clock.advance(300)  # the fakes go offline; the real boxes keep reporting
    box.report(node_id="zz-real", hostname="real")
    box.report(node_id=hub, hostname="hubbox")
    body = box.get("/v1/os/about", headers=OWNER).json()
    ids = [n["node_id"] for n in body["nodes"]]
    assert body["node_count"] == 102 and len(ids) == 64
    assert ids[:2] == [hub, "zz-real"]  # hub first, then the online node, then the rest
