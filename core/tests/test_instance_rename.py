# SPDX-License-Identifier: Apache-2.0
"""PUT /v1/instance/name (P-05): renaming the box is an owner action. A real gateway, ledger, approval rule and
audit chain talk over a real Unix socket to a stand-in for `onemindd host serve` (same routes and JSON as
internal/host). An agent may ask, never approve; nothing changes before approval; the sign-in name follows only
once the host says it renamed the box.
"""

from __future__ import annotations

import pytest

from conftest import ADULT, AGENT, GUEST, OWNER, make_client
from test_service_actions import audit, box, host  # noqa: F401  (the fixture and the helpers)

SETTINGS = {"box_name": "onemind", "time_zone": "UTC", "backup_choice": "later"}


def rename(c, name="kitchen", who=OWNER, **body):
    return c.put("/v1/instance/name", headers=who, json={"name": name, **body})


def setup_done(c):
    r = c.put("/v1/onboarding/settings", headers=OWNER, json=SETTINGS)
    assert r.status_code == 200, r.text


def test_an_agent_can_ask_to_rename_but_the_owner_decides(settings, clock, host):
    with box(settings, clock, host.path) as c:
        setup_done(c)
        before = c.get("/v1/instance/name").json()
        r = rename(c, who=AGENT, reason="the label on the box says kitchen")
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["type"] == "instance.rename" and a["state"] == "awaiting_approval" and a["params"] == {"name": "kitchen"}
        assert r.headers["Location"] == f"/v1/actions/{a['id']}"
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=AGENT).status_code == 403
        assert host.posts == [] and c.get("/v1/instance/name").json() == before  # nothing changes before approval
        ok = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
        assert ok.status_code == 200 and ok.json()["state"] == "dispatched", ok.text
        assert host.posts == [{"action_id": a["id"], "kind": "set-hostname", "hostname": "kitchen"}]
        assert c.get("/v1/instance/name").json() == {"name": "kitchen"}  # saved before the host restarts the gateway
        host.ops[a["id"]].update(state="succeeded", message="the box is now called kitchen")
        c.app.state.hostlink.poll()
        assert c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "succeeded"
        events = [x["event"] for x in audit(settings) if x.get("action_id") == a["id"]]
        assert "action.requested" in events and any(e.startswith("action.approved") for e in events), events


def test_the_name_is_put_back_when_the_host_could_not_rename(settings, clock, host):
    with box(settings, clock, host.path) as c:
        setup_done(c)
        a = rename(c).json()
        c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
        host.ops[a["id"]].update(state="failed", reason="host_error", message="renaming the box failed: denied")
        c.app.state.hostlink.poll()
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "failed"
        assert c.get("/v1/instance/name").json() == {"name": "onemind"}
        assert c.get("/v1/onboarding/settings", headers=OWNER).json()["box_name"] == "onemind"


def test_the_display_name_stays_after_a_finished_rename(settings, clock, host):
    with box(settings, clock, host.path) as c:
        setup_done(c)
        link = c.app.state.hostlink
        a = rename(c, "kitchen").json()
        c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
        host.ops[a["id"]].update(state="succeeded", message="ok")
        link.poll()
        assert c.get("/v1/instance/name").json() == {"name": "kitchen"}
        assert c.get("/v1/onboarding/settings", headers=OWNER).json()["time_zone"] == "UTC"  # nothing else was touched


@pytest.mark.parametrize("name", ["Kitchen", "my box", "-kitchen", "kitchen-", "a.b", "", "x" * 64, "kitchen\n", "k_1", "ké"])
def test_a_name_that_is_not_one_dns_label_is_refused_and_nothing_is_filed(settings, clock, host, name):
    with box(settings, clock, host.path) as c:
        setup_done(c)
        r = rename(c, name)
        assert r.status_code == 422, r.text
        assert c.get("/v1/actions", headers=OWNER).json() == [] and host.posts == []


def test_only_owners_and_agents_may_ask_and_a_replay_is_the_same_action(settings, clock, host):
    with box(settings, clock, host.path) as c:
        setup_done(c)
        for who in (ADULT, GUEST):
            assert rename(c, who=who).status_code == 403
        assert c.put("/v1/instance/name", json={"name": "kitchen"}).status_code == 401
        first, again = rename(c, idempotency_key="same"), rename(c, idempotency_key="same")
        assert first.status_code == 202 and again.status_code == 200 and again.json()["id"] == first.json()["id"]
        hdr = {**OWNER, "Idempotency-Key": "hdr-1"}
        h1, h2 = (c.put("/v1/instance/name", headers=hdr, json={"name": "garage"}) for _ in range(2))
        assert h1.status_code == 202 and h2.status_code == 200 and h2.json()["id"] == h1.json()["id"] != first.json()["id"]


