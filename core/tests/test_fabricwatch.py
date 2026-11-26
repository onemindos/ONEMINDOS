# SPDX-License-Identifier: Apache-2.0
"""#620 (NATS plan N3): the system-account observer. natsconf renders SYS and its one read-only user;
fabricwatch turns the server's connect, disconnect and auth-error announcements into `fabric.*` audit
lines and alerts; GET /v1/fabric/events reads them back. The last class runs a real nats-server (skipped
without one on PATH) and proves the announcements arrive, the observer cannot publish and no other user
can read `$SYS`."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import ADULT, AGENT, OWNER, Clock

from onemind_core import fabricwatch, natsconf
from onemind_core.bus import SeedClient
from onemind_core.fabricwatch import FabricWatch, SeenKeys, parse
from onemind_core.natsconf import NodeAccount, ServiceKey, new_user_key, render_accounts
from onemind_core.store import Database

OBS = new_user_key()[1]
GW = new_user_key()[1]
NODE_KEY = new_user_key()[1]
GONE = new_user_key()[1]
STRANGER = new_user_key()[1]


def body(user: str = "", kind: str = "Client", name: str = "", reason: str = "", acc: str | None = None) -> bytes:
    client = {"host": "203.0.113.9", "id": 7, "user": user, "name": name, "kind": kind}
    if acc:
        client["acc"] = acc
    return json.dumps({"server": {"name": "hub"}, "client": client, "reason": reason}).encode()


AUTH = "$SYS.SERVER.NSRV123.CLIENT.AUTH.ERR"


# ---- natsconf: the SYS account -------------------------------------------------------------------
class TestRender:
    def test_observer_gets_the_sys_account_and_is_not_a_hub_user(self):
        out = render_accounts([], [ServiceKey("gateway", GW), ServiceKey("observer", OBS)])
        assert "system_account: SYS" in out
        hub = out.split("  SYS: {")[0]
        assert OBS not in hub and GW in hub
        sys_block = out.split("  SYS: {")[1]
        assert OBS in sys_block and 'publish: {deny: [">"]}' in sys_block
        for subject in natsconf.OBSERVER_SUBJECTS:
            assert f'"{subject}"' in sys_block
        assert sys_block.count("nkey:") == 1   # no other user can ever read $SYS

    def test_without_an_observer_the_file_has_no_system_account(self):
        out = render_accounts([NodeAccount("a1", NODE_KEY)], [ServiceKey("gateway", GW)])
        assert "SYS" not in out and "system_account" not in out

    def test_an_observer_alone_does_not_lock_the_loopback_user_out(self):
        out = render_accounts([], [ServiceKey("observer", OBS)])
        assert f'no_auth_user: "{natsconf.HUB_LOCAL_USER}"' in out and "system_account: SYS" in out


# ---- parse ---------------------------------------------------------------------------------------
class TestParse:
    def test_connect_leaf_disconnect_and_auth_error(self):
        c = parse("$SYS.ACCOUNT.NODE_a1.CONNECT", body(NODE_KEY, "Leafnode", "leaf"))
        assert c == {"event": "fabric.connect", "account": "NODE_a1", "key": NODE_KEY, "client": "leaf",
                     "name": "leaf", "reason": ""}
        d = parse("$SYS.ACCOUNT.ONEMIND.DISCONNECT", body(GW, name="onemind-gateway", reason="Client Closed"))
        assert d["event"] == "fabric.disconnect" and d["reason"] == "Client Closed" and d["client"] == "client"
        a = parse(AUTH, body(STRANGER, reason="Authentication Failure"))
        assert a["event"] == "fabric.auth_failed" and a["account"] is None and a["key"] == STRANGER

    def test_a_user_name_or_token_is_never_kept_as_a_key(self):
        assert parse(AUTH, body("hunter2"))["key"] == ""
        assert parse(AUTH, body("[REDACTED]"))["key"] == ""

    def test_no_address_in_the_result(self):
        assert "203.0.113.9" not in json.dumps(parse(AUTH, body(STRANGER)))

    @pytest.mark.parametrize("subject,data", [
        ("$SYS.ACCOUNT.A.SERVER.CONNS", b"{}"), ("$SYS.SERVER.X.STATSZ", b"{}"), ("onemind.audit", b"{}"),
        ("$SYS.ACCOUNT.A.CONNECT", b"not json"), ("$SYS.ACCOUNT.A.CONNECT", b"[]"),
        ("$SYS.ACCOUNT.A.CONNECT", b'{"client": 3}'), ("$SYS.ACCOUNT.A.CONNECT", b" " * 20000),
    ])
    def test_other_or_malformed_announcements_are_ignored(self, subject, data):
        assert parse(subject, data) is None

    def test_odd_characters_in_a_name_are_dropped(self):
        assert parse(AUTH, body(STRANGER, name="x\n\x1b[31m<b>y"))["name"] == "x31mby"


# ---- FabricWatch ---------------------------------------------------------------------------------
class Audit:
    def __init__(self):
        self.lines: list[tuple[str, dict]] = []

    def append(self, event, principal, action_id, data):
        self.lines.append((event, data))


@pytest.fixture
def watch(tmp_path):
    from onemind_core.ledger import Base, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'w.db'}")
    Base.metadata.create_all(engine)
    clock = Clock()
    audit, alerts = Audit(), []
    ids = {GW: "service:gateway", NODE_KEY: "node:a1"}
    w = FabricWatch(url=None, seed=None, audit=audit,
                    publish_event=lambda d, n, p, **kw: alerts.append((f"{d}.{n}", p, kw)),
                    identities=lambda: ids, seen=SeenKeys(Database(engine)), clock=clock)
    w.audit_lines, w.alerts, w.clock_obj, w.ids = audit.lines, alerts, clock, ids
    return w


def types(w):
    return [t for t, _ in w.audit_lines]


class TestWatch:
    def test_connect_and_disconnect_become_audit_lines_with_the_identity(self, watch):
        watch.handle("$SYS.ACCOUNT.NODE_a1.CONNECT", body(NODE_KEY, "Leafnode"))
        watch.clock_obj.advance(10)
        watch.handle("$SYS.ACCOUNT.NODE_a1.DISCONNECT", body(NODE_KEY, "Leafnode", reason="Client Closed"))
        assert types(watch) == ["fabric.connect", "fabric.disconnect"]
        assert watch.audit_lines[0][1] == {"account": "NODE_a1", "key": NODE_KEY, "identity": "node:a1", "client": "leaf"}
        assert watch.audit_lines[1][1]["reason"] == "Client Closed"
        assert watch.alerts == []

    def test_a_refused_sign_in_is_not_also_a_disconnect(self, watch):
        # nats-server 2.15.3 sends both the auth-error and a DISCONNECT (account $G) for the same refusal
        assert watch.handle("$SYS.ACCOUNT.$G.DISCONNECT", body(STRANGER, reason="Authentication Failure")) is None
        assert watch.audit_lines == []

    def test_the_observers_own_sign_in_is_not_logged(self, watch):
        assert watch.handle("$SYS.ACCOUNT.SYS.CONNECT", body(OBS)) is None
        assert watch.audit_lines == []

    def test_an_unknown_key_is_audited_and_raises_one_alert(self, watch):
        watch.handle(AUTH, body(STRANGER, reason="Authentication Failure"))
        assert watch.audit_lines[0][0] == "fabric.auth_failed" and watch.audit_lines[0][1]["cause"] == "unknown_key"
        assert [a[0] for a in watch.alerts] == ["fabric.unknown_key"]
        assert watch.alerts[0][2] == {"severity": "warning", "dedupe_key": f"fabric:unknown:{STRANGER}"}
        watch.clock_obj.advance(61)
        watch.handle(AUTH, body(STRANGER))
        assert len(watch.alerts) == 1   # the same key does not alert twice

    def test_no_key_at_all_is_an_unknown_key(self, watch):
        watch.handle(AUTH, body(""))
        assert watch.audit_lines[0][1]["cause"] == "unknown_key"
        assert watch.alerts[0][2]["dedupe_key"] == "fabric:unknown:none"

    def test_a_removed_key_still_retrying_is_a_revoked_alert(self, watch):
        watch.ids[GONE] = "node:gone"
        watch.handle("$SYS.ACCOUNT.NODE_gone.CONNECT", body(GONE, "Leafnode"))   # it signed in once
        del watch.ids[GONE]                                                       # then was removed
        watch.clock_obj.advance(60)
        watch.handle(AUTH, body(GONE, "Leafnode"))
        assert watch.audit_lines[-1][1]["cause"] == "revoked_key"
        assert [a[0] for a in watch.alerts] == ["fabric.revoked_retry"]
        assert watch.alerts[0][1]["who"] == "node:gone"

    def test_a_listed_key_that_is_refused_is_audited_and_alerts(self, watch):
        # nats-server reports the key the client CLAIMED, signature checked or not: a process that presents
        # another live identity's public key (public keys are readable on the box) looks exactly like this
        watch.handle(AUTH, body(NODE_KEY, "Client"))
        assert watch.audit_lines[0][1]["cause"] == "known_key"
        assert [a[0] for a in watch.alerts] == ["fabric.key_refused"]
        assert watch.alerts[0][1]["who"] == "node:a1" and watch.alerts[0][2]["dedupe_key"] == f"fabric:refused:{NODE_KEY}"
        watch.clock_obj.advance(120)
        watch.handle(AUTH, body(NODE_KEY, "Client"))
        assert len(watch.alerts) == 1   # one open alert per key, not one per retry

    def test_concurrent_announcements_do_not_corrupt_the_bookkeeping(self, watch):
        import threading

        keys = [new_user_key()[1] for _ in range(40)]
        errors: list[BaseException] = []

        def hammer(offset: int):
            try:
                for i in range(300):
                    watch.handle(AUTH, body(keys[(i + offset) % 40]))
                    watch.handle("$SYS.ACCOUNT.NODE_a1.CONNECT", body(keys[(i * 7 + offset) % 40], "Leafnode"))
                    watch.tick()
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=hammer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(watch._recent) <= fabricwatch.RECENT

    def test_a_failed_subscribe_closes_that_connection_and_keeps_the_state_honest(self, watch, monkeypatch):
        made = []

        class Fake:
            closed = 0

            def __init__(self):
                made.append(self)

            async def connect(self, *a, **kw):
                self.kw = kw

            async def subscribe(self, *a, **kw):
                raise RuntimeError("no permission")

            async def close(self):
                Fake.closed += 1

            async def drain(self):
                Fake.closed += 1

        monkeypatch.setattr(fabricwatch, "SeedClient", Fake)
        monkeypatch.setattr(fabricwatch, "RETRY_S", 0.01)
        watch.url, watch.seed = "nats://x", "seed"

        async def go():
            watch._stop = asyncio.Event()
            task = asyncio.create_task(watch._run())
            await asyncio.sleep(0.15)
            assert watch.state == "connecting"
            watch._stop.set()
            await task

        asyncio.run(go())
        assert len(made) >= 2 and Fake.closed == len(made)   # every attempt's client was closed
        assert {"disconnected_cb", "reconnected_cb"} <= set(made[0].kw)
        asyncio.run(watch._up())
        assert watch.state == "watching"
        asyncio.run(watch._down())
        assert watch.state == "connecting"

    def test_a_retry_every_second_writes_one_line_a_minute_and_counts_the_rest(self, watch):
        for _ in range(61):
            watch.handle(AUTH, body(STRANGER))
            watch.clock_obj.advance(1)
        assert types(watch).count("fabric.auth_failed") == 2
        assert watch.audit_lines[1][1]["repeats"] == 59

    def test_a_spoofer_inventing_keys_cannot_flood_the_audit_log_or_the_inbox(self, watch):
        for _ in range(200):
            watch.handle(AUTH, body(new_user_key()[1]))
        assert types(watch).count("fabric.auth_failed") == fabricwatch.AUTH_LINES_PER_MIN
        assert len(watch.alerts) == fabricwatch.ALERTS_PER_WINDOW

    def test_five_connects_in_two_minutes_is_flapping_and_it_clears_when_quiet(self, watch):
        for _ in range(5):
            watch.handle("$SYS.ACCOUNT.NODE_a1.CONNECT", body(NODE_KEY, "Leafnode"))
            watch.clock_obj.advance(10)
        flaps = [a for a in watch.alerts if a[0] == "fabric.flapping"]
        assert len(flaps) == 1 and flaps[0][2]["dedupe_key"] == f"fabric:flap:{NODE_KEY}"
        assert flaps[0][1]["who"] == "node:a1" and flaps[0][1]["connects"] == 5
        watch.tick()
        assert [a[0] for a in watch.alerts] == ["fabric.flapping"]   # not yet quiet
        watch.clock_obj.advance(fabricwatch.FLAP_QUIET_S)
        watch.tick()
        assert watch.alerts[-1][0] == "fabric.flap_cleared" and watch.alerts[-1][2]["dedupe_key"] == f"fabric:flap:{NODE_KEY}"

    def test_a_steady_machine_is_not_flapping(self, watch):
        for _ in range(8):
            watch.handle("$SYS.ACCOUNT.NODE_a1.CONNECT", body(NODE_KEY, "Leafnode"))
            watch.clock_obj.advance(300)
        assert watch.alerts == []

    def test_state_is_off_without_an_observer_key(self, watch):
        assert watch.state == "off"
        asyncio.run(watch.start())
        assert watch._task is None


# ---- the alerts reach the inbox ------------------------------------------------------------------
def test_the_catalogue_knows_the_fabric_events():
    from onemind_core.notify import catalogue

    for t in ("fabric.unknown_key", "fabric.revoked_retry", "fabric.key_refused", "fabric.flapping"):
        spec = catalogue.lookup(t)
        assert spec.kind == "open" and spec.topic == "security" and spec.severity == "warning"
    assert catalogue.lookup("fabric.flap_cleared").resolves == ("fabric:flap:{key}",)
    # the dedupe keys the watcher sends are the ones the specs render, so a clear finds its alert
    key = new_user_key()[1]
    assert catalogue.render(catalogue.lookup("fabric.flapping").dedupe, {"key": key}) == f"fabric:flap:{key}"


# ---- the route -----------------------------------------------------------------------------------
class TestRoute:
    def lines(self, client, n):
        audit = client.app.state.audit
        for i in range(n):
            audit.append("fabric.connect", None, None, {"account": "NODE_a1", "key": NODE_KEY, "identity": "node:a1",
                                                       "client": "leaf", "repeats": i or None})
        audit.append("fabric.auth_failed", None, None, {"key": STRANGER, "cause": "unknown_key", "reason": "Authentication Failure"})
        audit.append("gateway.something", None, None, {})

    def test_owner_reads_the_newest_bus_events_first(self, client):
        self.lines(client, 3)
        r = client.get("/v1/fabric/events?count=3", headers=OWNER)
        assert r.status_code == 200
        j = r.json()
        assert j["observer"] == "off"
        assert [e["event"] for e in j["events"]] == ["fabric.auth_failed", "fabric.connect", "fabric.connect"]
        assert j["events"][0]["cause"] == "unknown_key" and j["events"][1]["identity"] == "node:a1"
        assert j["events"][0]["seq"] > j["events"][1]["seq"]

    def test_the_audit_log_is_read_once_then_new_events_come_from_memory(self, client, monkeypatch):
        from onemind_core.routers import fabric_events

        self.lines(client, 2)
        reads = []
        real = fabric_events.iter_all_records
        monkeypatch.setattr(fabric_events, "iter_all_records", lambda *a, **k: reads.append(1) or real(*a, **k))
        first = client.get("/v1/fabric/events", headers=OWNER).json()["events"]
        client.app.state.fabric_watch.handle("$SYS.ACCOUNT.NODE_a1.DISCONNECT", body(NODE_KEY, "Leafnode", reason="Client Closed"))
        again = client.get("/v1/fabric/events", headers=OWNER).json()["events"]
        client.get("/v1/fabric/events", headers=OWNER)
        assert len(reads) == 1
        assert again[0]["event"] == "fabric.disconnect" and again[1:] == first and len({e["seq"] for e in again}) == len(again)

    def test_only_fabric_bus_events_are_listed(self, client):
        self.lines(client, 1)
        events = client.get("/v1/fabric/events", headers=OWNER).json()["events"]
        assert {e["event"] for e in events} <= set(fabricwatch.EVENTS) and len(events) == 2

    def test_an_adult_may_read_an_agent_may_not(self, client):
        assert client.get("/v1/fabric/events", headers=ADULT).status_code == 200
        assert client.get("/v1/fabric/events", headers=AGENT).status_code == 403
        assert client.get("/v1/fabric/events").status_code == 401

    def test_count_is_bounded(self, client):
        assert client.get("/v1/fabric/events?count=0", headers=OWNER).status_code == 422
        assert client.get("/v1/fabric/events?count=201", headers=OWNER).status_code == 422


# ---- a real nats-server --------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("nats-server") is None, reason="needs nats-server on PATH")
class TestRealServer:
    def test_announcements_arrive_the_observer_cannot_publish_and_nobody_else_reads_sys(self, tmp_path):
        import socket

        import nats

        keys = tmp_path / "keys"
        for name in ("gateway", "observer"):
            natsconf.make_service_key(keys, name)
        acc = tmp_path / "accounts.conf"
        natsconf.write_accounts(acc, [], natsconf.load_service_keys(keys))
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        conf = tmp_path / "nats.conf"
        conf.write_text(f'listen: 127.0.0.1:{port}\nserver_name: t\ninclude "accounts.conf"\n')
        proc = subprocess.Popen(["nats-server", "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        url = f"nats://127.0.0.1:{port}"
        try:
            for _ in range(50):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                    break
                except OSError:
                    time.sleep(0.1)
            got: list[tuple[str, dict]] = []
            audit = Audit()
            seen_keys = []
            w = FabricWatch(url=url, seed=keys / "observer.nk", audit=audit,
                            publish_event=lambda d, n, p, **kw: got.append((f"{d}.{n}", p)),
                            identities=lambda: {natsconf.load_seed(keys / "gateway.nk")[0]: "service:gateway"},
                            seen=type("S", (), {"note": lambda self, *a: seen_keys.append(a[0]),
                                                "get": lambda self, k: None})(), clock=lambda: datetime.now(UTC))

            async def run():
                await w.start()
                for _ in range(50):
                    if w.state == "watching":
                        break
                    await asyncio.sleep(0.1)
                assert w.state == "watching"
                # a good client, a stranger, and a client with no key
                nc = SeedClient()
                await nc.connect(url, nkeys_seed=str(keys / "gateway.nk"), name="onemind-gateway", allow_reconnect=False)
                await nc.close()
                for kw in ({"nkeys_seed": str(self.stranger(tmp_path))}, {}):
                    bad = SeedClient()
                    with pytest.raises(Exception):  # noqa: B017 (nats-py raises its own auth error type)
                        await bad.connect(url, connect_timeout=2, allow_reconnect=False, max_reconnect_attempts=0, **kw)
                    await bad.close()
                for _ in range(50):
                    if {"fabric.connect", "fabric.disconnect", "fabric.auth_failed"} <= {t for t, _ in audit.lines}:
                        break
                    await asyncio.sleep(0.1)
                # the observer cannot publish: the server refuses and reports a permissions error
                errs = []
                obs = SeedClient()

                async def on_err(e):
                    errs.append(str(e))
                await obs.connect(url, nkeys_seed=str(keys / "observer.nk"), error_cb=on_err, allow_reconnect=False)
                await obs.publish("$SYS.REQ.SERVER.PING", b"")
                await obs.publish("onemind.audit", b"{}")
                await obs.flush()
                await asyncio.sleep(0.3)
                await obs.close()
                assert errs and all("ermission" in e for e in errs)
                # a hub-account client cannot read $SYS (it is another account; nothing is delivered)
                hub = SeedClient()
                await hub.connect(url, nkeys_seed=str(keys / "gateway.nk"), allow_reconnect=False)
                sub = await hub.subscribe("$SYS.>")
                await hub.flush()
                other = SeedClient()
                await other.connect(url, nkeys_seed=str(keys / "gateway.nk"), allow_reconnect=False)   # a real CONNECT
                await other.close()
                with pytest.raises(nats.errors.TimeoutError):
                    await sub.next_msg(timeout=0.5)
                await hub.close()
                await w.stop()

            asyncio.run(run())
            events = {t: d for t, d in audit.lines}
            assert events["fabric.connect"]["identity"] == "service:gateway"
            assert events["fabric.disconnect"]["key"] == natsconf.load_seed(keys / "gateway.nk")[0]
            assert events["fabric.auth_failed"]["cause"] == "unknown_key"
            assert "127.0.0.1" not in json.dumps(audit.lines)
            # a refused sign-in is reported once, as auth_failed, not also as a disconnect
            assert sum(1 for t, d in audit.lines if t == "fabric.disconnect") == 1
            assert all(d.get("account") != "$G" for _, d in audit.lines)
            assert sum(1 for t, _ in audit.lines if t == "fabric.auth_failed") >= 1
            assert any(t == "fabric.unknown_key" for t, _ in got)
        finally:
            proc.terminate()
            proc.wait(5)

    @staticmethod
    def stranger(tmp_path: Path) -> Path:
        seed, _ = new_user_key()
        p = tmp_path / "stranger.nk"
        p.write_text(seed + "\n")
        return p
