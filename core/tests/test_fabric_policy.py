# SPDX-License-Identifier: Apache-2.0
"""D-029 N7: the signed stop and revoke snapshot every machine keeps (fabric_policy.py).

internal/jobs/testdata/policy-vector.json is a snapshot signed here with the test-only key of the job
v2 vector; internal/jobs/policy_test.go verifies it byte for byte. internal/leaf/jobs_test.go runs the
whole path in nats-server (stop pressed while a machine is cut off: its queued job is refused on
reconnect). internal/leaf/testdata/policy-stream.golden.json is ONEMIND_POLICY as made here.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from conftest import OWNER, ScriptedExecutor, apply_settings_change
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

    async def purge_stream(self, name, subject=None):
        self.purged = getattr(self, "purged", []) + [(name, subject)]
        return True


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


def test_a_slow_old_publication_cannot_overwrite_a_new_stop_note(tmp_path):
    js, state = FakeJS(), {"s": fp.PolicyState()}
    pub = fp.PolicyPublisher(key=_key, store=fp.EpochStore(tmp_path / "e.json"), state=lambda: state["s"],
                             node_ids=lambda: ["nodea"], clock=lambda: NOW)
    nc = SimpleNamespace(jetstream=lambda: js)

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        publish = js.publish

        async def interleaved_publish(subject, data, headers):
            if json.loads(data)["epoch"] == 1:
                started.set()
                await release.wait()
            await publish(subject, data, headers=headers)

        js.publish = interleaved_publish
        old = asyncio.create_task(pub.publish_on(nc, every=True))
        await asyncio.wait_for(started.wait(), timeout=2)
        state["s"] = fp.PolicyState(agents_stopped=True)
        stop = asyncio.create_task(pub.publish_on(nc))
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(asyncio.gather(old, stop), timeout=2)

    asyncio.run(scenario())
    assert [env["epoch"] for _, env, _ in js.sent] == [1, 2]
    assert js.sent[-1][1]["stop"]["agents"]
    assert pub.published == {"nodea": 2}


# ------------------------------------------------------------------- #1210 review fixes
@pytest.mark.parametrize("body", ["{not json", '{"epoch": "7", "digest": "x"}', '{"epoch": 0, "digest": "x"}',
                                  '{"digest": "x"}', "[]"])
def test_a_corrupt_epoch_file_fails_loudly_and_is_never_reset(tmp_path, body):
    """#1210 review: a corrupt file used to read as epoch 1, so machines ignored every new note and
    refused every new job as stale_epoch, silently. Now it is an error everywhere, and nothing rewrites it."""
    path = tmp_path / "policy-epoch.json"
    path.write_text(body)
    store = fp.EpochStore(path)
    js = FakeJS()
    pub = fp.PolicyPublisher(key=_key, store=store, state=lambda: fp.PolicyState(motion_lockout=True),
                             node_ids=lambda: ["nodea"], clock=lambda: NOW)
    with pytest.raises(fp.EpochError):
        store.read()
    with pytest.raises(fp.EpochError):
        store.advance(fp.PolicyState().digest())
    with pytest.raises(fp.EpochError):
        pub.epoch()                                   # no job is signed with a guessed epoch
    asyncio.run(pub.publish_on(SimpleNamespace(jetstream=lambda: js), every=True))
    assert js.sent == [] and pub.error.startswith("EpochError")
    v = pub.view()
    assert v["epoch"] == 0 and v["error"].startswith("EpochError") and v["stop"]["motion_lockout"] is True
    assert path.read_text() == body                   # never reset behind the owner's back


def test_the_first_stop_on_a_fresh_box_is_epoch_2(tmp_path):
    """Jobs signed before any snapshot carry epoch 1 (backups/jobs.py POLICY_EPOCH): the very first stop
    must be a newer epoch, or those jobs would not be stale under it."""
    store = fp.EpochStore(tmp_path / "e.json")
    assert store.peek(fp.PolicyState(motion_lockout=True).digest()) == 2
    assert store.advance(fp.PolicyState(motion_lockout=True).digest()) == 2


def test_reading_the_policy_never_writes_the_epoch_file(tmp_path):
    """#1210 review: GET /v1/fabric/policy wrote the epoch file through epoch(). view() is read-only now
    and still shows the epoch a job signed now would carry."""
    path = tmp_path / "e.json"
    state = {"s": fp.PolicyState()}
    pub = fp.PolicyPublisher(key=_key, store=fp.EpochStore(path), state=lambda: state["s"],
                             node_ids=lambda: [], clock=lambda: NOW)
    assert pub.view()["epoch"] == 1 and not path.exists()
    state["s"] = fp.PolicyState(agents_stopped=True)
    assert pub.view()["epoch"] == 2 and not path.exists()
    assert pub.epoch() == 2 and path.exists()
    before = path.read_bytes()
    state["s"] = fp.PolicyState()
    assert pub.view()["epoch"] == 3 and path.read_bytes() == before
    assert pub.epoch() == 3


def test_a_stop_purges_queued_actuating_jobs_once_per_epoch(tmp_path):
    """#1210 review: a job queued before Stop must not wait in the queue for the note to win a race."""
    js, state = FakeJS(), {"s": fp.PolicyState()}
    pub = fp.PolicyPublisher(key=_key, store=fp.EpochStore(tmp_path / "e.json"), state=lambda: state["s"],
                             node_ids=lambda: ["nodea"], clock=lambda: NOW)
    nc = SimpleNamespace(jetstream=lambda: js)

    async def scenario():
        await pub.publish_on(nc, every=True)
        assert not getattr(js, "purged", [])           # no stop: nothing purged
        state["s"] = fp.PolicyState(motion_lockout=True)
        await pub.publish_on(nc)
        await pub.publish_on(nc)                      # same epoch: not purged again

    asyncio.run(scenario())
    assert js.purged == [("ONEMIND_JOBS", s) for s in fp.actuating_job_subjects()]
    assert "onemind.node.*.job.relay.>" in fp.actuating_job_subjects()
    assert "onemind.node.*.job.physical" in fp.actuating_job_subjects()


