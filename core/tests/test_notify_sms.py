# SPDX-License-Identifier: Apache-2.0
"""SMS alert channel through a provider-neutral adapter (issue #869).

Every send goes to a fake provider on loopback (an owner may point a channel at the LAN); no
real provider, no provider SDK. Phone numbers are from the +1 555 01xx range kept for fiction
and are built at runtime.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import replace
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.notify import NotifySettings
from onemind_core.notify.channels import DeliveryError, Message

PHONE = "+1" + "555" + "0100" + "123"
SENDER = "+1" + "555" + "0100" + "999"
TOKEN = "sk_test_" + "q" * 24


class FakeProvider:
    """A pretend SMS provider: records each POST, answers `status` with `reply`, after `delay` s."""

    def __init__(self):
        self.requests: list[dict] = []
        self.status = 200
        self.reply: bytes = b'{"id":"msg_0001","status":"queued"}'
        self.delay = 0.0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                outer.requests.append({"path": self.path, "headers": dict(self.headers.items()), "body": body})
                if outer.delay:
                    time.sleep(outer.delay)
                try:
                    self.send_response(outer.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(outer.reply)))
                    self.end_headers()
                    self.wfile.write(outer.reply)
                except OSError:  # the client gave up (timeout test)
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/messages"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def provider():
    p = FakeProvider()
    yield p
    p.close()


@pytest.fixture
def nclient(settings, clock, executor, tmp_path):
    s = replace(settings, sections={"notify": NotifySettings(worker=False, dir=tmp_path / "keys")})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


def svc(c):
    return c.app.state.notify


def publish(c, domain, name, data, severity="info"):
    c.app.state.events.publish_event(domain, name, data, severity=severity)


def add_sms(c, provider, headers=OWNER, secret=TOKEN, **config):
    body = {"kind": "sms", "label": "my phone", "config": {"url": provider.url, "to": PHONE, **config}}
    if secret:
        body["secret"] = secret
    r = c.post("/v1/notifications/channels", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def route_everything(c, channel_id):
    r = c.put("/v1/notifications/preferences", headers=OWNER,
              json={"routes": [{"match": {}, "channels": [channel_id]}]})
    assert r.status_code == 200, r.text


def message(**kw):
    base = dict(id="ntf_1", severity="warning", topic="nodes", title="beelink is offline",
                body="secret-file.txt went missing", link="https://box.example/alerts/1",
                created_at="2026-11-22T00:00:00Z", box_id="box")
    return Message(**{**base, **kw})


# ---- adapter contract (fake provider) ------------------------------------------------------

def test_adapter_send_ok_returns_the_provider_receipt(provider):
    from onemind_core.notify import sms

    cfg = sms.validate_config({"url": provider.url, "to": PHONE})
    receipt = sms.send(cfg, TOKEN, "title", message(), timeout=5, lan_ok=True)
    assert receipt.status == 200 and receipt.provider_id == "msg_0001"
    [req] = provider.requests
    assert req["path"] == "/v1/messages"
    assert req["headers"]["Authorization"] == "Bearer " + TOKEN
    doc = json.loads(req["body"])
    assert doc["to"] == PHONE
    assert doc["text"].startswith("OneMind: [warning] beelink is offline")
    assert "secret-file" not in doc["text"]          # never the body (file names, details)
    assert "box.example" not in doc["text"]          # title level: a hint, not the link
    assert len(doc["text"]) <= sms.MAX_TEXT


@pytest.mark.parametrize("status,error", [(400, "HTTP 400"), (401, "HTTP 401"), (503, "HTTP 503")])
def test_adapter_provider_errors_are_plain_delivery_errors(provider, status, error):
    from onemind_core.notify import sms

    provider.status = status
    provider.reply = json.dumps({"error": "bad", "echo": TOKEN}).encode()
    cfg = sms.validate_config({"url": provider.url, "to": PHONE})
    with pytest.raises(DeliveryError) as exc:
        sms.send(cfg, TOKEN, "title", message(), timeout=5, lan_ok=True)
    assert str(exc.value) == error and TOKEN not in str(exc.value)


def test_adapter_timeout_is_a_delivery_error(provider):
    from onemind_core.notify import sms

    provider.delay = 1.5
    cfg = sms.validate_config({"url": provider.url, "to": PHONE})
    start = time.monotonic()
    with pytest.raises(DeliveryError) as exc:
        sms.send(cfg, TOKEN, "title", message(), timeout=0.3, lan_ok=True)
    assert "timed out" in str(exc.value)
    assert time.monotonic() - start < 1.4


def test_adapter_form_fields_and_basic_auth_need_no_code_per_provider(provider):
    from onemind_core.notify import sms

    cfg = sms.validate_config({"url": provider.url, "to": PHONE, "from": SENDER, "format": "form",
                               "auth": "basic", "username": "acct-1",
                               "fields": {"to": "To", "from": "From", "text": "Body"}})
    provider.reply = b'{"sid":"SM0002"}'
    assert sms.send(cfg, TOKEN, "full", message(), timeout=5, lan_ok=True).provider_id == "SM0002"
    [req] = provider.requests
    assert req["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert req["headers"]["Authorization"] == "Basic " + base64.b64encode(f"acct-1:{TOKEN}".encode()).decode()
    form = parse_qs(req["body"].decode())
    assert form["To"] == [PHONE] and form["From"] == [SENDER]
    assert form["Body"][0].endswith("https://box.example/alerts/1")   # full level: the link
    assert "secret-file" not in form["Body"][0]


def test_adapters_are_a_registry_and_an_unknown_one_is_refused():
    from onemind_core.notify import sms

    assert "https" in sms.ADAPTERS
    with pytest.raises(ValueError):
        sms.validate_config({"url": "https://sms.example/send", "to": PHONE, "adapter": "nope"})
    for bad in ({"url": "https://sms.example/send", "to": "5550100"},           # not E.164
                {"url": "ftp://sms.example/", "to": PHONE},
                {"url": "https://sms.example/send", "to": PHONE, "daily_cap": 0},
                {"url": "https://sms.example/send", "to": PHONE, "daily_cap": True},
                {"url": "https://sms.example/send", "to": PHONE, "auth": "basic"},  # needs username
                {"url": "https://sms.example/send", "to": PHONE, "fields": {"to": "a b"}},
                {"url": "https://sms.example/send", "to": PHONE, "min_severity": "loud"}):
        with pytest.raises(ValueError):
            sms.validate_config(bad)


# ---- the channel through the gateway ---------------------------------------------------------

def test_add_sms_channel_defaults_and_validation(nclient, provider):
    ch = add_sms(nclient, provider)
    assert ch["kind"] == "sms" and ch["content_level"] == "title" and ch["secret"] == "provided"
    assert ch["config"]["daily_cap"] == 20 and ch["config"]["min_severity"] == "warning"
    assert ch["config"]["to"] == PHONE
    r = nclient.post("/v1/notifications/channels", headers=OWNER,
                     json={"kind": "sms", "label": "x", "config": {"url": provider.url, "to": "12345"}})
    assert r.status_code == 422
    r = nclient.post("/v1/notifications/channels", headers=GUEST,   # a guest may not aim at the LAN
                     json={"kind": "sms", "label": "x", "config": {"url": provider.url, "to": PHONE}})
    assert r.status_code == 422
    r = nclient.post("/v1/notifications/channels", headers=OWNER,
                     json={"kind": "sms", "label": "x", "config": {"url": provider.url, "to": PHONE, "daily_cap": 501}})
    assert r.status_code == 422


def test_credentials_never_appear_in_listing_logs_or_audit(nclient, provider, caplog):
    caplog.set_level(logging.DEBUG)
    ch = add_sms(nclient, provider)
    listing = nclient.get("/v1/notifications/channels", headers=OWNER).json()
    assert TOKEN not in json.dumps(listing)
    assert "secret" not in listing[0]["config"] and listing[0]["secret"] == "provided"
    route_everything(nclient, ch["id"])
    publish(nclient, "node", "offline", {"node_id": "n1", "hostname": "beelink", "age_s": 300}, "warning")
    provider.status = 500
    svc(nclient).pump()
    nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=OWNER)
    assert len(provider.requests) == 2
    assert TOKEN not in caplog.text
    audit = nclient.app.state.settings.audit_path.read_text()
    assert TOKEN not in audit and PHONE not in audit
    row = svc(nclient).repo.get_channel(ch["id"])
    assert TOKEN not in row.config_json and TOKEN not in (row.secret_enc or "")


def test_an_alert_at_the_channel_level_sends_exactly_once_and_below_never(nclient, provider, clock):
    ch = add_sms(nclient, provider, per_hour=60)
    route_everything(nclient, ch["id"])
    s = svc(nclient)
    publish(nclient, "update", "applied", {"node_id": "n1", "hostname": "pi", "version": "1.2"})   # info
    assert s.pump() == 0 and provider.requests == []                                             # below: never
    data = {"node_id": "n1", "hostname": "beelink", "age_s": 300}
    publish(nclient, "node", "offline", data, "warning")                                          # at level
    publish(nclient, "node", "offline", data, "warning")                                          # same alert
    assert s.pump() == 1
    assert s.pump() == 0
    clock.advance(60)
    assert s.pump() == 0
    assert len(provider.requests) == 1                                                           # exactly once
    publish(nclient, "app", "scan_blocked", {"app_id": "whoami"}, "critical")                     # above
    s.pump()
    assert len(provider.requests) == 2
    texts = [json.loads(r["body"])["text"] for r in provider.requests]
    assert texts[0].startswith("OneMind: [warning] beelink is offline")
    assert texts[1].startswith("OneMind: [critical] whoami")

    crit = add_sms(nclient, provider, min_severity="critical")
    route_everything(nclient, crit["id"])
    publish(nclient, "node", "offline", {"node_id": "n2", "hostname": "nas", "age_s": 300}, "warning")
    s.pump()
    assert len(provider.requests) == 2                                                           # below its level


def test_a_capped_channel_drops_with_a_ledger_entry_and_no_send(nclient, provider, clock):
    ch = add_sms(nclient, provider, daily_cap=2, per_hour=60)
    route_everything(nclient, ch["id"])
    s = svc(nclient)
    for i in range(3):
        publish(nclient, "app", "oom_killed", {"app_id": f"a{i}", "component": "web"}, "warning")
    s.pump()
    assert len(provider.requests) == 2
    dropped = [d for n in nclient.get("/v1/notifications", headers=OWNER).json()
               for d in s.repo.deliveries_for(n["id"]) if d.state == "dropped"]
    assert len(dropped) == 1 and dropped[0].last_error == "daily cap reached (2 per day)"
    assert dropped[0].next_attempt_at is None
    audit = [json.loads(x) for x in nclient.app.state.settings.audit_path.read_text().splitlines()]
    entry = [x for x in audit if x["event"] == "notify.delivery.dropped"]
    assert len(entry) == 1 and entry[0]["data"]["payload"]["channel_id"] == ch["id"]
    assert entry[0]["data"]["payload"]["reason"] == "daily_cap"
    clock.advance(3600)
    assert s.pump() == 0 and len(provider.requests) == 2      # a dropped item is never retried
    clock.advance(int(timedelta(hours=24).total_seconds()))
    publish(nclient, "app", "oom_killed", {"app_id": "later", "component": "web"}, "warning")
    s.pump()
    assert len(provider.requests) == 3                         # the window rolled over


def test_test_send_shows_the_receipt_and_counts_toward_the_cap(nclient, provider):
    ch = add_sms(nclient, provider, daily_cap=1)
    r = nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=OWNER).json()
    assert r["delivered"] is True and r["receipt"] == {"status": 200, "provider_id": "msg_0001"}
    text = json.loads(provider.requests[0]["body"])["text"]
    assert "Test" in text and text.startswith("OneMind:")
    r = nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=OWNER).json()
    assert r["delivered"] is False and r["error"] == "daily cap reached (1 per day)"
    assert len(provider.requests) == 1
    provider.status = 401
    other = add_sms(nclient, provider)
    r = nclient.post(f"/v1/notifications/channels/{other['id']}/test", headers=OWNER).json()
    assert r["delivered"] is False and r["error"] == "HTTP 401"
    assert nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=ADULT).status_code == 404


def test_per_hour_limit_holds_then_sends_one_summary(nclient, provider, clock):
    ch = add_sms(nclient, provider, per_hour=1)
    route_everything(nclient, ch["id"])
    s = svc(nclient)
    for i in range(3):
        publish(nclient, "app", "oom_killed", {"app_id": f"a{i}", "component": "web"}, "warning")
    s.pump()
    assert len(provider.requests) == 1
    clock.advance(3601)
    s.pump()
    assert len(provider.requests) == 2
    assert "2 notifications" in json.loads(provider.requests[-1]["body"])["text"]


def test_quiet_hours_hold_sms_like_any_channel(nclient, provider, clock):
    ch = add_sms(nclient, provider)
    nclient.put("/v1/notifications/preferences", headers=OWNER, json={
        "quiet_hours": {"tz": "UTC", "from": "21:30", "to": "07:00", "except_severity": ["critical"],
                        "except_topics": []},
        "routes": [{"match": {}, "channels": [ch["id"]]}]})
    publish(nclient, "node", "offline", {"node_id": "a", "hostname": "a", "age_s": 1}, "warning")
    assert svc(nclient).pump() == 0 and provider.requests == []
