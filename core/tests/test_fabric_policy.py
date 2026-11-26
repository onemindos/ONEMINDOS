# SPDX-License-Identifier: Apache-2.0
"""D-029 N7: the signed stop and revoke snapshot every machine keeps (fabric_policy.py).

internal/jobs/testdata/policy-vector.json is a snapshot signed here with the test-only key of the job
v2 vector; internal/jobs/policy_test.go verifies it byte for byte. internal/leaf/jobs_test.go runs the
whole path in nats-server (stop pressed while a machine is cut off: its queued job is refused on
reconnect). internal/leaf/testdata/policy-stream.golden.json is ONEMIND_POLICY as made here.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from conftest import OWNER, ScriptedExecutor
from onemind_core import fabric_policy as fp
from onemind_core.app import create_app

ROOT = Path(__file__).resolve().parents[2]
VECTOR = ROOT / "internal" / "jobs" / "testdata" / "policy-vector.json"
JOB_VECTOR = ROOT / "internal" / "backup" / "testdata" / "job-v2-vector.json"
STREAM_GOLDEN = ROOT / "internal" / "leaf" / "testdata" / "policy-stream.golden.json"
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(json.loads(JOB_VECTOR.read_text())["seed_hex"]))


def _vector_env() -> dict:
    state = fp.PolicyState(motion_lockout=True, revoked_kids=("job-00000000deadbeef",), allowed_kinds=("host.check", "relay.set"))
    return fp.sign_snapshot(_key(), "nodea", 3, state, NOW)


def test_vector_for_the_go_verifier_is_current():
    assert json.loads(VECTOR.read_text()) == {
        "$comment": "SPDX-License-Identifier: Apache-2.0. TEST-ONLY: signed with the job v2 vector's test key "
                    "(seed bytes 1..32). core/tests/test_fabric_policy.py writes it; internal/jobs/policy_test.go verifies it.",
        "node_id": "nodea", "envelope": _vector_env()}


def test_snapshot_shape_and_refusals():
    env = _vector_env()
    assert env["schema"] == "onemind.policy/v1" and env["aud"] == "node:nodea" and env["epoch"] == 3
    assert env["stop"] == {"motion_lockout": True, "agents": False} and env["kid"].startswith("job-")
    assert env["allowed_kinds"] == ["host.check", "relay.set"] and env["issued_at"] == "2026-11-25T12:00:00Z"
    for bad in ({"node_id": "Bad.Id"}, {"epoch": 0}, {"epoch": True}):
        args = {"node_id": "nodea", "epoch": 1, **bad}
        with pytest.raises(ValueError):
            fp.sign_snapshot(_key(), args["node_id"], args["epoch"], fp.PolicyState(), NOW)
    assert fp.PolicyState().body()["allowed_kinds"] is None  # no list: every kind


def test_stream_golden():
    assert json.loads(STREAM_GOLDEN.read_text()) == fp.stream_json()
    cfg = fp.stream_config()
    assert cfg.max_msgs_per_subject == 1 and cfg.allow_direct and cfg.subjects == ["onemind.node.*.policy"]


def test_epoch_rises_only_when_the_answer_changes(tmp_path):
    store = fp.EpochStore(tmp_path / "policy-epoch.json")
    calm, stop = fp.PolicyState().digest(), fp.PolicyState(motion_lockout=True).digest()
    assert store.advance(calm) == 1 and store.advance(calm) == 1
    assert store.advance(stop) == 2 and store.advance(calm) == 3  # turning it off is a new answer too
    assert fp.EpochStore(tmp_path / "policy-epoch.json").read() == (3, calm)
    assert (tmp_path / "policy-epoch.json").stat().st_mode & 0o777 == 0o600


class FakeJS:
    def __init__(self):
        self.streams, self.sent = {}, []

    async def stream_info(self, name):
        from nats.js.errors import NotFoundError

        if name not in self.streams:
            raise NotFoundError()
        return SimpleNamespace(config=self.streams[name])

    async def add_stream(self, cfg):
        self.streams[cfg.name] = cfg

    async def update_stream(self, cfg):
        self.streams[cfg.name] = cfg

    async def publish(self, subject, data, headers=None):
        self.sent.append((subject, json.loads(data), headers))


def test_publisher_republishes_every_machine_on_a_change(tmp_path):
    js, state = FakeJS(), {"s": fp.PolicyState()}
    pub = fp.PolicyPublisher(key=_key, store=fp.EpochStore(tmp_path / "e.json"), state=lambda: state["s"],
                             node_ids=lambda: ["nodea", "nodeb"], clock=lambda: NOW)
    nc = SimpleNamespace(jetstream=lambda: js)

    async def scenario():
        await pub.publish_on(nc, every=True)
        await pub.publish_on(nc)                       # nothing changed: nothing sent
        state["s"] = fp.PolicyState(agents_stopped=True)
        await pub.publish_on(nc)

    asyncio.run(scenario())
    assert "ONEMIND_POLICY" in js.streams
    assert [(s, e["epoch"], h["Nats-Msg-Id"]) for s, e, h in js.sent] == [
        ("onemind.node.nodea.policy", 1, "policy-nodea-1"), ("onemind.node.nodeb.policy", 1, "policy-nodeb-1"),
        ("onemind.node.nodea.policy", 2, "policy-nodea-2"), ("onemind.node.nodeb.policy", 2, "policy-nodeb-2")]
    assert js.sent[-1][1]["stop"] == {"motion_lockout": False, "agents": True}
    assert pub.published == {"nodea": 2, "nodeb": 2} and pub.epoch() == 2


def test_route_lockout_raises_the_epoch_jobs_carry(settings, clock):
    with TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor())) as c:
        r = c.get("/v1/fabric/policy", headers=OWNER)
        assert r.status_code == 200, r.text
        assert r.json()["schema"] == "onemind.policy/v1" and r.json()["stop"] == {"motion_lockout": False, "agents": False}
        first = r.json()["epoch"]
        assert c.put("/v1/physical/lockout", json={"locked": True}, headers=OWNER).status_code == 200
        r = c.get("/v1/fabric/policy", headers=OWNER)
        assert r.json()["stop"]["motion_lockout"] is True
        assert r.json()["epoch"] == first + 1 == c.app.state.gateway.policy.epoch()  # what a job signed now carries
        assert c.get("/v1/fabric/policy").status_code == 401


# ------------------------------------------------------------------- the NA lab's hub (test/qemu/CRITERIA-NATS.md)
NA_GOLDEN = ROOT / "internal" / "leaf" / "testdata" / "hub-accounts-na.golden.conf"
NA_PUB_A = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"   # internal/leaf goldenPubA
NA_PUB_B = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3"   # internal/leaf goldenPubB
NA_PUB_GW = "UAIETCIAFQAMTEIL47WBJYZ7OVLKMFPNIJ4P5T6XMGO7EHNVADUNJAAR"  # internal/leaf goldenPubGW


def na_accounts() -> str:
    from onemind_core import natsjwt
    from onemind_core.natsconf import CalloutAccount, NodeAccount, ServiceKey, render_accounts

    def key(n: int) -> Ed25519PrivateKey:
        return Ed25519PrivateKey.from_private_bytes(bytes([n]) * 32)

    callout = CalloutAccount(natsjwt.public_key(key(1), natsjwt.PREFIX_ACCOUNT), natsjwt.public_key(key(2), natsjwt.PREFIX_USER))
    return render_accounts([NodeAccount("aaa111", NA_PUB_A), NodeAccount("bbb222", NA_PUB_B)],
                           [ServiceKey("gateway", NA_PUB_GW)], 1 << 30, [], callout)


def test_na_lab_hub_is_what_the_gateway_writes_with_everything_on():
    text = na_accounts()
    assert NA_GOLDEN.read_text() == text
    for want in ("auth_callout", "ONEMIND_JOBS.node-aaa111", "DIRECT.GET.ONEMIND_POLICY.onemind.node.aaa111.policy",
                 f'"{NA_PUB_A}"', f'"{NA_PUB_GW}"'):
        assert want in text