ACTUATE_GOLDEN = ROOT / "internal" / "leaf" / "testdata" / "actuating-job-subjects.golden.json"


def test_actuating_subjects_golden_for_the_na_lab():
    """NA7 (test/qemu/CRITERIA-NATS.md §3) purges ONEMIND_JOBS in nats-server with exactly these filters."""
    assert json.loads(ACTUATE_GOLDEN.read_text()) == fp.actuating_job_subjects()


def test_push_now_puts_the_notes_on_the_hub_before_it_returns(tmp_path):
    """#1210 review: the stop switch call waits until the hub holds the new note (from a worker thread,
    as a sync FastAPI route runs), instead of the next 5 s tick."""
    import threading

    from onemind_core.bus import NatsBus

    js, state = FakeJS(), {"s": fp.PolicyState()}
    pub = fp.PolicyPublisher(key=_key, store=fp.EpochStore(tmp_path / "e.json"), state=lambda: state["s"],
                             node_ids=lambda: ["nodea"], clock=lambda: NOW)
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        bus = NatsBus.__new__(NatsBus)
        bus.nc, bus._loop = SimpleNamespace(is_connected=True, jetstream=lambda: js), loop
        state["s"] = fp.PolicyState(agents_stopped=True)
        assert pub.push_now(bus) is True
        assert [(s, e["epoch"], e["stop"]["agents"]) for s, e, _ in js.sent] == [("onemind.node.nodea.policy", 2, True)]
        assert pub.published == {"nodea": 2} and js.purged
        bus.nc = SimpleNamespace(is_connected=False)
        assert pub.push_now(bus) is False             # NATS down: the caller reports it, the loop retries
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(5)


