# SPDX-License-Identifier: Apache-2.0
"""#186 E2 acceptance: a Home-Assistant-style app gets USB passthrough only through a broker grant.

The sandbox (policy.py) refuses a host path (F-04) for every app; an active grant lets through
exactly the granted device node, for that app only, and nothing wider.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import OWNER, AGENT, FakeKubectl, action_body, write_scan
from onemind_core import policy
from onemind_core.app import create_app
from onemind_core.catalog import AppEntry
from onemind_core.executors import KubernetesExecutor
from onemind_core.hostgrants.kinds import NO_HOST, HostAllowance, problem

REPO = Path(__file__).resolve().parents[2]
RULES_FILE = REPO / "sdk" / "policy" / "app-objects.yaml"
SCHEMA = REPO / "sdk" / "schema" / "onemind.app.schema.json"
HA = REPO / "apps" / "home-assistant"
STICK = "/dev/ttyUSB0"


@pytest.fixture(scope="module")
def rules():
    return policy.load_rules(RULES_FILE)


def usb_docs(path: str = STICK, hp_type: str | None = "CharDevice", **pod) -> list[dict]:
    """Home Assistant's real rendered objects, with a USB Zigbee stick mounted into the pod."""
    docs = [d for part in ("pvc.yaml", "deployment.yaml", "service.yaml")
            for d in yaml.safe_load_all((HA / "manifests" / part).read_text()) if d]
    spec = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]
    host_path = {"path": path} | ({"type": hp_type} if hp_type else {})
    spec["volumes"].append({"name": "zigbee", "hostPath": host_path})
    spec["containers"][0]["volumeMounts"].append({"name": "zigbee", "mountPath": "/dev/ttyUSB0"})
    spec.update(pod)
    return docs


def manifest() -> dict:
    return yaml.safe_load((HA / "onemind.app.yaml").read_text())


def rules_hit(docs, rules, app_id="home-assistant", host=NO_HOST) -> set[str]:
    return {v.rule for v in policy.check_objects(docs, app_id, manifest(), rules, host)}


def stick(path=STICK) -> HostAllowance:
    return HostAllowance.of([("device", path)])


def test_usb_passthrough_is_refused_without_a_grant(rules):
    assert rules_hit(usb_docs(), rules) == {"F-04"}


def test_usb_passthrough_is_allowed_with_the_granted_node(rules):
    assert rules_hit(usb_docs(), rules, host=stick()) == set()


@pytest.mark.parametrize("docs, why", [
    (lambda: usb_docs("/dev/ttyUSB1"), "another node than the granted one"),
    (lambda: usb_docs(hp_type=None), "no CharDevice type, so kubelet would mount anything there"),
    (lambda: usb_docs(hp_type="Directory"), "a directory, not the device"),
    (lambda: usb_docs("/dev"), "the whole /dev"),
])
def test_a_grant_allows_nothing_wider_than_the_node(rules, docs, why):
    assert "F-04" in rules_hit(docs(), rules, host=stick()), why


def test_a_device_grant_never_unlocks_privileged_or_host_namespaces(rules):
    docs = usb_docs(hostNetwork=True, hostPID=True)
    docs[1]["spec"]["template"]["spec"]["containers"][0]["securityContext"]["privileged"] = True
    assert rules_hit(docs, rules, host=stick()) == {"F-01", "F-02", "F-06"}


def test_host_network_and_realtime_grants_allow_only_their_own_field(rules):
    docs = usb_docs(hostNetwork=True)
    caps = docs[1]["spec"]["template"]["spec"]["containers"][0]["securityContext"]["capabilities"]
    caps["add"] = ["SYS_NICE"]
    assert rules_hit(docs, rules) == {"F-01", "F-04", "F-07"}
    granted = HostAllowance.of([("device", STICK), ("host-network", None), ("realtime", None)])
    assert rules_hit(docs, rules, host=granted) == set()
    caps["add"] = ["SYS_NICE", "SYS_ADMIN"]
    assert rules_hit(docs, rules, host=granted) == {"F-07"}


