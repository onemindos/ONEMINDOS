# SPDX-License-Identifier: Apache-2.0
import json

import httpx
import pytest

from test_contract_drift import event_server  # noqa: F401
from test_identity import csrf, enrol, setup_owner
from test_identity_notify import hc  # noqa: F401

from onemind_core.identity.models import TokenRow

CARD = "/v1/me/dashboard-card"
STREAM = CARD + "/events"
BACKUP = "onemind.event.backup.run.finished"


def binding(subject):
    return {"source": {"kind": "subject", "subject": subject}}


@pytest.mark.parametrize("bad", [
    "onemind.event.unmapped.ready",
    "onemind.event.backup.>",
    "onemind.event.backup.*.*",
    "onemind.event.*.finished",
    "onemind.event.backup.run.finished\n",
    "onemind.audit",
    "$SYS.HEARTBEAT",
    "onemind.app.backup.event",
])
def test_validates_the_gateway_subject_on_save(hc, bad):
    setup_owner(hc)
    response = hc.put(CARD, json=binding(bad), headers=csrf(hc))
    assert response.status_code == 422
    assert response.json()["reason"] == "bad_subject"
    assert hc.get(CARD).json() is None


def test_subject_card_is_personal_and_read_requires_the_current_scope(hc):
    setup_owner(hc)
    for role in ("child", "guest"):
        person = enrol(hc, role, role + "-account")
        assert person.put(CARD, json=binding(BACKUP), headers=csrf(person)).status_code == 403
        assert person.get(CARD).json() is None
    assert hc.put(CARD, json=binding(BACKUP), headers=csrf(hc)).json() == binding(BACKUP)
    narrow = hc.post("/v1/tokens", headers=csrf(hc), json={"name": "test-narrow", "scopes": ["nodes:read"]})
    token = narrow.json()["one_time"]["token"]
    headers = {"Authorization": "Bearer " + token}
    assert hc.get(CARD, headers=headers).status_code == 403
    assert hc.get(STREAM, headers=headers).status_code == 403
    assert hc.get(CARD).json() == binding(BACKUP)


def records(response):
    for line in response.iter_lines():
        if line.startswith("data: "):
            yield json.loads(line.removeprefix("data: "))


@pytest.mark.parametrize("event_server", ["hc"], indirect=True)
def test_filters_eventhub_facts_and_rechecks_live_scope(event_server, hc):
    setup_owner(hc)
    assert hc.put(CARD, json=binding("onemind.event.backup.run.*"), headers=csrf(hc)).status_code == 200
    created = hc.post("/v1/tokens", headers=csrf(hc),
                      json={"name": "test-backups", "scopes": ["backups:read"]}).json()
    token = created["one_time"]["token"]
    token_id = created["id"]
    headers = {"Authorization": "Bearer " + token}
    app = hc.app
    gw = app.state.gateway
    gw.events.publish_event("backup", "run.finished", {"hidden": "fixture-payload"}, severity="warning")
    gw.events.publish_event("node", "joined", {})
    gw.audit.append("backup.run.forged", None, None, {"count": 1})

    with httpx.Client(base_url=event_server, timeout=8) as web:
        with web.stream("GET", STREAM, headers=headers) as response:
            assert response.status_code == 200
            stream = records(response)
            first = next(stream)
            assert (first["type"], first["severity"], first["data"], first["subject"]) == (
                "backup.run.finished", "warning", {}, {},
            )
            # A limited credential keeps its identity when this scope is removed.
            gateway_identity = app.state.identity
            gateway_identity.repo.update(TokenRow, [TokenRow.id == token_id], {"scopes": ["nodes:read"]})
            gw.events.publish_event("backup", "run.finished", {})
            reset = next(stream)
            assert reset["type"] == "stream.reset"
            assert reset["data"]["reason"] == "subject_unavailable"
            assert list(stream) == []
        assert web.get(CARD, headers=headers).status_code == 403
        assert web.get(STREAM, headers=headers).status_code == 403