def test_stop_then_resume_during_broker_outage_still_invalidates_pre_stop_jobs(tmp_path):
    state = {"value": fp.PolicyState(agents_stopped=True)}
    store = fp.EpochStore(tmp_path / "e.json")
    pub = fp.PolicyPublisher(key=_key, store=store, state=lambda: state["value"], node_ids=lambda: ["nodea"],
                             clock=lambda: NOW)
    bus = SimpleNamespace(connected=False)
    assert pub.push_now(bus) is False
    assert store.read() == (2, state["value"].digest())
    state["value"] = fp.PolicyState()
    assert pub.push_now(bus) is False
    assert store.read() == (3, state["value"].digest())


def test_stop_switch_pushes_and_a_failed_push_is_audited(settings, clock):
    from dataclasses import replace

    with TestClient(create_app(replace(settings, nats_url="nats://127.0.0.1:1"), clock=clock,
                               executor=ScriptedExecutor())) as c:
        gw = c.app.state.gateway
        calls = []
        gw.policy.push_now = lambda bus, **options: calls.append(options.get("confirm_stop")) or False
        for path, flag in (("/v1/physical/lockout", "locked"), ("/v1/agents/kill-switch", "on")):
            response = c.put(path, json={flag: True}, headers=OWNER)
            assert response.status_code == 503, response.text
            assert response.json()["reason"] == "fabric_policy_pending"
            assert c.get(path, headers=OWNER).json()[flag] is True
        assert calls == [True, True]
    events = [json.loads(line).get("event") for line in settings.audit_path.read_text().splitlines() if line.strip()]
    assert events.count("fabric.policy.push_failed") == 2


def test_live_dispatch_reports_stop_during_publication_failure_and_waits_out_old_admission(settings, clock):
    class Connection:
        is_connected = True

        def jetstream(self):
            return js

        async def publish(self, *args, **kwargs):
            pass  # unrelated audit and event publication

        async def drain(self):
            pass

    class FailedPublication(FakeJS):
        failing = False

        async def publish(self, subject, data, headers=None):
            if self.failing:
                raise RuntimeError("cannot write policy stream")
            await super().publish(subject, data, headers)

    js = FailedPublication()
    with TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor())) as c:
        gw = c.app.state.gateway
        gw.bus.url, gw.bus.nc = "nats://configured", Connection()
        gw.policy.node_ids, gw.policy.key = lambda: ["nodea"], _key
        assert gw.policy.push_now(gw.bus)
        assert js.sent[-1][1]["stop"]["motion_lockout"] is False

        async def ask(_nc):
            answers = []

            async def respond(body):
                answers.append(json.loads(body))

            challenge = b"1" * 32
            msg = SimpleNamespace(subject="onemind.node.nodea.policycheck", data=challenge, reply="inbox", respond=respond)
            await gw.bus.policy_check(msg)
            assert len(answers) == 1
            env = answers[0]
            _key().public_key().verify(base64.b64decode(env.pop("sig")), fp.canonical(env))
            assert env["challenge"] == challenge.decode("ascii")
            return env

        path = "/v1/physical/lockout"
        js.failing = True
        response = c.put(path, json={"locked": True}, headers=OWNER)
        assert response.status_code == 503, response.text
        assert js.sent[-1][1]["epoch"] == 1  # reachable hub still returns an old permissive note
        live = gw.bus.run_threadsafe(ask, 2)
        assert live["epoch"] == 2 and live["stop"]["motion_lockout"] is True

        js.failing = False
        response = c.put(path, json={"locked": True}, headers=OWNER)
        assert response.status_code == 200, response.text
        assert js.sent[-1][1]["epoch"] == 2 and js.purged

        apply_settings_change(c, c.put(path, json={"locked": False}, headers=OWNER))
        assert gw.bus.run_threadsafe(ask, 2)["stop"]["motion_lockout"] is False
        dispatch_until = gw.policy._dispatch_until
        assert dispatch_until > time.monotonic()
        assert c.put(path, json={"locked": True}, headers=OWNER).status_code == 200
        assert time.monotonic() >= dispatch_until


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
