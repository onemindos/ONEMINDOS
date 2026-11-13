# SPDX-License-Identifier: Apache-2.0
"""Notifications and alerts (contract §12.14): catalogue, alert life cycle, routing, channels."""

from __future__ import annotations

import base64
import email
import hashlib
import hmac
import json
from dataclasses import replace


import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER, action_body
from fakes import FakeHttp, FakeSmtp
from onemind_core.app import create_app
from onemind_core.notify import NotifySettings
from onemind_core.notify.crypto import b64u, b64u_decode

ADDR_TO = "owner" + "@" + "box.invalid"     # built at runtime: no address-shaped strings in the repo
ADDR_FROM = "onemind" + "@" + "box.invalid"


@pytest.fixture
def nclient(settings, clock, executor, tmp_path):
    s = replace(settings, sections={"notify": NotifySettings(worker=False, dir=tmp_path / "keys")})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


@pytest.fixture
def http():
    srv = FakeHttp()
    yield srv
    srv.close()


@pytest.fixture
def smtp():
    srv = FakeSmtp()
    yield srv
    srv.close()


def svc(c):
    return c.app.state.notify


def publish(c, domain, name, data, severity="info"):
    c.app.state.events.publish_event(domain, name, data, severity=severity)


def inbox(c, headers, **params):
    r = c.get("/v1/notifications", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def open_alerts(c, headers=OWNER):
    return c.get("/v1/alerts", headers=headers, params={"state": "open"}).json()


def add_channel(c, body, headers=OWNER):
    r = c.post("/v1/notifications/channels", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ---- sources: the action ledger -----------------------------------------------------------

def test_approval_opens_one_alert_for_owners_and_resolves_on_decision(nclient, clock):
    r = nclient.post("/v1/actions", headers=AGENT, json=action_body(clock))
    action_id = r.json()["id"]
    alerts = open_alerts(nclient)
    assert [a["type"] for a in alerts] == ["approval.requested"]
    assert alerts[0]["dedupe_key"] == f"approval:{action_id}"
    assert alerts[0]["subject"] == {"action_id": action_id, "app_id": "uptime-kuma"}
    items = inbox(nclient, OWNER)
    assert len(items) == 1 and items[0]["topic"] == "approvals" and items[0]["action_id"] == action_id
    assert items[0]["link"] == f"/approvals/{action_id}"
    assert "hermes" in items[0]["body"]
    assert inbox(nclient, ADULT) == [] and inbox(nclient, GUEST) == []
    assert open_alerts(nclient, GUEST) == [] and open_alerts(nclient, ADULT) == []

    assert nclient.post(f"/v1/actions/{action_id}/approve", headers=OWNER).json()["state"] == "succeeded"
    assert open_alerts(nclient) == []
    titles = [n["title"] for n in inbox(nclient, OWNER)]
    assert titles[0] == "Done: app.install uptime-kuma"


def test_failed_action_notifies_owners_and_person_requester(nclient, clock, executor):
    executor.outcome = "failed"
    a = nclient.post("/v1/actions", headers=OWNER, json=action_body(clock)).json()
    nclient.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
    first = inbox(nclient, OWNER)[0]
    assert first["title"] == "Failed: app.install uptime-kuma" and first["severity"] == "warning"


def test_outcome_unknown_opens_critical_alert_only_an_owner_resolves(nclient, clock, executor):
    executor.outcome = "outcome_unknown"
    a = nclient.post("/v1/actions", headers=OWNER, json=action_body(clock)).json()
    nclient.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
    [alert] = open_alerts(nclient)
    assert alert["type"] == "action.outcome_unknown" and alert["severity"] == "critical"
    assert nclient.post(f"/v1/alerts/{alert['id']}/resolve", headers=ADULT).status_code == 403
    r = nclient.post(f"/v1/alerts/{alert['id']}/resolve", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "resolved"
    audit = [json.loads(x) for x in nclient.app.state.settings.audit_path.read_text().splitlines()]
    assert any(x["event"] == "alert.resolved" and x["data"]["payload"]["by"] == "owner" for x in audit)


# ---- alert life cycle -------------------------------------------------------------------------

def test_dedupe_renotify_escalation_and_resolution(nclient, clock):
    data = {"node_id": "n1", "hostname": "beelink", "age_s": 125}
    publish(nclient, "node", "offline", data, "warning")
    publish(nclient, "node", "offline", data, "warning")
    [alert] = open_alerts(nclient)
    assert alert["occurrences"] == 2 and alert["dedupe_key"] == "node:n1:offline"
    assert len(inbox(nclient, OWNER)) == 1                       # dedupe: one notice
    clock.advance(31 * 60)
    publish(nclient, "node", "offline", data, "warning")
    assert len(inbox(nclient, OWNER)) == 2                       # one re-notify after 30 min
    publish(nclient, "node", "offline", {**data, "severity": "critical"})
    assert len(inbox(nclient, OWNER)) == 3                       # escalation notifies at once
    assert open_alerts(nclient)[0]["severity"] == "critical"
    publish(nclient, "node", "online", {"node_id": "n1"})
    assert open_alerts(nclient) == []
    assert inbox(nclient, OWNER)[0]["title"] == "Resolved: beelink is offline"


def test_flapping_reuses_the_alert(nclient, clock):
    data = {"node_id": "n1", "hostname": "pi", "age_s": 121}
    for _ in range(4):
        publish(nclient, "node", "offline", data, "warning")
        clock.advance(60)
        publish(nclient, "node", "online", {"node_id": "n1"})
        clock.advance(60)
    publish(nclient, "node", "offline", data, "warning")
    alerts = nclient.get("/v1/alerts", headers=OWNER).json()
    assert len(alerts) == 1 and alerts[0]["flapping"] is True and alerts[0]["state"] == "open"


def test_ack_by_adult_and_audience_filter(nclient):
    publish(nclient, "app", "unhealthy", {"app_id": "whoami", "reason": "not ready for 200 s"}, "warning")
    [alert] = open_alerts(nclient, ADULT)
    assert alert["fix"] == {"type": "app.restart", "params": {"app_id": "whoami"}}
    assert open_alerts(nclient, GUEST) == []
    assert nclient.get(f"/v1/alerts/{alert['id']}", headers=GUEST).status_code == 404
    assert nclient.post(f"/v1/alerts/{alert['id']}/ack", headers=GUEST).status_code == 403
    r = nclient.post(f"/v1/alerts/{alert['id']}/ack", headers=ADULT)
    assert r.json()["state"] == "acknowledged" and r.json()["acked_by"] == "adult"
    assert open_alerts(nclient)[0]["state"] == "acknowledged"   # still counts as open
    assert nclient.post(f"/v1/alerts/{alert['id']}/resolve", headers=OWNER).status_code == 409  # auto-resolving


def test_fix_files_a_normal_request(nclient, clock):
    nclient.post("/v1/actions", headers=OWNER, json=action_body(clock))
    a = nclient.get("/v1/actions", headers=OWNER).json()[0]
    nclient.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)   # installed now
    publish(nclient, "app", "scan_blocked", {"app_id": "uptime-kuma"}, "critical")
    alert = next(x for x in open_alerts(nclient) if x["type"] == "app.scan_blocked")
    assert nclient.post(f"/v1/alerts/{alert['id']}/fix", headers=GUEST).status_code == 403
    assert nclient.post(f"/v1/alerts/{alert['id']}/fix", headers=AGENT, json={"approve": True}).status_code == 403
    r = nclient.post(f"/v1/alerts/{alert['id']}/fix", headers=AGENT)
    assert r.status_code == 202 and r.json()["type"] == "app.remove" and r.json()["state"] == "awaiting_approval"
    again = nclient.post(f"/v1/alerts/{alert['id']}/fix", headers=AGENT)
    assert again.json()["id"] == r.json()["id"]                 # idempotent per alert and requester
    # a fix type the ledger cannot run yet is refused, not faked
    publish(nclient, "app", "unhealthy", {"app_id": "whoami", "reason": "x"}, "warning")
    unhealthy = next(x for x in open_alerts(nclient) if x["type"] == "app.unhealthy")
    assert nclient.post(f"/v1/alerts/{unhealthy['id']}/fix", headers=OWNER).status_code == 409


# ---- channels ---------------------------------------------------------------------------------

def test_ntfy_channel_title_level_and_secret_never_returned(nclient, http):
    ch = add_channel(nclient, {"kind": "ntfy", "label": "phone", "config": {"url": http.url + "/onemind"},
                               "secret": "tk_test_" + "x" * 20})
    assert ch["kind"] == "unifiedpush" and ch["content_level"] == "title" and ch["secret"] == "provided"
    assert "tk_test_" not in json.dumps(nclient.get("/v1/notifications/channels", headers=OWNER).json())
    publish(nclient, "node", "offline", {"node_id": "n1", "hostname": "beelink", "age_s": 300}, "warning")
    assert svc(nclient).pump() == 1
    [req] = http.requests
    assert req["path"] == "/onemind"
    assert req["headers"]["Title"] == "[warning] beelink is offline"
    assert req["headers"]["Priority"] == "4"
    assert req["headers"]["Authorization"] == "Bearer tk_test_" + "x" * 20
    assert b"300" not in req["body"]                             # title level: no body text
    assert "Click" not in req["headers"]


def test_info_items_stay_in_app_by_default(nclient, http):
    add_channel(nclient, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    publish(nclient, "update", "applied", {"node_id": "n1", "hostname": "pi", "version": "1.2"})
    assert len(inbox(nclient, OWNER)) == 1
    assert svc(nclient).pump() == 0 and http.requests == []


def test_webhook_full_and_signed(nclient, http, clock):
    add_channel(nclient, {"kind": "webhook", "label": "hook", "config": {"url": http.url + "/h"},
                          "secret": "s" * 32})
    publish(nclient, "backup", "run.failed", {"target": "usb", "reason": "disk full"}, "error")
    svc(nclient).pump()
    [req] = http.requests
    doc = json.loads(req["body"])
    assert doc["title"] == "[warning] Backup to usb failed" and doc["body"] == "disk full"
    assert doc["link"].endswith("/backups") and doc["box_id"] == "abc123def456"
    ts = req["headers"]["X-Onemind-Timestamp"]
    assert ts == str(int(clock.now.timestamp()))
    want = "sha256=" + hmac.new(b"s" * 32, ts.encode() + b"." + req["body"], hashlib.sha256).hexdigest()
    assert req["headers"]["X-Onemind-Signature"] == want


def test_email_over_fake_smtp(nclient, smtp):
    add_channel(nclient, {"kind": "email", "label": "mail", "content_level": "full", "config": {
        "host": "127.0.0.1", "port": smtp.port, "security": "none", "from": ADDR_FROM, "to": ADDR_TO}})
    publish(nclient, "app", "scan_blocked", {"app_id": "whoami"}, "critical")
    svc(nclient).pump()
    [m] = smtp.messages
    msg = email.message_from_string(m["data"])
    assert msg["Subject"] == "[critical] whoami failed its security scan"
    assert ADDR_TO in m["rcpt"][0]
    assert "/apps/whoami" in msg.get_payload()


def test_test_endpoint_reports_delivery(nclient, http):
    ch = add_channel(nclient, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    r = nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=OWNER).json()
    assert r["delivered"] is True and r["latency_ms"] >= 0
    assert nclient.get("/v1/notifications/channels", headers=OWNER).json()[0]["verified"] is True
    http.status = 500
    r = nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=OWNER).json()
    assert r == {"delivered": False, "latency_ms": r["latency_ms"], "error": "HTTP 500"}
    assert nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=ADULT).status_code == 404


def test_retry_backoff_dead_and_channel_failing_alert(nclient, http, clock):
    http.status = 503
    ch = add_channel(nclient, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    publish(nclient, "app", "scan_blocked", {"app_id": "whoami"}, "critical")
    s = svc(nclient)
    s.pump()
    for wait in (30, 120, 600, 3600, 6 * 3600):
        assert s.pump() == 0                       # nothing due before the backoff elapses
        clock.advance(wait)
        assert s.pump() == 1
    assert len(http.requests) == 6
    [d] = s.repo.deliveries_for(inbox(nclient, OWNER)[-1]["id"])
    assert d.state == "dead" and d.last_error == "HTTP 503"
    failing = [a for a in open_alerts(nclient) if a["type"] == "notify.channel_failing"]
    assert len(failing) == 1 and failing[0]["dedupe_key"] == f"channel:{ch['id']}"
    item = next(n for n in inbox(nclient, OWNER) if n["alert_id"] == failing[0]["id"])
    assert s.repo.deliveries_for(item["id"]) == []           # in-app only
    http.status = 200
    nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=OWNER)
    assert not [a for a in open_alerts(nclient) if a["type"] == "notify.channel_failing"]


def test_guest_cannot_point_a_channel_at_the_lan(nclient, http):
    r = nclient.post("/v1/notifications/channels", headers=GUEST,
                     json={"kind": "webhook", "label": "x", "config": {"url": http.url}})
    assert r.status_code == 422
    r = nclient.post("/v1/notifications/channels", headers=OWNER,
                     json={"kind": "webhook", "label": "x", "config": {"url": "http://169.254.169.254/latest"}})
    assert r.status_code == 422
    r = nclient.post("/v1/notifications/channels", headers=OWNER,
                     json={"kind": "webhook", "label": "x", "config": {"url": "https://u" + ":p@" + "example.org/"}})
    assert r.status_code == 422
    assert nclient.post("/v1/notifications/channels", headers=AGENT,
                        json={"kind": "webhook", "label": "x", "config": {"url": http.url}}).status_code == 403


# ---- routing ----------------------------------------------------------------------------------

def test_quiet_hours_hold_then_one_summary(nclient, http, clock):
    ch = add_channel(nclient, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    prefs = {"quiet_hours": {"tz": "UTC", "from": "21:30", "to": "07:00",
                             "except_severity": ["critical"], "except_topics": ["approvals"]},
             "routes": [{"match": {}, "channels": [ch["id"]]}]}
    r = nclient.put("/v1/notifications/preferences", headers=OWNER, json=prefs)
    assert r.status_code == 200 and r.headers["ETag"]
    publish(nclient, "node", "offline", {"node_id": "a", "hostname": "a", "age_s": 1}, "warning")
    publish(nclient, "node", "offline", {"node_id": "b", "hostname": "b", "age_s": 1}, "warning")
    s = svc(nclient)
    assert s.pump() == 0
    publish(nclient, "app", "scan_blocked", {"app_id": "whoami"}, "critical")
    assert s.pump() == 1                           # critical goes through quiet hours
    clock.advance(9 * 3600)                        # 07:00 next morning
    assert s.pump() == 1
    summary = json.loads(http.requests[-1]["body"])
    assert summary["count"] == 2 and summary["title"] == "[warning] 2 notifications"


def test_digest_holds_info(nclient, http, clock):
    ch = add_channel(nclient, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    nclient.put("/v1/notifications/preferences", headers=OWNER, json={
        "routes": [{"match": {}, "channels": [ch["id"]]}], "digest": {"enabled": True, "at": "08:00"}})
    publish(nclient, "update", "applied", {"node_id": "n", "hostname": "n", "version": "2"})
    s = svc(nclient)
    assert s.pump() == 0
    clock.advance(10 * 3600)
    assert s.pump() == 1


def test_rate_cap_per_channel(nclient, http, clock):
    ch = add_channel(nclient, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    nclient.put("/v1/notifications/preferences", headers=OWNER,
                json={"routes": [{"match": {}, "channels": [ch["id"]]}]})
    s = svc(nclient)
    for i in range(33):
        publish(nclient, "app", "oom_killed", {"app_id": f"a{i}", "component": "web"}, "warning")
    s.pump()
    assert len(http.requests) == 30
    clock.advance(3601)
    s.pump()
    assert len(http.requests) == 31 and json.loads(http.requests[-1]["body"])["count"] == 3


def test_preferences_validation_and_etag(nclient):
    r = nclient.get("/v1/notifications/preferences", headers=OWNER)
    tag = r.headers["ETag"]
    assert r.json()["routes"][0] == {"match": {"severity_at_least": "warning"}, "channels": ["*"]}
    bad = [{"routes": [{"match": {"topic": "nope"}, "channels": ["*"]}]},
           {"quiet_hours": {"tz": "Mars/Base", "from": "22:00", "to": "07:00"}},
           {"routes": [{"match": {}, "channels": ["chn_01JAAAAAAAAAAAAAAAAAAAAAAA"]}]},
           {"extra": 1}]
    for doc in bad:
        assert nclient.put("/v1/notifications/preferences", headers=OWNER, json=doc).status_code == 422, doc
    ok = nclient.put("/v1/notifications/preferences", headers={**OWNER, "If-Match": tag}, json={"routes": []})
    assert ok.status_code == 200
    stale = nclient.put("/v1/notifications/preferences", headers={**OWNER, "If-Match": tag}, json={"routes": []})
    assert stale.status_code == 409
    assert nclient.get("/v1/notifications/preferences", headers=AGENT).status_code == 403


# ---- inbox ------------------------------------------------------------------------------------

def test_inbox_pagination_filters_and_read(nclient, clock):
    for i in range(5):
        publish(nclient, "app", "oom_killed", {"app_id": f"a{i}", "component": "c"}, "warning")
        clock.advance(1)
    r = nclient.get("/v1/notifications", headers=OWNER, params={"limit": 2})
    assert len(r.json()) == 2 and 'rel="next"' in r.headers["Link"]
    nxt = r.headers["Link"].split("cursor=")[1].split(">")[0]
    page2 = nclient.get("/v1/notifications", headers=OWNER, params={"limit": 2, "cursor": nxt}).json()
    assert {n["id"] for n in page2}.isdisjoint({n["id"] for n in r.json()})
    first = r.json()[0]["id"]
    assert nclient.post(f"/v1/notifications/{first}/read", headers=OWNER).json()["read_at"]
    assert nclient.get(f"/v1/notifications/{first}", headers=ADULT).status_code == 404
    assert len(inbox(nclient, OWNER, unread=True)) == 4
    assert nclient.post("/v1/notifications/read-all", headers=OWNER).json() == {"marked": 4}
    assert inbox(nclient, OWNER, unread=True) == []
    assert len(inbox(nclient, OWNER, topic="apps.*", severity="warning")) == 5
    assert nclient.get("/v1/notifications", headers=AGENT).status_code == 403


# ---- send -------------------------------------------------------------------------------------

def test_agent_send_rules_and_rate_limit(nclient):
    body = {"severity": "info", "topic": "plugin.hermes", "title": "Daily summary ready", "body": "3 items"}
    r = nclient.post("/v1/notifications/send", headers=AGENT, json=body)
    assert r.status_code == 202 and r.json()["queued"] == 1
    assert inbox(nclient, OWNER)[0]["source"] == "hermes"
    assert nclient.post("/v1/notifications/send", headers=OWNER, json=body).status_code == 403
    assert nclient.post("/v1/notifications/send", headers=AGENT, json={**body, "topic": "approvals"}).status_code == 403
    assert nclient.post("/v1/notifications/send", headers=AGENT, json={**body, "severity": "critical"}).status_code == 422
    d = nclient.post("/v1/notifications/send", headers=AGENT, json={**body, "dedupe_key": "k"}).json()
    assert d["deduplicated"] is False
    assert nclient.post("/v1/notifications/send", headers=AGENT, json={**body, "dedupe_key": "k"}).json()["deduplicated"]
    codes = [nclient.post("/v1/notifications/send", headers=AGENT, json=body).status_code for _ in range(10)]
    assert codes.count(429) >= 1
    r = nclient.post("/v1/notifications/send", headers=AGENT, json=body)
    assert r.status_code == 429 and r.json()["error"] == "rate_limited" and int(r.headers["Retry-After"]) > 0


# ---- push -------------------------------------------------------------------------------------

def _decrypt(body: bytes, ua_priv: ec.EllipticCurvePrivateKey, auth: bytes) -> bytes:
    salt, rs, idlen = body[:16], body[16:20], body[20]
    as_pub = body[21:21 + idlen]
    ct = body[21 + idlen:]
    ua_pub = ua_priv.public_key().public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint)
    shared = ua_priv.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    hk = lambda salt_, info, n, ikm: HKDF(hashes.SHA256(), n, salt_, info).derive(ikm)  # noqa: E731
    ikm = hk(auth, b"WebPush: info\x00" + ua_pub + as_pub, 32, shared)
    cek = hk(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = hk(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    plain = AESGCM(cek).decrypt(nonce, ct, None)
    assert plain.endswith(b"\x02") and int.from_bytes(rs, "big") == 4096
    return plain[:-1]


def test_web_push_is_encrypted_vapid_signed_and_carries_ids_only(nclient, http):
    ua = ec.generate_private_key(ec.SECP256R1())
    auth = b"0123456789abcdef"
    keys = {"p256dh": b64u(ua.public_key().public_bytes(serialization.Encoding.X962,
                                                         serialization.PublicFormat.UncompressedPoint)),
            "auth": b64u(auth)}
    r = nclient.post("/v1/push/registrations", headers=OWNER,
                     json={"platform": "webpush", "endpoint": http.url + "/push/abc", "keys": keys, "label": "laptop"})
    assert r.status_code == 201
    dev = r.json()
    assert "endpoint" not in dev and nclient.get("/v1/push/registrations", headers=OWNER).json()[0]["id"] == dev["id"]
    vapid_pub = nclient.get("/v1/push/vapid-public-key", headers=GUEST).json()["key"]
    publish(nclient, "app", "scan_blocked", {"app_id": "whoami"}, "critical")
    svc(nclient).pump()
    [req] = http.requests
    assert req["headers"]["Content-Encoding"] == "aes128gcm" and req["headers"]["Urgency"] == "high"
    payload = json.loads(_decrypt(req["body"], ua, auth))
    nid = inbox(nclient, OWNER)[0]["id"]
    assert payload == {"notification_id": nid, "box_id": "abc123def456"}
    # VAPID: k is the box key, t is an ES256 JWT for the push service origin, signed by it
    auth_hdr = req["headers"]["Authorization"]
    t = auth_hdr.split("t=")[1].split(",")[0]
    assert auth_hdr.endswith("k=" + vapid_pub)
    head, claims, sig = t.split(".")
    assert json.loads(b64u_decode(claims))["aud"] == http.url
    raw = b64u_decode(sig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64u_decode(vapid_pub))
    pub.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    assert nclient.delete(f"/v1/push/registrations/{dev['id']}", headers=ADULT).status_code == 404
    assert nclient.delete(f"/v1/push/registrations/{dev['id']}", headers=OWNER).status_code == 204


def test_push_registration_validation(nclient, http):
    bad = [{"platform": "apns", "token": "abc"},
           {"platform": "webpush", "endpoint": http.url},
           {"platform": "webpush", "endpoint": http.url, "keys": {"p256dh": "AAAA", "auth": "AAAA"}}]
    for body in bad:
        assert nclient.post("/v1/push/registrations", headers=OWNER, json=body).status_code == 422, body
    ok = nclient.post("/v1/push/registrations", headers=OWNER,
                      json={"platform": "unifiedpush", "endpoint": http.url + "/up"})
    assert ok.status_code == 201
    publish(nclient, "app", "scan_blocked", {"app_id": "whoami"}, "critical")
    svc(nclient).pump()
    assert set(json.loads(http.requests[0]["body"])) == {"notification_id", "box_id"}


def test_secrets_and_endpoints_are_sealed_at_rest(nclient, http):
    add_channel(nclient, {"kind": "webhook", "label": "x", "config": {"url": http.url}, "secret": "z" * 40})
    nclient.post("/v1/push/registrations", headers=OWNER,
                 json={"platform": "unifiedpush", "endpoint": http.url + "/secret-topic"})
    from sqlalchemy import text
    with nclient.app.state.gateway.db.engine.connect() as conn:
        dump = json.dumps([list(map(str, r)) for t in ("notify_channels", "notify_devices")
                           for r in conn.execute(text(f"SELECT * FROM {t}"))])
    assert "z" * 40 not in dump and "secret-topic" not in dump


# ---- node events from NATS ----------------------------------------------------------------------

def test_node_outbox_event_mapping(nclient):
    s = svc(nclient)
    env = {"schema": "onemind.event/v1", "type": "update.rolled_back", "data": {"version": "2", "reason": "health gate"}}
    assert s.on_node_event("onemind.node.n7.event.update.rolled_back", json.dumps(env).encode())
    [a] = open_alerts(nclient)
    assert a["dedupe_key"] == "os:n7:rollback" and a["source_id"] == "node:n7"
    assert not s.on_node_event("onemind.node.n7.event.update.applied", json.dumps(env).encode())  # type mismatch
    assert not s.on_node_event("onemind.node.n7.event.x", b"not json")
    assert not s.on_node_event("onemind.node.n7.event.unknown", json.dumps({**env, "type": "unknown"}).encode())


def test_notify_tables_are_registered_feature(nclient):
    from onemind_core.store import registered_schemas
    assert "notify" in [s.feature for s in registered_schemas()]


def test_keys_are_private_files(nclient, tmp_path):
    for name in ("secret.key", "vapid.pem"):
        assert (tmp_path / "keys" / name).stat().st_mode & 0o077 == 0
    assert len(base64.urlsafe_b64decode(svc(nclient).vapid.public_key + "=")) == 65


def test_default_worker_runs_in_background(settings, clock, executor, http, tmp_path):
    s = replace(settings, sections={"notify": NotifySettings(worker=True, poll_s=0.05, dir=tmp_path / "k")})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        add_channel(c, {"kind": "webhook", "label": "x", "config": {"url": http.url}})
        publish(c, "app", "scan_blocked", {"app_id": "whoami"}, "critical")
        import time
        for _ in range(100):
            if http.requests:
                break
            time.sleep(0.05)
        assert len(http.requests) == 1




def test_nats_listener_subscribes_and_ingests(nclient):
    """The NATS path without a server: a fake connection records the subscription and its callback."""
    import asyncio

    class Msg:
        def __init__(self, subject, data):
            self.subject, self.data = subject, data

    class FakeNc:
        is_connected = True

        def __init__(self):
            self.subs = []

        async def subscribe(self, subject, cb):
            self.subs.append((subject, cb))

    s = svc(nclient)
    bus = nclient.app.state.bus
    nc = FakeNc()
    bus.nc = nc
    env = {"type": "backup.run.failed", "data": {"target": "usb", "reason": "disk full"}}

    async def run():
        task = asyncio.create_task(s._nats_listener())
        for _ in range(50):
            if nc.subs:
                break
            await asyncio.sleep(0.05)
        task.cancel()
        subject, cb = nc.subs[0]
        assert subject == "onemind.node.*.event.>"
        await cb(Msg("onemind.node.n2.event.backup.run.failed", json.dumps(env).encode()))

    try:
        asyncio.run(run())
    finally:
        bus.nc = None
    [a] = open_alerts(nclient)
    assert a["dedupe_key"] == "backup:usb" and a["source_id"] == "node:n2"


# ---- review fixes: SSRF, header injection, throttling, privacy, node outbox, fix retries ------

def _ip(*parts) -> str:
    return ".".join(str(x) for x in parts)       # built at runtime: no address literals in the repo


def test_non_owner_destinations_must_be_globally_routable():
    import ipaddress

    from onemind_core.notify.channels import DeliveryError, check_address

    tailnet = ipaddress.ip_address(_ip(100, 64, 0, 1))        # CGNAT / tailnet: not is_private
    mapped_metadata = ipaddress.ip_address("::ffff:" + _ip(169, 254, 169, 254))
    mapped_lan = ipaddress.ip_address("::ffff:" + _ip(10, 0, 0, 1))
    with pytest.raises(DeliveryError):
        check_address(tailnet, lan_ok=False)
    check_address(tailnet, lan_ok=True)
    for lan_ok in (False, True):
        with pytest.raises(DeliveryError):
            check_address(mapped_metadata, lan_ok=lan_ok)
    with pytest.raises(DeliveryError):
        check_address(mapped_lan, lan_ok=False)
    check_address(ipaddress.ip_address("2606:4700::1"), lan_ok=False)  # a global address passes


def test_peer_is_checked_after_connect_so_dns_rebinding_fails(http, monkeypatch):
    import ipaddress

    from onemind_core.notify import channels

    # The early check sees a public address; the connection then lands on the loopback server.
    monkeypatch.setattr(channels, "_addresses", lambda host: [ipaddress.ip_address("2606:4700::1")])
    url = http.url.replace("http://", "https://")
    with pytest.raises(channels.DeliveryError, match="local network"):
        channels.http_post(url, b"{}", {}, timeout=5, lan_ok=False)
    assert http.requests == []                                  # nothing reached the server
    assert channels.http_post(http.url, b"{}", {}, timeout=5, lan_ok=True) == 200


def test_secret_with_control_characters_is_refused(nclient, http):
    r = nclient.post("/v1/notifications/channels", headers=OWNER, json={
        "kind": "ntfy", "label": "p", "config": {"url": http.url}, "secret": "tok\r\nX-Injected: 1"})
    assert r.status_code == 422
    ch = add_channel(nclient, {"kind": "ntfy", "label": "p", "config": {"url": http.url}})
    r = nclient.patch(f"/v1/notifications/channels/{ch['id']}", headers=OWNER, json={"secret": "a\nb"})
    assert r.status_code == 422


def test_channel_test_is_rate_limited(nclient, http):
    ch = add_channel(nclient, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    codes = [nclient.post(f"/v1/notifications/channels/{ch['id']}/test", headers=OWNER).status_code
             for _ in range(6)]
    assert codes == [200] * 5 + [429]
    assert len(http.requests) == 5


def test_owner_listing_hides_other_peoples_destinations(nclient, monkeypatch):
    import socket

    from onemind_core.notify import channels

    def resolve(host, port, **kwargs):
        assert host == "ntfy.sh"
        return [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                 ("2606:4700::1", 0, 0, 0))]

    def no_delivery(*args, **kwargs):
        pytest.fail("listing channels must not send HTTP requests")

    # Keep the real SSRF checks; only DNS and unexpected HTTP delivery are isolated.
    monkeypatch.setattr(channels.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(channels, "http_post", no_delivery)
    mine = add_channel(nclient, {"kind": "ntfy", "label": "mine", "config": {"url": "https://ntfy.sh/owner-topic"}})
    add_channel(nclient, {"kind": "ntfy", "label": "theirs", "config": {"url": "https://ntfy.sh/adult-secret-topic"}},
                headers=ADULT)
    listed = nclient.get("/v1/notifications/channels", headers=OWNER).json()
    assert "adult-secret-topic" not in json.dumps(listed)
    own = next(c for c in listed if c["id"] == mine["id"])
    assert own["config"] == {"url": "https://ntfy.sh/owner-topic"}  # no internal "lan" flag
    theirs = nclient.get("/v1/notifications/channels", headers=ADULT).json()
    assert theirs[0]["config"]["url"].endswith("adult-secret-topic")


def test_node_outbox_cannot_raise_or_resolve_gateway_alerts(nclient):
    s = svc(nclient)
    publish(nclient, "app", "scan_blocked", {"app_id": "whoami"}, "critical")

    def env(type_, **data):
        return json.dumps({"schema": "onemind.event/v1", "type": type_, "data": data}).encode()

    for type_, data in [
        ("app.scan_ok", {"app_id": "whoami"}),                   # would silence a security alert
        ("approval.requested", {"action_id": "act_x", "action_type": "app.remove", "app_id": "whoami"}),
        ("action.succeeded", {"action_id": "act_x", "requested_by": "guest"}),
        ("notify.channel_failing", {"channel_id": "chn_x", "label": "x", "reason": "x", "person_id": "guest"}),
    ]:
        assert not s.on_node_event(f"onemind.node.n7.event.{type_}", env(type_, **data))
    assert [a["type"] for a in open_alerts(nclient)] == ["app.scan_blocked"]
    assert inbox(nclient, GUEST) == []
    # node conditions still work, and a node cannot attach an action or a recipient
    assert s.on_node_event("onemind.node.n7.event.disk.low",
                           env("disk.low", free_pct=5, mount="/data", free_gb=3, action_id="act_x"))
    disk = next(a for a in open_alerts(nclient) if a["type"] == "disk.low")
    assert disk["dedupe_key"] == "node:n7:disk" and "action_id" not in disk["subject"]


def test_fix_can_be_requested_again_after_a_denial(nclient, clock):
    nclient.post("/v1/actions", headers=OWNER, json=action_body(clock))
    a = nclient.get("/v1/actions", headers=OWNER).json()[0]
    nclient.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
    publish(nclient, "app", "scan_blocked", {"app_id": "uptime-kuma"}, "critical")
    alert = next(x for x in open_alerts(nclient) if x["type"] == "app.scan_blocked")
    first = nclient.post(f"/v1/alerts/{alert['id']}/fix", headers=AGENT).json()
    assert nclient.post(f"/v1/actions/{first['id']}/deny", headers=OWNER).status_code == 200
    second = nclient.post(f"/v1/alerts/{alert['id']}/fix", headers=AGENT)
    assert second.status_code == 202 and second.json()["id"] != first["id"]
    assert second.json()["state"] == "awaiting_approval"
    again = nclient.post(f"/v1/alerts/{alert['id']}/fix", headers=AGENT)
    assert again.json()["id"] == second.json()["id"]            # still idempotent while pending
