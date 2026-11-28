# SPDX-License-Identifier: Apache-2.0
"""Verification levels (D-028; gateway permissions design 3.11, PR 11): attestation at enrolment, the
level each approval needs, the owner-editable table with its floor, trusted key models, and the
body-bound step-up for owner changes at L2. Runs the real WebAuthn verification (py_webauthn)."""

from __future__ import annotations

import hashlib
import json
import struct
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import cbor2
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from conftest import OWNER, action_body
from onemind_core.app import create_app
from onemind_core.ca import MESH_NETS
from onemind_core.identity.crypto import b64url, totp_code
from test_identity import (
    LOCAL_PEER,
    PASSWORD,
    SoftAuthenticator,
    audit_events,
    box_code,
    csrf,
    enrol,
    id_settings,
    new_session_client,
    register_passkey,
    setup_owner,
)

BIO_AAGUID = "a1b2c3d4-0000-4000-8000-00000000b10e"  # a made-up model id for the test root
PIN_AAGUID = "a1b2c3d4-0000-4000-8000-0000000000a1"
AAGUID_OID = x509.ObjectIdentifier("1.3.6.1.4.1.45724.1.1.4")


def _name(cn: str, ou: str | None = None) -> x509.Name:
    attrs = [x509.NameAttribute(NameOID.COUNTRY_NAME, "US"), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test")]
    if ou:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, ou))
    return x509.Name([*attrs, x509.NameAttribute(NameOID.COMMON_NAME, cn)])


class FakeRoot:
    """A test attestation CA standing in for a vendor root from FIDO MDS."""

    def __init__(self, cn: str = "Test Attestation Root"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(UTC)
        self.cert = (x509.CertificateBuilder().subject_name(_name(cn)).issuer_name(_name(cn))
                     .public_key(self.key.public_key()).serial_number(x509.random_serial_number())
                     .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                     .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                     .sign(self.key, hashes.SHA256()))
        self.pem = self.cert.public_bytes(serialization.Encoding.PEM).decode()

    def leaf(self, key, aaguid: str) -> bytes:
        now = datetime.now(UTC)
        ext = x509.UnrecognizedExtension(AAGUID_OID, b"\x04\x10" + bytes.fromhex(aaguid.replace("-", "")))
        cert = (x509.CertificateBuilder().subject_name(_name("Test Key", "Authenticator Attestation"))
                .issuer_name(self.cert.subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(ext, critical=False).sign(self.key, hashes.SHA256()))
        return cert.public_bytes(serialization.Encoding.DER)


class AttestedAuthenticator(SoftAuthenticator):
    """A software security key that sends "packed" attestation signed by a test root."""

    def __init__(self, root: FakeRoot | None, aaguid: str = BIO_AAGUID, synced: bool = False,
                 fmt: str = "packed", claimed_aaguid: str | None = None):
        super().__init__()
        self.root, self.aaguid, self.synced, self.fmt = root, aaguid, synced, fmt
        self.claimed = claimed_aaguid or aaguid  # the AAGUID written into authenticatorData
        self.att_key = ec.generate_private_key(ec.SECP256R1())

    def register(self, options: dict) -> dict:
        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        flags = 0x45 | (0x18 if self.synced else 0)  # UP, UV, AT (+ BE, BS when synced)
        auth_data = (hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", 0)
                     + bytes.fromhex(self.claimed.replace("-", "")) + struct.pack(">H", len(self.cred_id))
                     + self.cred_id + cose)
        cd = self._client_data("webauthn.create", options["publicKey"]["challenge"])
        if self.fmt == "packed":
            stmt: dict = {"alg": -7}
            if self.root is None:  # self attestation: signed by the credential key, proves no model
                stmt["sig"] = self.key.sign(auth_data + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
            else:
                stmt["sig"] = self.att_key.sign(auth_data + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
                stmt["x5c"] = [self.root.leaf(self.att_key, self.aaguid)]
        else:  # a format py_webauthn does not know (e.g. a newer one): it must still enrol, at L1
            stmt = {"whatever": b"\x00"}
        att = cbor2.dumps({"fmt": self.fmt, "attStmt": stmt, "authData": auth_data})
        return {"id": b64url(self.cred_id), "rawId": b64url(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64url(cd), "attestationObject": b64url(att), "transports": ["usb"]}}

    def assert_(self, challenge: str, flat: bool = False) -> dict:
        out = super().assert_(challenge, flat)
        if self.synced:  # keep BE/BS on every assertion, as a synced passkey does
            body = out if flat else out["response"]
            from onemind_core.identity.crypto import unb64url

            ad = bytearray(unb64url(body["authenticatorData"]))
            ad[32] |= 0x18
            cd = unb64url(body["clientDataJSON"])
            body["authenticatorData"] = b64url(bytes(ad))
            body["signature"] = b64url(self.key.sign(bytes(ad) + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256())))
        return out


@pytest.fixture
def root():
    return FakeRoot()


@pytest.fixture
def lvc(settings, clock, executor, tmp_path, root):
    """A gateway whose shipped allow-list trusts the test root for a biometric model and a PIN-only one."""
    allow = tmp_path / "allowlist.json"
    allow.write_text(json.dumps({"version": 1, "entries": [
        {"kind": "fido_aaguid", "aaguid": BIO_AAGUID, "name": "Test Bio Key", "roots": [root.pem],
         "user_verification": ["fingerprint_internal", "passcode_internal"]},
        {"kind": "fido_aaguid", "aaguid": PIN_AAGUID, "name": "Test PIN Key", "roots": [root.pem],
         "user_verification": ["passcode_internal"]},
    ]}))
    with TestClient(create_app(id_settings(settings, allowlist_file=allow), clock=clock, executor=executor),
                    client=LOCAL_PEER) as c:
        add_wipe_type(c)
        yield c


def add_wipe_type(c: TestClient) -> None:
    """A destructive (T3) feature type, standing in for backup.restore over live data."""
    from pydantic import BaseModel

    from onemind_core.actions import FeatureAction
    from onemind_core.executors import ExecResult

    class WipeParams(BaseModel):
        target: str

    c.app.state.gateway.actions.register_type("test.wipe", FeatureAction(
        "destructive", lambda a, finish: finish(ExecResult("succeeded", "wiped")), frozenset({"person"}),
        params_model=WipeParams))
    c.app.state.gateway.actions.register_type("test.reversible", FeatureAction(
        "write", lambda a, finish: finish(ExecResult("succeeded", "changed")), frozenset({"person"}),
        params_model=WipeParams))


def keys(c: TestClient) -> dict:
    return {k["label"]: k for k in c.get("/v1/auth/passkeys").json()}


def add_key(c: TestClient, auth, label: str, grant: str | None = None, at_box: bool = True) -> dict:
    """Register with a step-up grant when the owner already holds a proven key. at_box: the person reads
    the code the box's screen shows (N-1 b: the household's first proven key is added at the box)."""
    h = {**csrf(c), **({"OneMind-Step-Up": grant} if grant else {})}
    opts = c.post("/v1/auth/passkeys/register/options", headers=h)
    assert opts.status_code == 200, opts.text
    assert opts.json()["publicKey"]["attestation"] == "direct"
    body = {"credential": auth.register(opts.json()), "label": label}
    if at_box and opts.json()["box_code_if_proven"]:
        body["box_code"] = box_code(c)
    r = c.post("/v1/auth/passkeys/register", json=body, headers=csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


def grant(c: TestClient, auth, op: str, target: str = "", body: dict | None = None, at_box: bool = False) -> str:
    """A step-up grant; when the hub asks for the box's code (the grace), the person at the box types it."""
    opts = c.post("/v1/auth/step-up/options", json={"op": op, "target": target, "body": body or {}, "at_box": at_box},
                  headers=csrf(c))
    assert opts.status_code == 200, opts.text
    sent = {"credential": auth.assert_(opts.json()["publicKey"]["challenge"])}
    if opts.json()["box_code_required"]:
        sent["box_code"] = box_code(c)
    r = c.post("/v1/auth/step-up", json=sent, headers=csrf(c))
    assert r.status_code == 200, r.text
    return r.json()["step_up"]


def file_action(c: TestClient, clock, type_: str, params: dict, key: str) -> str:
    r = c.post("/v1/actions", json={**action_body(clock, type_=type_, key=key), "params": params}, headers=csrf(c))
    assert r.status_code in (201, 202), r.text
    return r.json()["id"]


def approve(c: TestClient, aid: str, auth, at_box: bool = True) -> object:
    """Approve with a passkey; at_box: also type the code the box's screen shows when the hub asks (grace)."""
    opts = c.post(f"/v1/actions/{aid}/approve-options", headers=csrf(c))
    if opts.status_code != 200:
        return opts
    body = {"webauthn": auth.assert_(opts.json()["challenge"], flat=True)}
    if at_box and opts.json()["box_code_required"]:
        body["box_code"] = box_code(c)
    return c.post(f"/v1/actions/{aid}/approve", json=body, headers=csrf(c))


# ---- enrolment: what each kind of key proves ------------------------------------------------------
def test_attested_biometric_key_is_l2_and_a_none_passkey_is_l1(lvc, root, settings):
    setup_owner(lvc)
    phone = SoftAuthenticator()  # attestation "none", like an iCloud or Google passkey
    out = add_key(lvc, phone, "phone")
    assert out["level"] == "L1" and out["level_reason"] == "no_attestation"
    assert "can't prove its make and model" in out["explanation"]
    key = AttestedAuthenticator(root)
    out = add_key(lvc, key, "bio key")
    assert out["level"] == "L2" and out["level_reason"] == "proven"
    listed = keys(lvc)
    assert listed["bio key"]["model"] == "Test Bio Key" and listed["bio key"]["device_bound"] is True
    assert listed["phone"]["level"] == "L1" and listed["phone"]["model"] is None
    ev = [e for e in audit_events(settings) if e["event"] == "auth.passkey.registered"]
    assert {e["data"]["payload"]["level"] for e in ev} == {"L1", "L2"}
    # OneMind stores no biometric data: only the model id, format, chain digest, flags and level.
    assert not any("fingerprint" in json.dumps(e) for e in ev)


@pytest.mark.parametrize("make,reason", [
    (lambda root: AttestedAuthenticator(root, synced=True), "synced"),
    (lambda root: AttestedAuthenticator(FakeRoot("Someone Else")), "chain_untrusted"),
    (lambda root: AttestedAuthenticator(root, aaguid=PIN_AAGUID), "not_biometric_capable"),
    (lambda root: AttestedAuthenticator(root, aaguid="a1b2c3d4-0000-4000-8000-00000000ffff"), "model_not_trusted"),
    (lambda root: AttestedAuthenticator(None), "no_attestation"),  # packed self attestation
    (lambda root: AttestedAuthenticator(root, fmt="compound-v9"), "no_attestation"),  # unknown format
    # a trusted model's certificate, but authenticatorData claims the biometric model
    (lambda root: AttestedAuthenticator(root, aaguid=PIN_AAGUID, claimed_aaguid=BIO_AAGUID), "chain_untrusted"),
])
def test_keys_that_cannot_prove_a_proven_key_still_enrol_at_l1(lvc, root, make, reason):
    setup_owner(lvc)
    out = add_key(lvc, make(root), "key")
    assert (out["level"], out["level_reason"]) == ("L1", reason)


# ---- approvals --------------------------------------------------------------------------------------
def test_grace_until_the_first_proven_key_then_l1_cannot_approve_t3(lvc, root, clock):
    setup_owner(lvc)
    phone = SoftAuthenticator()
    add_key(lvc, phone, "phone")
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "t3a")
    opts = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()
    # No proven key yet (N-1 = b): L2 is eased to L1 plus the code on the box's own screen, and the answer
    # says so. The code itself is never in an API answer.
    assert (opts["required_level"], opts["grace"], opts["decided_by"]) == ("L1", True, "tier.T3")
    assert opts["box_code_required"] is True and box_code(lvc) not in json.dumps(opts)
    assert lvc.get(f"/v1/actions/{aid}").json()["required_level"] == "L2"  # the card says what remote needs
    bio = AttestedAuthenticator(root)
    add_key(lvc, bio, "bio")  # the household's first proven key: the grace ends
    opts = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()
    assert (opts["required_level"], opts["grace"]) == ("L2", False)
    assert [c["id"] for c in opts["publicKey"]["allowCredentials"]] == [b64url(bio.cred_id)]
    # An L1 key's assertion is refused even if a client offers it anyway.
    r = lvc.post(f"/v1/actions/{aid}/approve", json={"webauthn": phone.assert_(opts["challenge"], flat=True)},
                 headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    assert lvc.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"
    r = approve(lvc, aid, bio)
    assert r.status_code == 200, r.text
    # Everyday approvals stay L1: the phone approves an install.
    aid2 = file_action(lvc, clock, "app.install", {"app_id": "uptime-kuma"}, "t2a")
    assert approve(lvc, aid2, phone).status_code == 200


def test_owner_with_only_l1_keys_is_told_plainly_when_strict(settings, clock, executor, root, tmp_path):
    s = id_settings(settings, l2_grace=False)
    with TestClient(create_app(s, clock=clock, executor=executor), client=LOCAL_PEER) as c:
        add_wipe_type(c)
        setup_owner(c)
        add_key(c, SoftAuthenticator(), "phone")
        aid = file_action(c, clock, "test.wipe", {"target": "photos"}, "t3s")
        r = c.post(f"/v1/actions/{aid}/approve-options", headers=csrf(c))
        assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet"
        assert "proven key" in r.json()["message"]


def test_a_synced_attested_key_is_capped_at_l1(lvc, root, clock):
    setup_owner(lvc)
    synced = AttestedAuthenticator(root, synced=True)
    assert add_key(lvc, synced, "synced")["level"] == "L1"
    bio = AttestedAuthenticator(root)
    add_key(lvc, bio, "bio", grant=None)
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "t3b")
    opts = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()
    assert b64url(synced.cred_id) not in [c["id"] for c in opts["publicKey"]["allowCredentials"]]


def test_device_approver_key_cannot_approve_an_l2_action(lvc, root, clock):
    setup_owner(lvc)
    add_key(lvc, AttestedAuthenticator(root), "bio")
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "t3c")
    opts = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()
    body = {"device_signature": {"key_id": "apk_x", "challenge": opts["challenge"], "signature": "AA"}}
    r = lvc.post(f"/v1/actions/{aid}/approve", json=body, headers=csrf(lvc))
    assert r.status_code == 401 and "proven key" in r.json()["message"]


# ---- the owner-editable table -----------------------------------------------------------------------
def test_table_edits_go_through_the_queue_at_l2_and_keep_the_floor(lvc, root, clock, settings):
    setup_owner(lvc)
    phone, bio = SoftAuthenticator(), AttestedAuthenticator(root)
    add_key(lvc, phone, "phone")
    add_key(lvc, bio, "bio")
    table = lvc.get("/v1/verification-requirements").json()
    rows = {r["key"]: r for r in table["rows"]}
    assert rows["tier.T3"]["current"] == "L2" and rows["tier.P"]["minimum"] == "L2"
    assert rows["data.access"]["maximum"] == "L1" and table["grace"] is False
    assert table["household_level"] == "L2"
    for key, level, reason in [("tier.P", "L1", "below_floor"), ("security.settings", "L1", "below_floor"),
                               ("verification.table", "L1", "below_floor"), ("data.access", "L2", "above_ceiling"),
                               ("type:no.such", "L2", "unknown_row")]:
        r = lvc.post("/v1/actions", json={**action_body(clock, type_="verification.requirement.set", key=key + level),
                                          "params": {"key": key, "level": level}}, headers=csrf(lvc))
        assert r.status_code == 422 and r.json()["reason"] == reason, (key, r.text)
    r = lvc.post("/v1/actions", json={**action_body(clock, type_="verification.requirement.set", key="l3"),
                                      "params": {"key": "type:backup.restore", "level": "L3"}}, headers=csrf(lvc))
    assert r.status_code == 409 and r.json()["reason"] == "level_unreachable"
    # Lowering T3 to L1 (N-3 = a) is allowed, but only an L2 key approves the change.
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "tier.T3", "level": "L1"}, "edit1")
    assert lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()["required_level"] == "L2"
    r = approve(lvc, aid, phone)
    assert r.status_code == 401
    assert approve(lvc, aid, bio).status_code == 200
    rows = {r["key"]: r for r in lvc.get("/v1/verification-requirements").json()["rows"]}
    assert rows["tier.T3"]["current"] == "L1"
    ev = [e for e in audit_events(settings) if e["event"] == "verification.requirement.changed"]
    assert ev and {"key": "tier.T3", "from": "L2", "to": "L1"}.items() <= ev[-1]["data"]["payload"].items()
    # A per-type opt-in only raises: app.install now needs the proven key.
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "type:app.install", "level": "L2"}, "edit2")
    assert approve(lvc, aid, bio).status_code == 200
    aid = file_action(lvc, clock, "app.install", {"app_id": "uptime-kuma"}, "inst")
    opts = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()
    assert (opts["required_level"], opts["decided_by"]) == ("L2", "type:app.install")


