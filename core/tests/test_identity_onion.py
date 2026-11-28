# SPDX-License-Identifier: Apache-2.0
"""The sign-in accepts this box's own .onion address as a WebAuthn origin (NET-TOR-01, #284)."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.identity.service import IdentityService
from onemind_core.identity.settings import IdentitySettings

ONION = "a" * 55 + "b" + ".onion"


def rp(host: str, **cfg):
    svc = SimpleNamespace(cfg=IdentitySettings(**cfg))
    request = SimpleNamespace(headers={"host": host}, url=SimpleNamespace(hostname=host.split(":")[0]))
    return IdentityService.rp(svc, request)


def test_onion_host_is_the_relying_party_over_http():
    rp_id, origins = rp(ONION)
    assert rp_id == ONION
    assert f"http://{ONION}" in origins and f"https://{ONION}" in origins


def test_onion_host_with_port():
    assert f"http://{ONION}:8080" in rp(f"{ONION}:8080")[1]


def test_plain_http_stays_refused_for_other_names():
    for host in ("box.example.com", "onemind.local"):
        assert not [o for o in rp(host)[1] if o.startswith("http://")], host


def test_only_well_formed_v3_onion_addresses():
    for host in ("short.onion", "a" * 16 + ".onion", ("a" * 56 + ".onion.evil.com"), "A" * 56 + ".onion",
                 "1" * 56 + ".onion"):
        assert not [o for o in rp(host)[1] if o.startswith("http://")], host


def test_configured_origins_still_win():
    assert rp(ONION, origins=("https://box.example.com",))[1] == ["https://box.example.com"]



# ---- through the real routes: what an owner can and cannot do over the onion origin ---------------
def test_owner_with_a_lan_passkey_over_onion_needs_totp(settings, clock, executor):
    """Pins the known limit (review of #335): a passkey belongs to one relying party, so the LAN
    passkey does not work on the onion origin, and registering an onion passkey is refused. Password plus TOTP works."""
    from onemind_core.identity.crypto import totp_code
    from test_identity import LOCAL_PEER, PASSWORD, SoftAuthenticator, csrf, setup_owner
    from test_identity_signin import enable_totp

    cfg = IdentitySettings(cookie_secure=False)
    app = create_app(dataclasses.replace(settings, sections={**settings.sections, "identity": cfg}),
                     clock=clock, executor=executor)
    lan_host = "onemind.local"
    key = SoftAuthenticator(rp_id=lan_host, origin=f"https://{lan_host}")
    with TestClient(app, base_url=f"https://{lan_host}", client=LOCAL_PEER) as lan, \
            TestClient(app, base_url=f"http://{ONION}", client=LOCAL_PEER) as tor:
        setup_owner(lan)
        opts = lan.post("/v1/auth/passkeys/register/options", headers=csrf(lan)).json()
        assert lan.post("/v1/auth/passkeys/register", headers=csrf(lan),
                        json={"credential": key.register(opts), "label": "laptop"}).status_code == 201

        denied = tor.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
        assert denied.status_code == 401 and denied.json()["reason"] == "remote_factor_required"
        secret = enable_totp(lan, clock)
        body = {"username": "zeus", "password": PASSWORD, "totp": totp_code(secret, int(clock.now.timestamp()) // 30)}
        assert tor.post("/v1/auth/login", json=body).status_code == 200
        # ... but the LAN passkey does not (different relying party)
        o = tor.post("/v1/auth/login/options").json()
        assert o["publicKey"]["rpId"] == ONION
        assert TestClient(app, base_url=f"http://{ONION}").post(
            "/v1/auth/login", json={"passkey": key.assert_(o["publicKey"]["challenge"])}).status_code == 401
        # ... and an onion passkey cannot be added at all yet
        r = tor.post("/v1/auth/passkeys/register/options", headers=csrf(tor))
        assert r.status_code == 403 and "passkey_enrolment_unavailable_on_onion" in r.text, r.text


def test_owner_without_a_passkey_cannot_enrol_one_over_onion(settings, clock, executor):
    """Review of #335: the first passkey needs no step-up, so without a guard an owner could register
    an onion-bound key over Tor. That flips passkeys_active() for the whole box and locks LAN
    approvals (the onion key cannot assert on the LAN origin). Registration is refused on onion
    origins until the owner-approved enrolment design lands; the LAN stays unaffected."""
    from onemind_core.identity.crypto import totp_code
    from test_identity import LOCAL_PEER, PASSWORD, SoftAuthenticator, csrf, setup_owner
    from test_identity_signin import enable_totp

    cfg = IdentitySettings(cookie_secure=False)
    app = create_app(dataclasses.replace(settings, sections={**settings.sections, "identity": cfg}),
                     clock=clock, executor=executor)
    lan_host = "onemind.local"
    with TestClient(app, base_url=f"https://{lan_host}", client=LOCAL_PEER) as lan, \
            TestClient(app, base_url=f"http://{ONION}", client=LOCAL_PEER) as tor:
        setup_owner(lan)
        secret = enable_totp(lan, clock)
        body = {"username": "zeus", "password": PASSWORD, "totp": totp_code(secret, int(clock.now.timestamp()) // 30)}
        assert tor.post("/v1/auth/login", json=body).status_code == 200

        r = tor.post("/v1/auth/passkeys/register/options", headers=csrf(tor))
        assert r.status_code == 403 and "passkey_enrolment_unavailable_on_onion" in r.text, r.text
        # a ceremony started elsewhere cannot be completed on the onion origin either
        opts = lan.post("/v1/auth/passkeys/register/options", headers=csrf(lan)).json()
        key = SoftAuthenticator(rp_id=ONION, origin=f"http://{ONION}")
        r = tor.post("/v1/auth/passkeys/register", headers=csrf(tor),
                     json={"credential": key.register(opts), "label": "tor"})
        assert r.status_code == 403 and "passkey_enrolment_unavailable_on_onion" in r.text, r.text

        # the LAN can still enrol its first passkey, so approvals are not locked
        lkey = SoftAuthenticator(rp_id=lan_host, origin=f"https://{lan_host}")
        opts = lan.post("/v1/auth/passkeys/register/options", headers=csrf(lan)).json()
        assert lan.post("/v1/auth/passkeys/register", headers=csrf(lan),
                        json={"credential": lkey.register(opts), "label": "laptop"}).status_code == 201