def test_it_waits_for_the_first_run_setup_and_for_the_host(settings, clock, tmp_path):
    with box(settings, clock, host_sock := str(tmp_path / "none.sock")) as c:  # no host service on this box
        r = rename(c)
        assert r.status_code == 409 and r.json()["reason"] == "setup_needed", r.text
        setup_done(c)
        r = rename(c)
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable", r.text
        assert c.get("/v1/actions", headers=OWNER).json() == []
    assert host_sock


def test_the_name_is_still_open_to_everyone_before_sign_in(settings, clock):
    with make_client(settings, clock) as c:
        assert c.get("/v1/instance/name").status_code == 200


def test_the_box_name_follows_the_saved_name(tmp_path):
    from onemind_core.netconf import NetSettings

    f = tmp_path / "hostname"
    net = NetSettings(box_name="onemind", hostname_file=f)
    assert net.box() == "onemind"  # never renamed: no file
    f.write_text("kitchen\n")
    assert net.box() == "kitchen" and net.box_domains()[1] == "kitchen.local"
    f.write_text("../etc\n")
    assert net.box() == "onemind"  # a file that is not a DNS label is ignored


def _verify(leaf_pem: bytes, ca_pem: bytes, name: str) -> None:
    """Verify the way a strict client does (RFC 5280 incl. name constraints) against the box's ca.crt."""
    from cryptography import x509
    from cryptography.x509.verification import PolicyBuilder, Store

    store = Store([x509.load_pem_x509_certificate(ca_pem)])
    leaf = x509.load_pem_x509_certificates(leaf_pem)[0]
    verifier = PolicyBuilder().store(store).build_server_verifier(x509.DNSName(name))
    verifier.verify(leaf, [])


def test_a_rename_keeps_the_https_certificate_inside_the_ca_constraints(tmp_path):
    """The CA's name constraints are fixed for its life: after a rename the certificate keeps the names the CA
    permits, so it still verifies against the existing ca.crt, and the join URL names a name the cert covers."""
    from onemind_core.ca import BoxCA, existing_box_name
    from onemind_core.netconf import NetSettings

    tls, f = tmp_path / "tls", tmp_path / "hostname"
    net = NetSettings(box_name="oldbox", hostname_file=f)
    first = BoxCA(tls, net.tls_box(tls)).ensure_https_cert()
    ca_pem = (tls / "ca.crt").read_bytes()
    _verify(first.cert_path.read_bytes(), ca_pem, "oldbox.local")
    assert existing_box_name(tls) == "oldbox"

    f.write_text("kitchen\n")  # the owner renamed the box
    assert net.box() == "kitchen" and net.tls_box(tls) == "oldbox"
    after = BoxCA(tls, net.tls_box(tls)).ensure_https_cert()  # what serve.https_cert does on the restart
    assert (tls / "ca.crt").read_bytes() == ca_pem  # the CA is never replaced
    for name in ("oldbox.local", "onemind.local", "files.oldbox.local"):
        _verify(after.cert_path.read_bytes(), ca_pem, name)
    assert not any("kitchen" in n for n in after.dns_names)
    # With the new name the old code issued kitchen.local, which no strict client accepts under this CA.
    bad = BoxCA(tls, "kitchen")
    with pytest.raises(ValueError):
        bad.issue("bad", ["kitchen.local"])
    # The certificate does not flip between name sets across restarts, whichever box name the caller starts from.
    again = BoxCA(tls, existing_box_name(tls) or "onemind").ensure_https_cert()
    assert sorted(again.dns_names) == sorted(after.dns_names)
    assert after.not_after == again.not_after  # unchanged, not re-issued


def test_before_a_ca_exists_the_tls_name_is_the_box_name(tmp_path):
    from onemind_core.netconf import NetSettings

    f = tmp_path / "hostname"
    f.write_text("kitchen\n")
    assert NetSettings(box_name="onemind", hostname_file=f).tls_box(tmp_path / "tls") == "kitchen"