def test_only_owners_read_and_request_table_changes(lvc, clock):
    setup_owner(lvc)
    adult = enrol(lvc, "adult", "ana")
    assert adult.get("/v1/verification-requirements").status_code == 403
    r = adult.post("/v1/actions", json={**action_body(clock, type_="verification.requirement.set", key="x"),
                                        "params": {"key": "tier.T1", "level": "L2"}}, headers=csrf(adult))
    assert r.status_code == 403
    assert adult.get("/v1/auth/authenticator-allowlist").status_code == 403


# ---- trusted key models -------------------------------------------------------------------------------
def test_owner_adds_a_trusted_model_at_l2_and_removing_it_drops_keys_to_l1(settings, clock, executor, root):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor),
                    client=LOCAL_PEER) as c:
        setup_owner(c)
        bio = AttestedAuthenticator(root)
        assert add_key(c, bio, "bio")["level_reason"] == "model_not_trusted"  # nothing shipped yet
        params = {"aaguid": BIO_AAGUID, "name": "Test Bio Key", "roots": [root.pem],
                  "user_verification": ["fingerprint_internal"]}
        bad = c.post("/v1/actions", json={**action_body(clock, type_="authenticator.allowlist.add", key="bad"),
                                          "params": {**params, "roots": [_leaf_pem(root)]}}, headers=csrf(c))
        assert bad.status_code == 422 and bad.json()["reason"] == "invalid_root"
        aid = file_action(c, clock, "authenticator.allowlist.add", params, "m1")
        assert approve(c, aid, bio).status_code == 200  # grace: nobody holds a proven key yet
        models = c.get("/v1/auth/authenticator-allowlist").json()
        assert models[0]["source"] == "owner" and models[0]["biometric"] is True
        bio2 = AttestedAuthenticator(root)
        assert add_key(c, bio2, "bio2")["level"] == "L2"
        assert keys(c)["bio"]["level"] == "L1"  # enrolled before the model was trusted
        # bio2 is the household's only proven key: untrusting its model takes that key (or the box).
        r = c.delete(f"/v1/auth/authenticator-allowlist/{BIO_AAGUID}", headers=csrf(c))
        step = step_up_of(r)
        assert (step["op"], step["required_level"], step["box"]) == ("auth.trusted_models.remove", "L2", "alt")
        g = grant_from(c, bio2, step)
        r = c.delete(f"/v1/auth/authenticator-allowlist/{BIO_AAGUID}", headers={**csrf(c), "OneMind-Step-Up": g})
        assert r.status_code == 204, r.text
        listed = keys(c)["bio2"]
        assert (listed["level"], listed["level_reason"]) == ("L1", "model_not_trusted")
        # The grace never comes back: L2 actions now wait for a recovery path, not for an L1 key.
        table = c.get("/v1/verification-requirements").json()
        assert (table["grace"], table["recovery_needed"]) == (False, True)