def test_grant_shapes_name_exactly_one_thing():
    assert problem("device", "usb-serial", "/dev/ttyUSB0") is None
    assert problem("device", "usb-serial", "/dev/serial/by-id/usb-Itead_Sonoff_Zigbee_3.0-if00-port0") is None
    assert problem("gpu", None, "/dev/dri/renderD128") is None
    assert problem("host-network", None, None) is None and problem("realtime", None, None) is None
    for bad in [("device", "usb-serial", "/dev/sda"), ("device", "usb-serial", "/dev/serial/by-id/../../sda"),
                ("device", None, "/dev/ttyUSB0"), ("device", "usb", "/dev/bus/usb"), ("gpu", None, "/dev/dri"),
                ("gpu", "video", "/dev/dri/renderD128"), ("host-network", None, "/dev/ttyUSB0"), ("root", None, None)]:
        assert problem(*bad), bad


def test_namespace_is_privileged_only_under_a_grant():
    assert policy.enforce_level("baseline") == "baseline"
    assert policy.enforce_level("baseline", stick()) == "privileged"


# ---- end to end: the gateway, the broker and the install sandbox --------------------------------

@pytest.fixture
def ha_client(settings, clock, rules):
    app_dir = settings.apps_dir / "home-assistant"
    shutil.copytree(HA, app_dir)
    doc = yaml.safe_load((app_dir / "onemind.app.yaml").read_text())
    doc["metadata"]["tier"] = "verified"  # CI sets it; Z-21: a host grant needs Verified or higher
    (app_dir / "onemind.app.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    (app_dir / "manifests" / "deployment.yaml").write_text(
        yaml.safe_dump(usb_docs()[1], sort_keys=False))
    write_scan(app_dir, clock.now)
    run = FakeKubectl()
    s = replace(settings, executor="kubernetes", app_schema_path=SCHEMA)
    with TestClient(create_app(s, clock=clock, executor=KubernetesExecutor(runner=run, rules=rules))) as c:
        yield c, run


def install(c, clock, key):
    r = c.post("/v1/actions", json=action_body(clock, app_id="home-assistant", key=key), headers=OWNER)
    assert r.status_code == 201, r.text
    return c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)


def grant_body(clock, key="g1"):
    return {"app_id": "home-assistant", "kind": "device", "device_class": "usb-serial", "path": STICK,
            "reason": "Zigbee coordinator stick", "idempotency_key": key,
            "expires_at": action_body(clock)["expires_at"]}


def test_home_assistant_gets_usb_only_through_an_owner_approved_grant(ha_client, clock):
    c, run = ha_client
    refused = install(c, clock, "i1")
    assert refused.status_code == 409 and refused.json()["error"] == "policy_refused"
    assert {d["rule"] for d in refused.json()["details"]} == {"F-04"} and run.cluster_calls == []

    # An agent may file the request; it stays pending and only the owner's approval activates it.
    filed = c.post("/v1/host-grants/requests", json=grant_body(clock), headers=AGENT)
    assert filed.status_code == 202, filed.text
    assert filed.json()["state"] == "awaiting_approval"
    assert c.post(f"/v1/actions/{filed.json()['id']}/approve", headers=AGENT).status_code == 403
    assert c.get("/v1/host-grants", headers=OWNER).json() == {"grants": []}
    assert install(c, clock, "i2").status_code == 409

    approved = c.post(f"/v1/actions/{filed.json()['id']}/approve", headers=OWNER)
    assert approved.status_code == 200 and approved.json()["state"] == "succeeded", approved.text
    [grant] = c.get("/v1/host-grants", headers=OWNER).json()["grants"]
    assert grant["active"] and grant["path"] == STICK and grant["app_id"] == "home-assistant"

    done = install(c, clock, "i3")
    assert done.status_code == 200 and done.json()["state"] == "succeeded", done.text
    namespace = yaml.safe_load(run.cluster_calls[0][1])
    assert namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "privileged"

    # Revocation removes it: the next render of the app is refused again.
    r = c.post(f"/v1/host-grants/{grant['id']}/revoke", headers=OWNER)
    assert r.status_code == 200 and r.json()["active"] is False
    assert c.post(f"/v1/host-grants/{grant['id']}/revoke", headers=OWNER).status_code == 404
    again = c.post("/v1/actions", json=action_body(clock, app_id="home-assistant", type_="app.update", key="u1"),
                   headers=OWNER)
    assert again.status_code == 201, again.text
    res = c.post(f"/v1/actions/{again.json()['id']}/approve", headers=OWNER)
    assert res.status_code == 409 and res.json()["error"] == "policy_refused", res.text
    assert c.app.state.host_grants.allowance("home-assistant") == NO_HOST