# ---- the grace is one-way (review of #1184: the D-028 L2 bypass) ---------------------------------------
def test_an_l1_key_cannot_delete_the_last_proven_key_to_reopen_the_grace(lvc, root, clock):
    """The reviewer's repro: phone (L1) plus bio (L2); the phone deletes bio, then approves T3 with L1."""
    setup_owner(lvc)
    phone, bio = SoftAuthenticator(), AttestedAuthenticator(root)
    add_key(lvc, phone, "phone")
    add_key(lvc, bio, "bio")
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "t3x")
    assert lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()["required_level"] == "L2"
    bio_id = b64url(bio.cred_id)
    # Deleting the last proven key needs that key (L2); the phone can't even start the step-up remotely.
    step = step_up_of(lvc.delete(f"/v1/auth/passkeys/{bio_id}", headers=csrf(lvc)))
    assert (step["required_level"], step["box"]) == ("L2", "alt")
    opts = lvc.post("/v1/auth/step-up/options", json={"op": step["op"], "target": bio_id, "body": {}},
                    headers=csrf(lvc)).json()
    assert [k["id"] for k in opts["publicKey"]["allowCredentials"]] == [bio_id]
    r = lvc.post("/v1/auth/step-up", json={"credential": phone.assert_(opts["publicKey"]["challenge"])},
                 headers=csrf(lvc))
    assert r.status_code == 401
    # A grant the phone made for removing some other key does not stretch to this one.
    spare = SoftAuthenticator()
    add_key(lvc, spare, "spare", grant=grant(lvc, bio, "auth.passkeys.register"))
    other = grant(lvc, phone, "auth.passkeys.delete", b64url(spare.cred_id))
    r = lvc.delete(f"/v1/auth/passkeys/{bio_id}", headers={**csrf(lvc), "OneMind-Step-Up": other})
    assert r.status_code == 401
    assert keys(lvc)["bio"]["level"] == "L2"
    # The owner removes it with the key itself: allowed, and the grace stays over.
    g = grant(lvc, bio, "auth.passkeys.delete", bio_id)
    assert lvc.delete(f"/v1/auth/passkeys/{bio_id}", headers={**csrf(lvc), "OneMind-Step-Up": g}).status_code == 204
    table = lvc.get("/v1/verification-requirements").json()
    assert (table["grace"], table["recovery_needed"], table["household_level"]) == (False, True, "L1")
    r = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc))
    assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet"
    assert approve(lvc, aid, phone).status_code == 409
    assert lvc.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"
    # Removing the key does not lower the security setting's level. The home-network path adds a box code.
    share = {"roles": ["guest"], "people": [], "auth": None}
    step = step_up_of(lvc.put("/v1/apps/uptime-kuma/access", json=share, headers=csrf(lvc)))
    assert (step["required_level"], step["box"]) == ("L2", "alt")
    r = lvc.post("/v1/auth/step-up/options", json={k: step[k] for k in ("op", "target", "body")},
                 headers=csrf(lvc))
    assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet"


def test_a_lost_last_proven_key_is_revoked_at_the_box_and_a_new_one_enrolled_there(lvc, root, clock):
    """Revoking stays possible without the key (design 3.11): an owner at the box, then recovery at the box."""
    setup_owner(lvc)
    phone, lost = SoftAuthenticator(), AttestedAuthenticator(root)
    add_key(lvc, phone, "phone")
    add_key(lvc, lost, "lost")
    lost_id = b64url(lost.cred_id)
    # Remotely (no box code) the phone can't use the at-the-box path.
    opts = lvc.post("/v1/auth/step-up/options", json={"op": "auth.passkeys.delete", "target": lost_id, "body": {},
                                                      "at_box": True}, headers=csrf(lvc)).json()
    assert opts["box_code_required"] is True and opts["required_level"] == "L1"
    r = lvc.post("/v1/auth/step-up", json={"credential": phone.assert_(opts["publicKey"]["challenge"])},
                 headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "box_code_required"
    g = grant(lvc, phone, "auth.passkeys.delete", lost_id, at_box=True)  # at the box: reads the code
    assert lvc.delete(f"/v1/auth/passkeys/{lost_id}", headers={**csrf(lvc), "OneMind-Step-Up": g}).status_code == 204
    assert lvc.get("/v1/verification-requirements").json()["recovery_needed"] is True
    # Adding a key now needs L2, which nobody has: the interim recovery path is the box.
    step = step_up_of(lvc.post("/v1/auth/passkeys/register/options", headers=csrf(lvc)))
    assert (step["required_level"], step["box"]) == ("L1", "required")
    new = AttestedAuthenticator(root)
    assert add_key(lvc, new, "new", grant=grant_from(lvc, phone, step))["level"] == "L2"
    assert lvc.get("/v1/verification-requirements").json()["recovery_needed"] is False


def test_demoting_the_owner_who_holds_the_proven_key_does_not_reopen_the_grace(lvc, root, clock):
    setup_owner(lvc)
    add_key(lvc, AttestedAuthenticator(root), "bio")
    svc = lvc.app.state.identity
    assert svc.levels.latched()
    from onemind_core.identity.models import PasskeyRow

    svc.repo.delete(PasskeyRow, PasskeyRow.label == "bio")  # however the key goes away
    assert svc.levels.in_grace() is False
    assert svc.levels.effective(2, False) == (2, False)


# ---- the grace is at the box (N-1 = b) -------------------------------------------------------------------
def test_during_grace_a_remote_l1_key_cannot_approve_an_l2_action(lvc, clock, settings):
    setup_owner(lvc)
    phone = SoftAuthenticator()
    add_key(lvc, phone, "phone")
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "t3r")
    r = approve(lvc, aid, phone, at_box=False)
    assert r.status_code == 401 and r.json()["reason"] == "box_code_required"
    # A wrong code burns the challenge; the next try shows a new code.
    opts = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()
    shown = box_code(lvc)
    wrong = f"{(int(shown) + 1) % 10 ** 6:06d}"
    r = lvc.post(f"/v1/actions/{aid}/approve", json={"webauthn": phone.assert_(opts["challenge"], flat=True),
                                                     "box_code": wrong}, headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "box_code_required"
    assert lvc.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"
    # A phone approver key can't stand in either (it has no way to send the box's code).
    opts = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()
    body = {"device_signature": {"key_id": "apk_x", "challenge": opts["challenge"], "signature": "AA"}}
    r = lvc.post(f"/v1/actions/{aid}/approve", json=body, headers=csrf(lvc))
    assert r.status_code == 401 and "box" in r.json()["message"]
    # At the box it goes through.
    assert approve(lvc, aid, phone).status_code == 200
    ev = [e["data"]["payload"] for e in audit_events(settings) if e["event"] == "auth.step_up.succeeded"]
    assert ev[-1]["at_box"] is True and ev[-1]["grace"] is True
    assert any(e["event"] == "auth.box_code.failed" for e in audit_events(settings))


def test_wrong_box_codes_lock_the_box_confirmation_for_a_while(lvc, clock):
    setup_owner(lvc)
    phone = SoftAuthenticator()
    add_key(lvc, phone, "phone")
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "t3l")
    for _ in range(5):
        opts = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc)).json()
        lvc.post(f"/v1/actions/{aid}/approve", json={"webauthn": phone.assert_(opts["challenge"], flat=True),
                                                     "box_code": "000000" if box_code(lvc) != "000000" else "111111"},
                 headers=csrf(lvc))
    r = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc))
    assert r.status_code == 429 and r.json()["reason"] == "box_code_locked"
    clock.advance(16 * 60)  # the window passes (the request itself has expired by now): codes are made again
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "t3l2")
    r = approve(lvc, aid, phone)
    assert r.status_code == 200, r.text


def test_during_grace_an_l1_key_cannot_trust_a_model_remotely_to_make_itself_l2(settings, clock, executor, root):
    """The related hole: authenticator.allowlist.add approved by L1 would turn the approver's own key L2."""
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor),
                    client=LOCAL_PEER) as c:
        setup_owner(c)
        mine = AttestedAuthenticator(root)
        assert add_key(c, mine, "mine")["level_reason"] == "model_not_trusted"
        params = {"aaguid": BIO_AAGUID, "name": "Test Bio Key", "roots": [root.pem],
                  "user_verification": ["fingerprint_internal"]}
        aid = file_action(c, clock, "authenticator.allowlist.add", params, "m2")
        r = approve(c, aid, mine, at_box=False)
        assert r.status_code == 401 and r.json()["reason"] == "box_code_required"
        assert c.get("/v1/auth/authenticator-allowlist").json() == []
        assert approve(c, aid, mine).status_code == 200  # an owner at the box
        assert keys(c)["mine"]["level"] == "L1"  # enrolled before the model was trusted: it stays L1


def test_the_first_proven_key_is_added_at_the_box(lvc, root):
    setup_owner(lvc)
    add_key(lvc, SoftAuthenticator(), "phone")
    bio = AttestedAuthenticator(root)
    opts = lvc.post("/v1/auth/passkeys/register/options", headers=csrf(lvc)).json()
    assert opts["box_code_if_proven"] is True
    r = lvc.post("/v1/auth/passkeys/register", json={"credential": bio.register(opts), "label": "bio"},
                 headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "box_code_required"
    assert "bio" not in keys(lvc) and lvc.get("/v1/verification-requirements").json()["grace"] is True
    # Another phone passkey (L1) still enrols remotely, without the code.
    assert add_key(lvc, SoftAuthenticator(), "laptop", at_box=False)["level"] == "L1"
    assert add_key(lvc, AttestedAuthenticator(root), "bio")["level"] == "L2"


def test_an_adults_proven_key_needs_no_box_code(lvc, root):
    """Only owners' keys set the household's level, so an adult enrols a proven key without the box."""
    from test_identity import enrol

    setup_owner(lvc)
    lvc.passkey = SoftAuthenticator()  # stepped() confirms adding the person at the box with it
    add_key(lvc, lvc.passkey, "phone")
    adult = enrol(lvc, "adult", "ana")
    opts = adult.post("/v1/auth/passkeys/register/options", headers=csrf(adult)).json()
    assert opts["box_code_if_proven"] is False
    r = adult.post("/v1/auth/passkeys/register", json={"credential": AttestedAuthenticator(root).register(opts),
                                                        "label": "ana key"}, headers=csrf(adult))
    assert r.status_code == 201 and r.json()["level"] == "L2", r.text
    assert lvc.get("/v1/verification-requirements").json()["grace"] is True  # still no owner proven key


def test_a_box_without_a_screen_waits_for_a_proven_key(settings, clock, executor):
    with TestClient(create_app(id_settings(settings, box_code_file=None), clock=clock, executor=executor),
                    client=LOCAL_PEER) as c:
        add_wipe_type(c)
        setup_owner(c)
        add_key(c, SoftAuthenticator(), "phone")
        aid = file_action(c, clock, "test.wipe", {"target": "photos"}, "t3n")
        r = c.post(f"/v1/actions/{aid}/approve-options", headers=csrf(c))
        assert r.status_code == 409 and r.json()["reason"] == "box_presence_unavailable"
        assert c.get("/v1/verification-requirements").json()["box_confirm"] is False


def test_an_approved_l3_edit_is_judged_again_when_no_key_reaches_l3(lvc, root, clock):
    setup_owner(lvc)
    add_key(lvc, bio := AttestedAuthenticator(root), "bio")
    svc = lvc.app.state.identity
    from onemind_core.identity.models import PasskeyRow

    bio_id = b64url(bio.cred_id)
    svc.repo.update(PasskeyRow, [PasskeyRow.id == bio_id], {"level": "L3"})  # a future L3 device
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "type:app.install", "level": "L3"}, "l3")
    svc.repo.update(PasskeyRow, [PasskeyRow.id == bio_id], {"level": "L2"})  # gone before the approval
    r = approve(lvc, aid, bio)
    assert r.status_code == 409 and "L3" in r.json()["message"], r.text
    assert lvc.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"


def _leaf_pem(root: FakeRoot) -> str:
    der = root.leaf(ec.generate_private_key(ec.SECP256R1()), BIO_AAGUID)
    return x509.load_der_x509_certificate(der).public_bytes(serialization.Encoding.PEM).decode()


# ---- body-bound step-up for owner changes (gap 20) ------------------------------------------------------
def test_security_setting_with_an_l1_key_needs_a_body_bound_l2_step_up(lvc, root):
    setup_owner(lvc)
    phone, bio = SoftAuthenticator(), AttestedAuthenticator(root)
    add_key(lvc, phone, "phone")
    add_key(lvc, bio, "bio")
    share = {"roles": ["guest"], "people": [], "auth": None}
    # A fresh passkey sign-in (the 5-minute window) is not enough for an L2 row.
    r = lvc.put("/v1/apps/uptime-kuma/access", json=share, headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required" and "L2" in r.json()["message"]
    # The phone can't even start the step-up: only proven keys are offered.
    opts = lvc.post("/v1/auth/step-up/options", json={"op": "apps.access.set", "target": "uptime-kuma", "body": share},
                    headers=csrf(lvc)).json()
    assert [k["id"] for k in opts["publicKey"]["allowCredentials"]] == [b64url(bio.cred_id)]
    r = lvc.post("/v1/auth/step-up", json={"credential": phone.assert_(opts["publicKey"]["challenge"])},
                 headers=csrf(lvc))
    assert r.status_code == 401
    # A grant made for a different body is refused, and a grant is single use.
    other = grant(lvc, bio, "apps.access.set", "uptime-kuma", {**share, "roles": ["child"]})
    r = lvc.put("/v1/apps/uptime-kuma/access", json=share, headers={**csrf(lvc), "OneMind-Step-Up": other})
    assert r.status_code == 401
    g = grant(lvc, bio, "apps.access.set", "uptime-kuma", share)
    assert lvc.put("/v1/apps/uptime-kuma/access", json=share, headers={**csrf(lvc), "OneMind-Step-Up": g}).status_code == 200
    share2 = {"roles": ["guest", "child"], "people": [], "auth": None}
    r = lvc.put("/v1/apps/uptime-kuma/access", json=share2, headers={**csrf(lvc), "OneMind-Step-Up": g})
    assert r.status_code == 401


def test_adding_a_key_needs_a_proven_key_once_one_exists(lvc, root, clock):
    setup_owner(lvc)
    bio = AttestedAuthenticator(root)
    add_key(lvc, bio, "bio")
    r = lvc.post("/v1/auth/passkeys/register/options", headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    add_key(lvc, SoftAuthenticator(), "phone", grant=grant(lvc, bio, "auth.passkeys.register"))


def test_the_motion_lockout_stays_strict_without_a_proven_key(lvc, monkeypatch):
    setup_owner(lvc)
    phone = SoftAuthenticator()
    add_key(lvc, phone, "phone")
    path = "/v1/physical/lockout"
    body = {"locked": False, "reason": None}
    assert lvc.put(path, json={"locked": True}, headers=csrf(lvc)).status_code == 200
    locked = lvc.get(path).json()
    r = lvc.put(path, json=body, headers=csrf(lvc))
    assert step_up_of(r)["box"] is None
    for explicit in ({}, {"at_box": True}):
        r = lvc.post("/v1/auth/step-up/options", json={"op": "physical.lockout.set", "body": body, **explicit},
                     headers=csrf(lvc))
        assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet", r.text

    # An outstanding grant issued under the old rule cannot turn off the lockout either.
    with monkeypatch.context() as old:
        old.setattr(lvc.app.state.identity, "_op_rule", lambda *a, **kw: (2, "alt"))
        issued = grant(lvc, phone, "physical.lockout.set", body=body, at_box=True)
    refused = lvc.put(path, json=body, headers={**csrf(lvc), "OneMind-Step-Up": issued})
    assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
    assert lvc.get(path).json() == locked


def test_grace_keeps_l1_owner_changes_working_at_the_box_and_says_so(lvc, settings):
    setup_owner(lvc)
    phone = SoftAuthenticator()
    add_key(lvc, phone, "phone")  # fresh passkey proof on this session
    body = {"display_name": "B", "role": "adult"}
    # N-1 = b: the fresh sign-in alone is not enough for an L2 row during the grace; the box must confirm.
    step = step_up_of(lvc.post("/v1/users", json=body, headers=csrf(lvc)))
    assert (step["required_level"], step["box"]) == ("L1", "required")
    g = grant_from(lvc, phone, step)
    assert lvc.post("/v1/users", json=body, headers={**csrf(lvc), "OneMind-Step-Up": g}).status_code == 201
    table = lvc.get("/v1/verification-requirements").json()
    assert (table["grace"], table["recovery_needed"], table["box_confirm"]) == (True, False, True)


def test_the_session_records_which_key_stepped_up(lvc, root):
    setup_owner(lvc)
    bio = AttestedAuthenticator(root)
    add_key(lvc, bio, "bio")
    other = new_session_client(lvc)
    opts = other.post("/v1/auth/login/options").json()
    assert other.post("/v1/auth/login", json={"passkey": bio.assert_(opts["publicKey"]["challenge"])}).status_code == 200
    svc = lvc.app.state.identity
    from sqlalchemy import select

    from onemind_core.identity.models import SessionRow

    rows = svc.repo.all(select(SessionRow).where(SessionRow.auth_method == "passkey"))
    assert [r.step_up_credential_id for r in rows] == [b64url(bio.cred_id)]


def test_shipped_allowlist_is_valid_and_empty_until_the_mds_seed():
    from onemind_core.identity import levels as lv

    doc = json.loads(lv.SHIPPED_ALLOWLIST.read_text())
    assert doc["version"] == 1 and doc["entries"] == []
    assert lv.load_file(lv.SHIPPED_ALLOWLIST) == []


def test_every_step_up_row_and_type_row_is_a_real_row():
    from onemind_core.identity import levels as lv

    assert set(lv.STEP_UP_ROWS.values()) <= set(lv.ROWS)
    assert set(lv.TYPE_ROWS.values()) <= set(lv.ROWS)
    for key, row in lv.ROWS.items():
        assert lv.rank(row.minimum) <= lv.rank(row.default) <= lv.rank(row.maximum), key
    assert lv.ROWS["data.access"].maximum == "L1"  # data access never depends on a strong key (B-4)


# ---- the step-up a client makes in place (review of #1184) -------------------------------------------------
def step_up_of(r) -> dict:
    """The step-up a 401 names in details, as a client reads it after a JSON round trip."""
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    (d,) = [x["step_up"] for x in r.json()["details"] if "step_up" in x]
    return json.loads(json.dumps(d))


def grant_from(c: TestClient, auth, step: dict) -> str:
    return grant(c, auth, step["op"], step["target"], step["body"])


def test_the_401_names_the_step_up_so_any_client_can_finish_the_change(lvc, root):
    setup_owner(lvc)
    bio = AttestedAuthenticator(root)
    add_key(lvc, bio, "bio")  # the grace is over: owner changes need a body-bound L2 step-up
    cases = [
        ("post", "/v1/users", {"display_name": "Bea", "role": "adult"}),
        ("put", "/v1/apps/uptime-kuma/access", {"roles": ["guest"], "people": []}),
    ]
    for method, path, body in cases:
        r = getattr(lvc, method)(path, json=body, headers=csrf(lvc))
        step = step_up_of(r)
        assert step["required_level"] == "L2" and step["op"] in ("users.create", "apps.access.set")
        g = grant_from(lvc, bio, step)  # the client sends back exactly what it was given
        r = getattr(lvc, method)(path, json=body, headers={**csrf(lvc), "OneMind-Step-Up": g})
        assert r.status_code in (200, 201), r.text
    # A used grant names the step-up again, so a client can retry once more and no further.
    r = lvc.put("/v1/apps/uptime-kuma/access", json={"roles": ["guest", "child"], "people": []},
                headers={**csrf(lvc), "OneMind-Step-Up": g})
    assert step_up_of(r)["body"]["roles"] == ["guest", "child"]


def test_the_step_up_digest_is_pinned():
    from onemind_core.identity.service import IdentityService as S

    # create_user binds {display_name, role, username}; a client never rebuilds it, it echoes details.
    body = {"display_name": "Bea", "role": "adult", "username": None}
    assert S.step_up_sha256("users.create", "", body) == "sha256:" + hashlib.sha256(
        b'{"body":{"display_name":"Bea","role":"adult","username":null},"op":"users.create","target":""}').hexdigest()
    assert S.step_up_sha256("users.create", "", dict(reversed(body.items()))) == S.step_up_sha256("users.create", "", body)
    # JSON has one number type: 2.0 from Python and 2 back from a browser are the same value.
    assert S.step_up_sha256("x", "", {"n": 2.0, "l": [1.0, 1.5]}) == S.step_up_sha256("x", "", {"n": 2, "l": [1, 1.5]})
    assert S.step_up_sha256("x", "", {"n": 1.5}) != S.step_up_sha256("x", "", {"n": 1})
    assert S.step_up_sha256("x", "a", {}) != S.step_up_sha256("x", "b", {})
    assert S._step_up_details("x", "", {"n": 2.0}, 2) == [{"step_up": {"op": "x", "target": "", "body": {"n": 2},
                                                                      "required_level": "L2", "box": None}}]


def test_during_grace_a_step_up_in_place_replaces_signing_in_again(lvc, clock, settings):
    setup_owner(lvc)
    phone = SoftAuthenticator()
    add_key(lvc, phone, "phone")
    clock.advance(lvc.app.state.identity.cfg.step_up_s + 60)  # the sign-in proof has gone stale
    body = {"display_name": "Cy", "role": "adult"}
    step = step_up_of(lvc.post("/v1/users", json=body, headers=csrf(lvc)))
    assert (step["required_level"], step["box"]) == ("L1", "required")
    g = grant_from(lvc, phone, step)
    assert lvc.post("/v1/users", json=body, headers={**csrf(lvc), "OneMind-Step-Up": g}).status_code == 201
    # Ordinary key revocation remains available after the fresh proof expires (D-034).
    clock.advance(lvc.app.state.identity.cfg.step_up_s + 60)
    add_key(lvc, SoftAuthenticator(), "spare", grant=grant(lvc, phone, "auth.passkeys.register"))
    clock.advance(lvc.app.state.identity.cfg.step_up_s + 60)
    spare = keys(lvc)["spare"]["credential_id"]
    r = lvc.delete(f"/v1/auth/passkeys/{spare}", headers=csrf(lvc))
    assert r.status_code == 204, r.text
    assert list(keys(lvc)) == ["phone"]


@pytest.mark.parametrize("method", ["passkey", "password+totp"])
def test_a_physical_approval_stays_l2_during_the_grace(lvc, clock, method, monkeypatch):
    from onemind_core.actions import FeatureAction
    from onemind_core.executors import ExecResult

    from pydantic import BaseModel

    class PumpParams(BaseModel):
        pump: str

    lvc.app.state.gateway.actions.register_type("test.pump.run", FeatureAction(
        "write", lambda a, finish: finish(ExecResult("succeeded", "ran")), frozenset({"person"}), physical=True,
        params_model=PumpParams))
    setup_owner(lvc)
    phone = SoftAuthenticator()
    add_key(lvc, phone, "phone")
    secret = _enable_totp(lvc, clock)
    assert lvc.get("/v1/verification-requirements").json()["grace"] is True
    aid = file_action(lvc, clock, "test.pump.run", {"pump": "garden"}, "pump1")
    r = lvc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(lvc))
    # tier.P is strict: the grace that eases T3 to L1 never reaches it, so the phone is told plainly.
    assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet", r.text
    r = lvc.post(f"/v1/actions/{aid}/approve-options", json={"at_box": True, "method": method}, headers=csrf(lvc))
    assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet", r.text
    assert r.json()["details"][0]["approval_verification"]["box_available"] is False

    # Simulate an unconsumed challenge issued before the strict rule was enforced.
    levels = lvc.app.state.identity.levels
    need, _, row = levels.for_action(lvc.get(f"/v1/actions/{aid}").json())
    with monkeypatch.context() as old:
        old.setattr(levels, "for_action", lambda _: (need, False, row))
        r = lvc.post(f"/v1/actions/{aid}/approve-options", json={"at_box": True, "method": method}, headers=csrf(lvc))
    assert r.status_code == 200 and r.json()["box_code_required"], r.text
    opts = r.json()
    proof = ({"webauthn": phone.assert_(opts["publicKey"]["challenge"])} if method == "passkey"
             else {"password_totp": _totp_proof(opts, secret, clock)})
    refused = lvc.post(f"/v1/actions/{aid}/approve", headers=csrf(lvc),
                       json={**proof, "plan_sha256": opts["plan_sha256"], "hold_ms": 2000, "box_code": box_code(lvc)})
    assert refused.status_code in (401, 409), refused.text
    assert refused.json()["reason"] == ("step_up_required" if method == "passkey" else "verification_level_unmet")
    assert lvc.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"


def test_a_step_up_without_a_session_is_refused_not_a_crash(lvc, root):
    """An API token has no session for a grant to be bound to: a plain 403, never a 500."""
    setup_owner(lvc)
    add_key(lvc, AttestedAuthenticator(root), "bio")
    tok = lvc.post("/v1/tokens", json={"name": "cli"}, headers=csrf(lvc))
    assert tok.status_code == 201, tok.text
    bearer = {"Authorization": f"Bearer {tok.json()['one_time']['token']}"}
    api = new_session_client(lvc)
    r = api.post("/v1/auth/step-up/options", json={"op": "users.create", "body": {}}, headers=bearer)
    assert r.status_code == 403, r.text
    r = api.post("/v1/auth/step-up", json={"credential": {"id": "x", "rawId": "x", "type": "public-key",
                                                          "response": {}}}, headers=bearer)
    assert r.status_code == 403, r.text
    # The change itself still names the step-up; the CLI turns that into "use the dashboard or phone".
    r = api.post("/v1/users", json={"display_name": "Di", "role": "adult"}, headers=bearer)
    assert r.status_code in (401, 403), r.text


# ---- password and authenticator verification (D-034) -----------------------------------------------
def test_password_only_cannot_approve_a_destructive_action(lvc, clock):
    setup_owner(lvc)
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "password-wipe")
    r = lvc.post(f"/v1/actions/{aid}/approve", headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    assert lvc.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"
    r = lvc.post(f"/v1/actions/{aid}/approve-options", json={"method": "password+totp", "at_box": True},
                 headers=csrf(lvc))
    assert r.status_code == 409 and r.json()["reason"] == "authenticator_required", r.text


def test_password_only_approves_a_reversible_action_and_can_remove_its_sole_l1_key(lvc, clock):
    setup_owner(lvc)
    key = SoftAuthenticator()
    key_id = add_key(lvc, key, "phone")["credential_id"]
    key_session = new_session_client(lvc)
    opts = key_session.post("/v1/auth/login/options").json()
    r = key_session.post("/v1/auth/login", json={"passkey": key.assert_(opts["publicKey"]["challenge"])})
    assert r.status_code == 200, r.text
    r = lvc.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
    assert r.status_code == 200, r.text
    aid = file_action(lvc, clock, "test.reversible", {"target": "photos"}, "password-change")
    assert lvc.post(f"/v1/actions/{aid}/approve", headers=csrf(lvc)).status_code == 200
    r = lvc.delete(f"/v1/auth/passkeys/{key_id}", headers=csrf(lvc))
    assert r.status_code == 204 and keys(lvc) == {}, r.text
    assert key_session.get("/v1/me").status_code == 401
    assert lvc.get("/v1/me").status_code == 200


def _enable_totp(c, clock):
    pending = c.post("/v1/auth/totp/setup", headers=csrf(c))
    assert pending.status_code == 200, pending.text
    secret = pending.json()["one_time"]["secret"]
    code = totp_code(secret, int(clock.now.timestamp() // 30))
    confirmed = c.post("/v1/auth/totp/confirm", json={"code": code}, headers=csrf(c))
    assert confirmed.status_code == 204, confirmed.text
    clock.advance(30)
    return secret


def _totp_proof(options, secret, clock):
    return {"challenge": options["challenge"], "password": PASSWORD,
            "totp": totp_code(secret, int(clock.now.timestamp() // 30))}


def test_fresh_totp_login_meets_l1_but_not_after_its_window(lvc, clock):
    setup_owner(lvc)
    secret = _enable_totp(lvc, clock)
    r = lvc.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD,
                                        "totp": totp_code(secret, int(clock.now.timestamp() // 30))})
    assert r.status_code == 200, r.text
    aid = file_action(lvc, clock, "app.install", {"app_id": "uptime-kuma"}, "totp-l1")
    r = lvc.post(f"/v1/actions/{aid}/approve", headers=csrf(lvc))
    assert r.status_code == 200, r.text
    clock.advance(lvc.app.state.identity.cfg.step_up_s + 1)
    aid = file_action(lvc, clock, "app.install", {"app_id": "whoami"}, "totp-stale")
    r = lvc.post(f"/v1/actions/{aid}/approve", headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text


@pytest.mark.parametrize("has_proven_key", [False, True])
def test_l2_with_password_totp_needs_home_box_and_totp_cannot_be_reused(lvc, clock, root, has_proven_key):
    setup_owner(lvc)
    if has_proven_key:
        add_key(lvc, AttestedAuthenticator(root), "bio")
    secret = _enable_totp(lvc, clock)
    aid = file_action(lvc, clock, "test.wipe", {"target": "photos"}, "totp-box")
    options = f"/v1/actions/{aid}/approve-options"
    remote = TestClient(lvc.app, client=(str(MESH_NETS[0].network_address + 1), 50000))
    sign_in = {"username": "zeus", "password": PASSWORD,
               "totp": totp_code(secret, int(clock.now.timestamp() // 30))}
    r = remote.post("/v1/auth/login", json=sign_in)
    assert r.status_code == 200, r.text
    r = remote.post(options, json={"method": "password+totp", "at_box": True}, headers=csrf(remote))
    assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet", r.text
    clock.advance(30)
    opts = lvc.post(options, json={"method": "password+totp", "at_box": True}, headers=csrf(lvc))
    assert opts.status_code == 200, opts.text
    assert opts.json()["box_code_required"] and box_code(lvc) not in opts.text
    proof = _totp_proof(opts.json(), secret, clock)
    r = lvc.post(f"/v1/actions/{aid}/approve", json={"password_totp": proof, "box_code": box_code(lvc)},
                 headers=csrf(lvc))
    assert r.status_code == 200, r.text
    l1 = file_action(lvc, clock, "app.install", {"app_id": "uptime-kuma"}, "totp-replay")
    opts = lvc.post(f"/v1/actions/{l1}/approve-options", json={"method": "password+totp"}, headers=csrf(lvc))
    assert opts.status_code == 200, opts.text
    r = lvc.post(f"/v1/actions/{l1}/approve", json={"password_totp": {**proof, "challenge": opts.json()["challenge"]}},
                 headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "totp_invalid", r.text


def test_password_totp_grant_meets_l2_at_box_for_one_exact_change(lvc, clock):
    setup_owner(lvc)
    secret = _enable_totp(lvc, clock)
    body = {"display_name": "Barb", "role": "adult"}
    path = "/v1/users"
    step = step_up_of(lvc.post(path, json=body, headers=csrf(lvc)))
    assert step["box"] == "required"
    opts = lvc.post("/v1/auth/step-up/options", json={"op": step["op"], "target": step["target"],
                    "body": step["body"], "method": "password+totp"}, headers=csrf(lvc))
    assert opts.status_code == 200 and opts.json()["box_code_required"], opts.text
    r = lvc.post("/v1/auth/step-up", json={"password_totp": _totp_proof(opts.json(), secret, clock),
                 "box_code": box_code(lvc)}, headers=csrf(lvc))
    assert r.status_code == 200 and r.json()["level"] == "L2", r.text
    headers = {**csrf(lvc), "OneMind-Step-Up": r.json()["step_up"]}
    assert lvc.post(path, json=body, headers=headers).status_code == 201
    assert lvc.post(path, json=body, headers=headers).status_code == 401


# ---- a proven key is vouched for by a proven key or the box (final review of #1184) -------------------------
def _household_with_a_proven_key(c: TestClient, root) -> tuple[SoftAuthenticator, AttestedAuthenticator]:
    """Owner zeus with a phone (L1) and a proven key (L2): the grace is over for good."""
    setup_owner(c)
    phone, bio = SoftAuthenticator(), AttestedAuthenticator(root)
    add_key(c, phone, "phone")
    add_key(c, bio, "bio")
    assert c.app.state.identity.levels.latched()
    c.passkey = bio  # stepped() (test_identity.enrol) confirms owner changes with it
    return phone, bio


def _wipe_by(c: TestClient, clock, key: str) -> str:
    return file_action(c, clock, "test.wipe", {"target": "photos"}, key)


def test_a_second_owners_l1_key_cannot_delete_its_key_and_enrol_a_proven_one(lvc, root, clock, settings):
    """The final review's repro: a second owner's synced phone passkey (L1) deletes that owner's only key,
    then enrols a key of a trusted model. It must not land at L2 without a proven key or the box."""
    from test_identity import enrol

    _household_with_a_proven_key(lvc, root)
    bea = enrol(lvc, "owner", "bea")
    bea_phone = SoftAuthenticator()
    assert add_key(bea, bea_phone, "bea phone", at_box=False)["level"] == "L1"
    # The attacker holds bea's phone passkey: a fresh L1 sign-in is enough to delete it (it is not the last
    # proven key, and the other owner still has keys).
    phone_id = b64url(bea_phone.cred_id)
    r = bea.delete(f"/v1/auth/passkeys/{phone_id}", headers=csrf(bea))
    assert r.status_code == 204, r.text
    # Now bea holds no key. Enrolling a key of a trusted model needs the box's code: no proven key of hers
    # vouches for it.
    attacker_key = AttestedAuthenticator(root)
    opts = bea.post("/v1/auth/passkeys/register/options", headers=csrf(bea))
    assert opts.status_code == 200, opts.text
    r = bea.post("/v1/auth/passkeys/register", json={"credential": attacker_key.register(opts.json()),
                                                      "label": "attacker"}, headers=csrf(bea))
    assert r.status_code == 401 and r.json()["reason"] == "box_code_required", r.text
    assert bea.get("/v1/auth/passkeys").json() == []
    assert opts.json()["box_code_if_proven"] is True  # the box's screen showed a code for her
    # So the T3 approval still has no key that meets it.
    aid = _wipe_by(lvc, clock, "t3-bea")
    r = bea.post(f"/v1/actions/{aid}/approve-options", headers=csrf(bea))
    assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet", r.text
    assert lvc.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"
    # An L1 key still enrols remotely, without the code.
    laptop = SoftAuthenticator()
    assert add_key(bea, laptop, "bea laptop", at_box=False)["level"] == "L1"
    # With only L1 keys, adding another key needs a proven key, or her L1 key plus the box's code ...
    step = step_up_of(bea.post("/v1/auth/passkeys/register/options", headers=csrf(bea)))
    assert (step["required_level"], step["box"]) == ("L2", "alt")
    # ... and at the box (she reads the code) her new proven key enrols at L2; the audit says how.
    g = grant(bea, laptop, "auth.passkeys.register", at_box=True)
    assert add_key(bea, AttestedAuthenticator(root), "bea key", grant=g, at_box=False)["level"] == "L2"
    ev = [e["data"]["payload"] for e in audit_events(settings) if e["event"] == "auth.passkey.registered"]
    assert (ev[-1]["level"], ev[-1]["confirmed"]) == ("L2", "box")


@pytest.mark.parametrize("recovery", [False, True])
def test_an_owner_with_no_key_needs_the_box_for_a_proven_key(lvc, root, clock, recovery):
    """A password-only owner (also while the household waits for recovery) never enrols L2 remotely."""
    from test_identity import enrol

    phone, bio = _household_with_a_proven_key(lvc, root)
    bea = enrol(lvc, "owner", "bea")  # password only: no key at all
    if recovery:  # zeus's proven key is lost and revoked at the box: no owner holds a proven key now
        bio_id = b64url(bio.cred_id)
        g = grant(lvc, phone, "auth.passkeys.delete", bio_id, at_box=True)
        assert lvc.delete(f"/v1/auth/passkeys/{bio_id}", headers={**csrf(lvc), "OneMind-Step-Up": g}).status_code == 204
        assert lvc.get("/v1/verification-requirements").json()["recovery_needed"] is True
    opts = bea.post("/v1/auth/passkeys/register/options", headers=csrf(bea))
    assert opts.status_code == 200, opts.text
    r = bea.post("/v1/auth/passkeys/register", json={"credential": AttestedAuthenticator(root).register(opts.json()),
                                                      "label": "remote"}, headers=csrf(bea))
    assert r.status_code == 401 and r.json()["reason"] == "box_code_required", r.text
    assert bea.get("/v1/auth/passkeys").json() == [] and opts.json()["box_code_if_proven"] is True
    assert lvc.get("/v1/verification-requirements").json()["recovery_needed"] is recovery
    # An L1 key (a phone passkey) still enrols remotely; a proven key enrols at the box.
    assert add_key(bea, SoftAuthenticator(), "bea phone", at_box=False)["level"] == "L1"
    if recovery:  # the interim recovery path: an owner at the box adds the household's proven key again
        step = step_up_of(bea.post("/v1/auth/passkeys/register/options", headers=csrf(bea)))
        assert (step["required_level"], step["box"]) == ("L1", "required")


def test_lowering_admin_high_risk_never_lets_an_l1_key_vouch_for_a_proven_one(lvc, root, clock, settings):
    """admin.high_risk at L1 (the phone-only escape hatch) lets a phone add a key, never a proven one."""
    phone, bio = _household_with_a_proven_key(lvc, root)
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "admin.high_risk", "level": "L1"}, "hr1")
    assert approve(lvc, aid, bio).status_code == 200
    rows = {r["key"]: r for r in lvc.get("/v1/verification-requirements").json()["rows"]}
    assert rows["admin.high_risk"]["current"] == "L1"
    # The phone's L1 grant is enough to add a key now ...
    g = grant(lvc, phone, "auth.passkeys.register")
    h = {**csrf(lvc), "OneMind-Step-Up": g}
    opts = lvc.post("/v1/auth/passkeys/register/options", headers=h)
    assert opts.status_code == 200, opts.text
    # ... but a key that would be L2 needs the box's code: the phone can't vouch for it.
    minted = AttestedAuthenticator(root)
    r = lvc.post("/v1/auth/passkeys/register", json={"credential": minted.register(opts.json()), "label": "minted"},
                 headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "box_code_required", r.text
    assert "minted" not in keys(lvc) and opts.json()["box_code_if_proven"] is True
    # Another phone passkey (L1) is fine with the phone's grant.
    assert add_key(lvc, SoftAuthenticator(), "laptop", grant=grant(lvc, phone, "auth.passkeys.register"),
                   at_box=False)["level"] == "L1"
    # The proven key vouches without the box, and the audit says so.
    assert add_key(lvc, AttestedAuthenticator(root), "bio2", grant=grant(lvc, bio, "auth.passkeys.register"),
                   at_box=False)["level"] == "L2"
    ev = [e["data"]["payload"] for e in audit_events(settings) if e["event"] == "auth.passkey.registered"]
    assert (ev[-1]["level"], ev[-1]["confirmed"]) == ("L2", "proven_key")
    # The table says so where the row is edited (GET /v1/verification-requirements, onemind permissions verify).
    assert "never lowers what adding a proven key takes" in rows["admin.high_risk"]["label"]


def test_lowering_admin_high_risk_never_lets_an_l1_key_promote_a_proven_key_to_owner(lvc, root, clock):
    """The same hole by another door: an adult's proven key (adults enrol one without the box) made an owner's
    key by an L1 grant. Promoting a person who holds a proven key needs a proven key, or the box."""
    from test_identity import enrol

    phone, bio = _household_with_a_proven_key(lvc, root)
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "admin.high_risk", "level": "L1"}, "hr2")
    assert approve(lvc, aid, bio).status_code == 200
    lvc.passkey = phone  # with the row at L1 the phone adds people
    ana = enrol(lvc, "adult", "ana")
    ana_id = ana.get("/v1/me").json()["principal"]["id"]
    ana_key = AttestedAuthenticator(root)
    assert add_key(ana, ana_key, "ana key", at_box=False)["level"] == "L2"
    body = {"display_name": None, "role": "owner"}
    step = step_up_of(lvc.patch(f"/v1/users/{ana_id}", json=body, headers=csrf(lvc)))
    assert (step["op"], step["required_level"], step["box"]) == ("users.update", "L2", "alt")
    opts = lvc.post("/v1/auth/step-up/options", json={"op": step["op"], "target": ana_id, "body": step["body"]},
                    headers=csrf(lvc)).json()
    assert [k["id"] for k in opts["publicKey"]["allowCredentials"]] == [b64url(bio.cred_id)]
    r = lvc.post("/v1/auth/step-up", json={"credential": phone.assert_(opts["publicKey"]["challenge"])},
                 headers=csrf(lvc))
    assert r.status_code == 401
    assert lvc.get("/v1/users").json()[-1]["role"] == "adult"
    # Someone who is already an owner keeps the table's row (L1 here).
    me = lvc.get("/v1/me").json()["principal"]["id"]
    opts = lvc.post("/v1/auth/step-up/options", json={"op": "users.update", "target": me,
                                                      "body": {"display_name": "Z", "role": None}}, headers=csrf(lvc))
    assert (opts.json()["required_level"], opts.json()["box_code_required"]) == ("L1", False), opts.text
    # The proven key (or an owner at the box) promotes her.
    g = grant_from(lvc, bio, step)
    r = lvc.patch(f"/v1/users/{ana_id}", json=body, headers={**csrf(lvc), "OneMind-Step-Up": g})
    assert r.status_code == 200 and r.json()["role"] == "owner", r.text


def test_owner_proven_key_enrolment_requires_fresh_options_after_promotion(lvc, root):
    """Pending options for a member cannot authorise a proven key after the member becomes an owner."""
    from test_identity import enrol

    _, bio = _household_with_a_proven_key(lvc, root)
    ana = enrol(lvc, "adult", "ana")
    ana_id = ana.get("/v1/me").json()["principal"]["id"]
    opts = ana.post("/v1/auth/passkeys/register/options", headers=csrf(ana))
    assert opts.status_code == 200 and opts.json()["box_code_if_proven"] is False, opts.text

    body = {"display_name": None, "role": "owner"}
    g = grant(lvc, bio, "users.update", ana_id, body)
    r = lvc.patch(f"/v1/users/{ana_id}", json=body, headers={**csrf(lvc), "OneMind-Step-Up": g})
    assert r.status_code == 200 and r.json()["role"] == "owner", r.text

    key = AttestedAuthenticator(root)
    r = ana.post("/v1/auth/passkeys/register", json={"credential": key.register(opts.json())}, headers=csrf(ana))
    assert r.status_code == 409 and r.json()["reason"] == "registration_options_stale", r.text
    assert keys(ana) == {}
    assert add_key(ana, key, "confirmed at the box")["level"] == "L2"


def test_pending_first_passkey_options_cannot_enrol_a_later_proven_key(lvc, root):
    setup_owner(lvc)
    opts = lvc.post("/v1/auth/passkeys/register/options", headers=csrf(lvc))
    # D-034 (founder gate decision, train 2026-11-28): no first-owner-passkey exemption; the household's first
    # proven key also needs the box's code at home, so even the first options ask for it.
    assert opts.status_code == 200 and opts.json()["box_code_if_proven"] is True, opts.text
    assert add_key(lvc, SoftAuthenticator(), "first key", at_box=False)["level"] == "L1"

    key = AttestedAuthenticator(root)
    r = lvc.post("/v1/auth/passkeys/register", json={"credential": key.register(opts.json())}, headers=csrf(lvc))
    assert r.status_code == 401 and r.json()["reason"] == "box_code_required", r.text
    assert set(keys(lvc)) == {"first key"}


def test_only_one_owner_can_use_the_first_passkey_exception(lvc, root):
    """D-034 (founder gate decision, train 2026-11-28): there is no first-owner-passkey exemption left to race
    for. Two owners enrolling their first keys at the same time each need the box's code: the one who types it
    gets an L2 key, the one who doesn't gets nothing."""
    from test_identity import enrol

    setup_owner(lvc)
    bea = enrol(lvc, "owner", "bea")

    def register(c, body):
        return c.post("/v1/auth/passkeys/register", json=body, headers=csrf(c))

    bodies = []
    for c in (lvc, bea):
        opts = c.post("/v1/auth/passkeys/register/options", headers=csrf(c))
        assert opts.status_code == 200 and opts.json()["box_code_if_proven"] is True, opts.text
        bodies.append({"credential": AttestedAuthenticator(root).register(opts.json())})
        if c is lvc:  # zeus reads his code off the screen before bea's request shows hers
            bodies[-1]["box_code"] = box_code(lvc)

    with ThreadPoolExecutor(max_workers=2) as clients:
        first = clients.submit(register, lvc, bodies[0])
        second = clients.submit(register, bea, bodies[1])
        accepted, rejected = first.result(timeout=15), second.result(timeout=15)
    assert accepted.status_code == 201 and accepted.json()["level"] == "L2", accepted.text
    assert rejected.status_code == 401 and rejected.json()["reason"] == "box_code_required", rejected.text
    assert keys(bea) == {}


@pytest.fixture
def keyless_recovery(lvc, root, clock):
    from test_identity import PASSWORD, enrol

    _, bio = _household_with_a_proven_key(lvc, root)
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "admin.high_risk", "level": "L1"}, "hr-zero")
    assert approve(lvc, aid, bio).status_code == 200
    bea = enrol(lvc, "owner", "bea")
    ana = enrol(lvc, "adult", "ana")
    assert add_key(ana, AttestedAuthenticator(root), "ana key", at_box=False)["level"] == "L2"
    r = bea.post("/v1/auth/login", json={"username": "bea", "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert bea.get("/v1/me").json()["session"]["auth_method"] == "password"
    me = lvc.get("/v1/me").json()["principal"]["id"]
    r = bea.post(f"/v1/users/{me}/disable", headers=csrf(bea))
    assert r.status_code == 200 and r.json()["disabled"] is True, r.text
    assert lvc.get("/v1/me").status_code == 401
    table = bea.get("/v1/verification-requirements").json()
    assert (table["grace"], table["recovery_needed"], table["household_level"]) == (False, True, None)
    return bea, ana.get("/v1/me").json()["principal"]["id"]


def test_keyless_recovery_preserves_the_promotion_floor(keyless_recovery, root):
    bea, ana_id = keyless_recovery
    body = {"display_name": None, "role": "owner"}
    step = step_up_of(bea.patch(f"/v1/users/{ana_id}", json=body, headers=csrf(bea)))
    assert (step["op"], step["required_level"], step["box"]) == ("users.update", "L2", "alt")

    recovered = AttestedAuthenticator(root)
    assert add_key(bea, recovered, "recovered at the box")["level"] == "L2"
    assert bea.get("/v1/verification-requirements").json()["recovery_needed"] is False
    g = grant_from(bea, recovered, step)
    r = bea.patch(f"/v1/users/{ana_id}", json=body, headers={**csrf(bea), "OneMind-Step-Up": g})
    assert r.status_code == 200 and r.json()["role"] == "owner", r.text


def test_keyless_recovery_preserves_the_approval_level(keyless_recovery, clock):
    bea, _ = keyless_recovery
    aid = _wipe_by(bea, clock, "keyless-recovery")
    r = bea.post(f"/v1/actions/{aid}/approve", headers=csrf(bea))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    r = bea.post(f"/v1/actions/{aid}/approve-options", headers=csrf(bea))
    assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet", r.text
    action = bea.get(f"/v1/actions/{aid}").json()
    assert (action["state"], action["required_level"]) == ("awaiting_approval", "L2")


@pytest.mark.parametrize("legacy", [False, True], ids=["current", "upgrade-from-v4"])
def test_l1_only_household_stays_out_of_setup(lvc, root, clock, legacy):
    from onemind_core.identity.models import HouseholdFlagRow, SCHEMA
    from onemind_core.store import SchemaVersionRow, migrate
    from test_identity import enrol

    setup_owner(lvc)
    bea = enrol(lvc, "owner", "bea")
    me = lvc.get("/v1/me").json()["principal"]["id"]
    bea_id = bea.get("/v1/me").json()["principal"]["id"]
    assert add_key(lvc, SoftAuthenticator(), "first key")["level"] == "L1"
    r = bea.post(f"/v1/users/{me}/disable", headers=csrf(bea))
    assert r.status_code == 200 and r.json()["disabled"], r.text

    identity = lvc.app.state.identity
    if legacy:
        repo = identity.repo
        repo.delete(HouseholdFlagRow, HouseholdFlagRow.key == "owner_passkey_seen")
        repo.update(SchemaVersionRow, [SchemaVersionRow.feature == "identity"], {"version": 4})
        migrate(repo.db.engine, schemas=[SCHEMA])
    assert not identity.passkeys_active() and not identity.levels.latched()

    opts = bea.post("/v1/auth/passkeys/register/options", headers=csrf(bea))
    assert opts.status_code == 200 and opts.json()["box_code_if_proven"] is True, opts.text
    r = bea.patch(f"/v1/users/{bea_id}", json={"display_name": "Bea"}, headers=csrf(bea))
    step = step_up_of(r)
    assert (step["required_level"], step["box"]) == ("L1", "required")
    aid = _wipe_by(bea, clock, "l1-key-lost")
    r = bea.post(f"/v1/actions/{aid}/approve-options", headers=csrf(bea))
    assert r.status_code == 409 and r.json()["reason"] == "verification_level_unmet", r.text
    assert bea.get(f"/v1/actions/{aid}").json()["required_level"] == "L2"
    assert bea.get("/v1/verification-requirements").json()["grace"] is True

    body = {"credential": AttestedAuthenticator(root).register(opts.json()), "box_code": box_code(bea)}
    r = bea.post("/v1/auth/passkeys/register", json=body, headers=csrf(bea))
    assert r.status_code == 201 and r.json()["level"] == "L2", r.text
    assert bea.get("/v1/verification-requirements").json()["grace"] is False


@pytest.mark.parametrize("established_by", ["registration", "promotion"])
def test_first_proven_owner_key_latches_before_it_can_be_lost(lvc, root, monkeypatch, established_by):
    from test_identity import enrol

    setup_owner(lvc)
    bea = enrol(lvc, "owner" if established_by == "registration" else "adult", "bea")
    bea_id = bea.get("/v1/me").json()["principal"]["id"]
    identity = lvc.app.state.identity
    emit = identity.emit
    boundary = "passkey.registered" if established_by == "registration" else "updated"

    def disable_at_first_post_commit_event(domain, name, payload, *args, **kwargs):
        if name == boundary and payload.get("user_id") == bea_id:
            r = lvc.post(f"/v1/users/{bea_id}/disable", headers=csrf(lvc))
            assert r.status_code == 200 and r.json()["disabled"], r.text
        emit(domain, name, payload, *args, **kwargs)

    if established_by == "registration":
        monkeypatch.setattr(identity, "emit", disable_at_first_post_commit_event)
        assert add_key(bea, AttestedAuthenticator(root), "first proven key")["level"] == "L2"
    else:
        phone = SoftAuthenticator()
        assert add_key(lvc, phone, "owner phone")["level"] == "L1"
        assert add_key(bea, AttestedAuthenticator(root), "member key")["level"] == "L2"
        assert not identity.levels.latched()
        body = {"display_name": None, "role": "owner"}
        g = grant(lvc, phone, "users.update", bea_id, body)
        monkeypatch.setattr(identity, "emit", disable_at_first_post_commit_event)
        r = lvc.patch(f"/v1/users/{bea_id}", json=body, headers={**csrf(lvc), "OneMind-Step-Up": g})
        assert r.status_code == 200 and r.json()["role"] == "owner", r.text

    assert bea.get("/v1/me").status_code == 401
    table = lvc.get("/v1/verification-requirements").json()
    assert (table["grace"], table["recovery_needed"]) == (False, True)


@pytest.mark.parametrize("changed", ["session", "revoked-key", "untrusted-model"])
def test_proven_key_vouch_must_still_be_valid_at_registration(lvc, root, clock, changed):
    from test_identity import PASSWORD

    phone, bio = _household_with_a_proven_key(lvc, root)
    model = "a1b2c3d4-0000-4000-8000-0000000000a2"
    params = {"aaguid": model, "name": "Test Model", "roots": [root.pem],
              "user_verification": ["fingerprint_internal"]}
    aid = file_action(lvc, clock, "authenticator.allowlist.add", params, "vouch-model")
    assert approve(lvc, aid, bio).status_code == 200
    key = AttestedAuthenticator(root, aaguid=model)
    assert add_key(lvc, key, "vouching key", grant=grant(lvc, bio, "auth.passkeys.register"))["level"] == "L2"

    g = grant(lvc, key, "auth.passkeys.register")
    opts = lvc.post("/v1/auth/passkeys/register/options", headers={**csrf(lvc), "OneMind-Step-Up": g})
    assert opts.status_code == 200 and opts.json()["box_code_if_proven"] is False, opts.text
    client = lvc
    if changed == "session":
        client = new_session_client(lvc)
        r = client.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
        assert r.status_code == 200, r.text
    elif changed == "revoked-key":
        g = grant(lvc, phone, "auth.passkeys.delete", b64url(key.cred_id))
        r = lvc.delete(f"/v1/auth/passkeys/{b64url(key.cred_id)}", headers={**csrf(lvc), "OneMind-Step-Up": g})
        assert r.status_code == 204, r.text
    else:
        r = lvc.delete(f"/v1/auth/authenticator-allowlist/{model}", headers=csrf(lvc))
        assert r.status_code == 204 and keys(lvc)["vouching key"]["level"] == "L1", r.text

    replacement = AttestedAuthenticator(root)
    r = client.post("/v1/auth/passkeys/register", json={"credential": replacement.register(opts.json())},
                    headers=csrf(client))
    # D-034 (train 2026-11-28) binds the options to their session and credential revision, so a new session or a
    # removed key (it bumps the revision) is refused before the vouch is rechecked; a model that lost trust is
    # caught by the vouch recheck itself. Either way nothing enrols.
    stale = (401, "assertion_invalid") if changed in ("session", "revoked-key") else (409, "registration_options_stale")
    assert (r.status_code, r.json()["reason"]) == stale, r.text
    assert add_key(lvc, replacement, "fresh vouch", grant=grant(lvc, bio, "auth.passkeys.register"))["level"] == "L2"


@pytest.mark.parametrize("keyless", [False, True], ids=["active-owner-keys", "keyless-recovery"])
def test_promotion_rechecks_keys_after_step_up(lvc, root, clock, monkeypatch, keyless):
    from test_identity import enrol

    phone, bio = _household_with_a_proven_key(lvc, root)
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "admin.high_risk", "level": "L1"}, "hr-race")
    assert approve(lvc, aid, bio).status_code == 200
    bea = enrol(lvc, "owner", "bea") if keyless else None
    me = lvc.get("/v1/me").json()["principal"]["id"]
    ana = enrol(lvc, "adult", "ana")
    ana_id = ana.get("/v1/me").json()["principal"]["id"]
    body = {"display_name": None, "role": "owner"}
    g = grant(lvc, phone, "users.update", ana_id, body)

    checked, resume = Event(), Event()
    identity = lvc.app.state.identity
    require_step_up = identity.require_step_up

    def pause_promotion(*args, **kwargs):
        via = require_step_up(*args, **kwargs)
        if kwargs.get("op") == "users.update":
            checked.set()
            assert resume.wait(timeout=15)
        return via

    monkeypatch.setattr(identity, "require_step_up", pause_promotion)
    with ThreadPoolExecutor(max_workers=1) as client:
        promotion = client.submit(lvc.patch, f"/v1/users/{ana_id}", json=body,
                                  headers={**csrf(lvc), "OneMind-Step-Up": g})
        try:
            assert checked.wait(timeout=15)
            if bea is not None:
                r = bea.post(f"/v1/users/{me}/disable", headers=csrf(bea))
                assert r.status_code == 200 and not identity.passkeys_active() and identity.levels.latched(), r.text
            assert add_key(ana, AttestedAuthenticator(root), "ana key", at_box=False)["level"] == "L2"
        finally:
            resume.set()
        r = promotion.result(timeout=15)
    assert r.status_code == 409 and r.json()["reason"] == "promotion_verification_changed", r.text
    assert ana.get("/v1/me").json()["principal"]["role"] == "adult"


@pytest.mark.parametrize("body, expected", [
    ({"display_name": "Ana's new name", "role": None}, {"display_name": "Ana's new name", "role": "adult"}),
    ({"display_name": None, "role": "guest"}, {"role": "guest"}),
], ids=["rename", "demote"])
def test_non_promotion_of_a_member_with_a_proven_key_follows_the_table(lvc, root, clock, body, expected):
    from test_identity import enrol

    phone, bio = _household_with_a_proven_key(lvc, root)
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "admin.high_risk", "level": "L1"}, "hr-edit")
    assert approve(lvc, aid, bio).status_code == 200
    ana = enrol(lvc, "adult", "ana")
    ana_id = ana.get("/v1/me").json()["principal"]["id"]
    assert add_key(ana, AttestedAuthenticator(root), "ana key", at_box=False)["level"] == "L2"
    opts = lvc.post("/v1/auth/step-up/options", json={"op": "users.update", "target": ana_id, "body": body},
                    headers=csrf(lvc))
    assert opts.status_code == 200 and opts.json()["required_level"] == "L1", opts.text
    g = grant(lvc, phone, "users.update", ana_id, body)
    r = lvc.patch(f"/v1/users/{ana_id}", json=body, headers={**csrf(lvc), "OneMind-Step-Up": g})
    assert r.status_code == 200, r.text
    assert {field: r.json()[field] for field in expected} == expected


def test_member_promotion_requires_vouch_for_a_previously_trusted_key(lvc, root, clock):
    from test_identity import enrol

    phone, bio = _household_with_a_proven_key(lvc, root)
    aid = file_action(lvc, clock, "verification.requirement.set", {"key": "admin.high_risk", "level": "L1"}, "hr-model")
    assert approve(lvc, aid, bio).status_code == 200
    model = "a1b2c3d4-0000-4000-8000-0000000000a2"
    params = {"aaguid": model, "name": "Test Member Key", "roots": [root.pem],
              "user_verification": ["fingerprint_internal"]}
    aid = file_action(lvc, clock, "authenticator.allowlist.add", params, "member-model")
    assert approve(lvc, aid, bio).status_code == 200
    ana = enrol(lvc, "adult", "ana")
    ana_id = ana.get("/v1/me").json()["principal"]["id"]
    assert add_key(ana, AttestedAuthenticator(root, aaguid=model), "ana key", at_box=False)["level"] == "L2"
    r = lvc.delete(f"/v1/auth/authenticator-allowlist/{model}", headers=csrf(lvc))
    assert r.status_code == 204, r.text
    assert keys(ana)["ana key"]["level"] == "L1"

    body = {"display_name": None, "role": "owner"}
    step = step_up_of(lvc.patch(f"/v1/users/{ana_id}", json=body, headers=csrf(lvc)))
    assert (step["required_level"], step["box"]) == ("L2", "alt")
    g = grant_from(lvc, bio, step)
    r = lvc.patch(f"/v1/users/{ana_id}", json=body, headers={**csrf(lvc), "OneMind-Step-Up": g})
    assert r.status_code == 200 and r.json()["role"] == "owner", r.text


# ---- adding a recovery contact is L2 (D-028, admin.high_risk) ----------------------------------------------
CONTACTS = "/v1/auth/recovery/contacts"


def _contact(name: str) -> dict:
    return {"kind": "outside", "display_name": name}


def test_an_l1_passkey_cannot_add_a_recovery_contact_once_a_proven_key_exists(lvc, root):
    """A synced (L1) passkey session is refused: the step-up is L2 and only proven keys are offered."""
    phone, bio = _household_with_a_proven_key(lvc, root)
    r = lvc.post(CONTACTS, json=_contact("Ana"), headers=csrf(lvc))
    step = step_up_of(r)
    assert step["op"] == "recovery.contacts.add" and step["required_level"] == "L2", step
    opts = lvc.post("/v1/auth/step-up/options", json={k: step[k] for k in ("op", "target", "body")},
                    headers=csrf(lvc)).json()
    assert [k["id"] for k in opts["publicKey"]["allowCredentials"]] == [b64url(bio.cred_id)]
    r = lvc.post("/v1/auth/step-up", json={"credential": phone.assert_(opts["publicKey"]["challenge"])},
                 headers=csrf(lvc))
    assert r.status_code == 401
    assert lvc.get(CONTACTS, headers=csrf(lvc)).json() == []
    # A grant for another contact does not add this one; the proven key's own grant does, once.
    other = grant(lvc, bio, step["op"], step["target"], {**step["body"], "display_name": "Eve"})
    assert lvc.post(CONTACTS, json=_contact("Ana"), headers={**csrf(lvc), "OneMind-Step-Up": other}).status_code == 401
    g = grant_from(lvc, bio, step)
    assert lvc.post(CONTACTS, json=_contact("Ana"), headers={**csrf(lvc), "OneMind-Step-Up": g}).status_code == 201


def test_at_home_an_l1_passkey_adds_a_contact_with_the_box_code(lvc):
    """Before any proven key (the grace), L1 plus the code on the box's own screen meets L2, at home only."""
    setup_owner(lvc)
    phone = SoftAuthenticator()
    add_key(lvc, phone, "phone")
    step = step_up_of(lvc.post(CONTACTS, json=_contact("Ana"), headers=csrf(lvc)))
    assert step["op"] == "recovery.contacts.add" and step["box"] == "required", step  # an L1 key plus the code
    opts = lvc.post("/v1/auth/step-up/options", json={k: step[k] for k in ("op", "target", "body")},
                    headers=csrf(lvc))
    assert opts.status_code == 200 and opts.json()["box_code_required"], opts.text
    sent = {"credential": phone.assert_(opts.json()["publicKey"]["challenge"])}
    assert lvc.post("/v1/auth/step-up", json=sent, headers=csrf(lvc)).status_code == 401  # no box code
    opts = lvc.post("/v1/auth/step-up/options", json={k: step[k] for k in ("op", "target", "body")}, headers=csrf(lvc))
    sent = {"credential": phone.assert_(opts.json()["publicKey"]["challenge"]), "box_code": box_code(lvc)}
    r = lvc.post("/v1/auth/step-up", json=sent, headers=csrf(lvc))
    assert r.status_code == 200, r.text
    added = lvc.post(CONTACTS, json=_contact("Ana"), headers={**csrf(lvc), "OneMind-Step-Up": r.json()["step_up"]})
    assert added.status_code == 201, added.text


def test_away_from_home_a_proven_key_adds_a_contact(lvc, root):
    _, bio = _household_with_a_proven_key(lvc, root)
    remote = TestClient(lvc.app, client=(str(MESH_NETS[0].network_address + 1), 50000))
    opts = remote.post("/v1/auth/login/options").json()
    assert remote.post("/v1/auth/login", json={"passkey": bio.assert_(opts["publicKey"]["challenge"])}).status_code == 200
    step = step_up_of(remote.post(CONTACTS, json=_contact("Ana"), headers=csrf(remote)))
    assert not step["box"], step  # no box code is offered away from home (D-034)
    g = grant_from(remote, bio, step)
    r = remote.post(CONTACTS, json=_contact("Ana"), headers={**csrf(remote), "OneMind-Step-Up": g})
    assert r.status_code == 201, r.text


def test_a_password_only_owner_adds_a_contact_with_an_authenticator_and_the_box_code(lvc, clock):
    setup_owner(lvc)
    secret = _enable_totp(lvc, clock)
    step = step_up_of(lvc.post(CONTACTS, json=_contact("Ana"), headers=csrf(lvc)))
    opts = lvc.post("/v1/auth/step-up/options", json={"op": step["op"], "target": step["target"],
                    "body": step["body"], "method": "password+totp"}, headers=csrf(lvc))
    assert opts.status_code == 200 and opts.json()["box_code_required"], opts.text
    r = lvc.post("/v1/auth/step-up", json={"password_totp": _totp_proof(opts.json(), secret, clock),
                 "box_code": box_code(lvc)}, headers=csrf(lvc))
    assert r.status_code == 200 and r.json()["level"] == "L2", r.text
    added = lvc.post(CONTACTS, json=_contact("Ana"), headers={**csrf(lvc), "OneMind-Step-Up": r.json()["step_up"]})
    assert added.status_code == 201, added.text
