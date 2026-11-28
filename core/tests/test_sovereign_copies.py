# SPDX-License-Identifier: Apache-2.0
from dataclasses import replace

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from onemind_core.backups.jobs import AgentError
from onemind_core.backups.kit import new_owner_key
from onemind_core.boxbundle import box_config, sovereign as copy
from onemind_core.boxbundle.manifest import BundleRefused, Source, canonical, sha256
from onemind_core.automation.registry import automatable, policy_may_cover

from conftest import ADULT, AGENT, OWNER
from test_backups import FakeAgent, approve
from test_identity import SoftAuthenticator, csrf, idc, new_session_client, register_passkey, setup_owner

START = "/v1/backups/copies"
DISCOVER = "/v1/onboarding/restore/copy"


class CopyAgent(FakeAgent):
    def __init__(self, clock):
        super().__init__(clock)
        self.objects = {}
        self.damage = set()
        self.generation = 0
        self.repository = sha256(b"test repository")
        self.target_keys = {}

    def job(self, kind, params, *, action_id=None, timeout=None):
        if kind != "backup.copy":
            result = super().job(kind, params, action_id=action_id, timeout=timeout)
            if kind == "backup.configure":
                self.target_keys = {t["id"]: self.target_keys.get(t["id"]) for t in params["targets"]}
            if kind == "backup.key.add":
                self.target_keys = dict.fromkeys(self.target_keys, params["key"])
            return result
        self.jobs.append((kind, params, action_id))
        op, cid = params["operation"], params.get("copy_id")
        if op == "prepare":
            return {"repository": self.repository, "generation": self.generation,
                    "snapshots": [s for s in self.snaps if s["id"] in params["snapshots"]]}
        if op == "publish":
            assert action_id and params["repository"] == self.repository
            target = params["target_id"]
            if params.get("attach_recovery_key"):
                self.target_keys[target] = params["recovery_key"]
            if self.target_keys[target] != params["recovery_key"]:
                raise AgentError(kind, "kit missing from this repository", reason="failed")
            self.objects[cid] = {k: params[k] for k in ("bundle", "record")}
        if op == "list":
            return list(self.objects)
        if op in ("bundle", "record"):
            return self.objects[cid][op]
        if op == "check":
            assert params["repository"] == self.repository
            assert params["snapshots"] == [self.snaps[-1]["id"]]
            if cid in self.damage:
                raise AgentError(kind, "corrupt snapshot", reason="failed")
            return {"snapshots": [self.snaps[-1]]}
        return None


def provision_copy(client, clock, tmp_path):
    svc = client.app.state.backups
    svc.agent = CopyAgent(clock)
    svc.worker.inline = True
    svc.s = replace(svc.s, copy_keys_dir=tmp_path)
    box = svc.gw.settings.node_id
    root, signer = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    root_pub = root.public_key().public_bytes_raw()
    trust = {"root": copy.b64(root_pub), "certificate": copy.certificate(root, signer.public_key(), box)}
    (tmp_path / "trust.json").write_bytes(canonical(trust))
    keyfile = tmp_path / "export.key"
    keyfile.write_bytes(signer.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    keyfile.chmod(0o600)
    return svc, box, sha256(root_pub), signer


def make_kit(client, headers):
    response = client.post("/v1/backups/kit", headers=headers)
    assert response.status_code == 201, response.text
    issued = response.json()

    return confirm_kit(client, headers, issued)


def confirm_kit(client, headers, issued):
    kit = issued["one_time"]
    answers = {str(i): kit["groups"][i - 1] for i in issued["kit"]["positions"]}
    assert client.post("/v1/backups/kit/confirm", headers=headers, json={"answers": answers}).status_code == 200
    return kit["owner_key"]


@pytest.fixture
def copy_box(client, clock, tmp_path):
    svc, box, root, signer = provision_copy(client, clock, tmp_path)
    dest = client.post("/v1/backups/destinations", headers=OWNER, json={
        "kind": "usb", "label": "Owner NAS", "config": {"usb_uuid": "nas", "sovereign": True}}).json()
    assert approve(client, dest["id"])["state"] == "succeeded"
    dest_id = dest["params"]["destination_id"]
    assert svc.agent.jobs[-1][1]["targets"][0]["sovereign"] is True
    recovery_key = make_kit(client, OWNER)
    run = client.post("/v1/backups/runs", headers=OWNER, json={"destination_id": dest_id}).json()
    assert approve(client, run["id"])["state"] == "succeeded"

    return svc, {"destination_id": dest_id, "recovery_key": recovery_key}, box, root, signer


@pytest.mark.parametrize("issue_key", ["first-kit-after-passkey", None])
def test_existing_passkey_owner_can_publish_to_new_target(idc, clock, tmp_path, issue_key):
    svc, box, root, _ = provision_copy(idc, clock, tmp_path)
    setup_owner(idc)
    headers = csrf(idc)
    dest = idc.post("/v1/backups/destinations", headers=headers, json={
        "kind": "usb", "label": "Existing disk", "config": {"usb_uuid": "original"}, "approve": True})
    assert dest.status_code == 202 and dest.json()["state"] == "succeeded", dest.text
    authenticator = SoftAuthenticator()
    register_passkey(idc, authenticator)
    assert idc.app.state.identity.passkeys_active()

    def step_up(action):
        url = f"/v1/actions/{action['id']}"
        options = idc.post(url + "/approve-options", headers=headers)
        assert options.status_code == 200, options.text
        assertion = authenticator.assert_(options.json()["challenge"], flat=True)
        result = idc.post(url + "/approve", headers=headers, json={"webauthn": assertion})
        assert result.status_code == 200 and result.json()["state"] == "succeeded", result.text
        return result.json()

    issue = "/v1/backups/kit"
    assert idc.get(issue, headers=headers).json()["state"] == "missing"
    issue_headers = {**headers, **({"Idempotency-Key": issue_key} if issue_key else {})}
    pending = idc.post(issue, headers=issue_headers)
    assert pending.status_code == 401 and pending.json()["reason"] == "step_up_required", pending.text
    actions = idc.get("/v1/actions", headers=headers).json()
    action = next(a for a in actions if a["type"] == "backup.kit.issue")
    action_url = f"/v1/actions/{action['id']}"
    assert action["state"] == "awaiting_approval"
    assert "backup.key.add" not in svc.agent.kinds()
    assert idc.post(action_url + "/approve", headers=headers).status_code == 401
    approved = step_up(action)
    assert "one_time" not in approved

    retry_headers = {**headers, "Idempotency-Key": issue_key or pending.headers["Idempotency-Key"]}
    with new_session_client(idc) as other:
        wrong_owner = other.post(issue, headers={**OWNER, "Idempotency-Key": retry_headers["Idempotency-Key"]})
    assert wrong_owner.status_code == 409 and "one_time" not in wrong_owner.json(), wrong_owner.text
    issued = idc.post(issue, headers=retry_headers)
    assert issued.status_code == 201 and issued.headers["Cache-Control"] == "no-store", issued.text
    assert issued.json()["action"]["id"] == action["id"]
    assert pending.headers["Location"] == action_url
    assert pending.headers["Idempotency-Key"] == retry_headers["Idempotency-Key"]
    replay = idc.post(issue, headers=retry_headers)
    assert replay.status_code == 409 and "one_time" not in replay.json(), replay.text
    assert svc.agent.kinds().count("backup.key.add") == 1
    recovery_key = confirm_kit(idc, headers, issued.json())

    new_dest = idc.post("/v1/backups/destinations", headers=headers, json={
        "kind": "usb", "label": "Owner NAS", "config": {"usb_uuid": "nas", "sovereign": True}})
    assert new_dest.status_code == 202, new_dest.text
    destination = step_up(new_dest.json())["params"]["destination_id"]
    assert svc.agent.target_keys[destination] is None
    run = idc.post("/v1/backups/runs", headers=headers, json={"destination_id": destination})
    assert run.status_code == 202, run.text
    step_up(run.json())
    body = {"destination_id": destination, "recovery_key": recovery_key}
    response = idc.post(START, headers=headers, json=body)
    assert response.status_code == 202, response.text
    action = response.json()
    refused = idc.post(f"/v1/actions/{action['id']}/approve", headers=headers)
    assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
    assert svc.agent.target_keys[destination] is None and not svc.agent.objects
    done = step_up(action)
    assert svc.agent.target_keys[destination] == recovery_key
    assert idc.get("/v1/backups/kit", headers=headers).json()["state"] == "confirmed"
    found = idc.post(DISCOVER, headers=headers, json={**body, "box_id": box, "root_fingerprint": root})
    assert found.status_code == 200, found.text
    assert found.json()["candidate"]["copy_id"] == done["result"]["steps"][0]["copy_id"]


def test_copy_replay_preserves_original_run(client, clock, copy_box):
    _, body, _, _, _ = copy_box
    headers = {**OWNER, "Idempotency-Key": "retry-before-next-backup"}
    first = client.post(START, headers=headers, json=body)
    assert first.status_code == 202, first.text
    clock.advance(1)
    run = client.post("/v1/backups/runs", headers=OWNER, json={"destination_id": body["destination_id"]})
    assert run.status_code == 202, run.text
    assert approve(client, run.json()["id"])["state"] == "succeeded"
    newer = client.post(START, headers=OWNER, json=body)
    assert newer.status_code == 202, newer.text
    assert newer.json()["params"]["run_id"] != first.json()["params"]["run_id"]
    replay = client.post(START, headers=headers, json=body)
    assert replay.status_code == 202, replay.text
    assert replay.headers["OneMind-Idempotent-Replay"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["params"] == first.json()["params"]
    other = client.post("/v1/backups/destinations", headers=OWNER, json={
        "kind": "usb", "label": "Other NAS", "config": {"usb_uuid": "other", "sovereign": True}, "approve": True})
    assert other.status_code == 202 and other.json()["state"] == "succeeded", other.text
    conflict = client.post(START, headers=headers,
                           json={**body, "destination_id": other.json()["params"]["destination_id"]})
    assert conflict.status_code == 409, conflict.text


def test_copy_replays_after_destination_removal(client, copy_box):
    _, body, _, _, _ = copy_box
    headers = {**OWNER, "Idempotency-Key": "retry-after-destination-removal"}
    first = client.post(START, headers=headers, json=body)
    assert first.status_code == 202, first.text
    removed = client.delete(f"/v1/backups/destinations/{body['destination_id']}", headers=OWNER)
    assert removed.status_code == 202, removed.text
    assert approve(client, removed.json()["id"])["state"] == "succeeded"

    replay = client.post(START, headers=headers, json=body)
    assert replay.status_code == 202, replay.text
    assert replay.headers["OneMind-Idempotent-Replay"] == "true"
    assert replay.json() == first.json()
    assert client.post(START, headers=OWNER, json=body).status_code == 404
    conflict = client.post(START, headers=headers, json={**body, "destination_id": "dst_0000000000000000"})
    assert conflict.status_code == 409, conflict.text


def test_sovereign_s3_endpoint_rejects_non_origins_before_approval(client, settings):
    path = "/v1/backups/destinations"
    before = client.get("/v1/actions", headers=OWNER).json()
    userinfo = "fixture-user:fixture-secret"
    for endpoint in (
        f"https://{userinfo}@storage.example.test",
        "https://storage.example.test/?fixture-secret", "https://storage.example.test/#fixture-secret",
        "https://storage.example.test/path-fixture-secret", "https://storage.example.test/%2F",
        "https://storage.example.test?", "https://storage.example.test#", "https://storage.example.test:65536",
        "https://", "http://storage.example.test", "https://[::1]unexpected", "https://bad..example.test",
    ):
        response = client.post(path, headers=OWNER, json={
            "kind": "s3", "label": "S3", "config": {"endpoint": endpoint, "bucket": "bucket", "sovereign": True},
            "credentials": {"access_key": "test-access", "secret_key": "test-value"}})
        assert response.status_code == 422, response.text
        assert "fixture-secret" not in response.text
    assert client.get("/v1/actions", headers=OWNER).json() == before
    assert "fixture-secret" not in settings.audit_path.read_text()
    for endpoint in ("https://storage.example.test:9443/", "https://[2001:db8::1]:9443"):
        response = client.post(path, headers=OWNER, json={
            "kind": "s3", "label": "S3", "config": {"endpoint": endpoint, "bucket": "bucket", "sovereign": True},
            "credentials": {"access_key": "test-access", "secret_key": "test-value"}})
        assert response.status_code == 202 and response.json()["params"]["config"]["endpoint"] == endpoint, response.text


def test_sovereign_copy_openapi_keeps_migration_copy_body(client):
    schema = client.get("/openapi.json").json()
    operations = {method["operationId"]: method for path in schema["paths"].values() for method in path.values()}
    assert operations["backups.copies.request"]["requestBody"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/SovereignCopyBody")
    assert operations["migrate.copy"]["requestBody"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/CopyBody")


def start_copy(client, request):
    r = client.post(START, headers=OWNER, json=request)
    assert r.status_code == 202, r.text
    action = r.json()
    assert action["state"] == "awaiting_approval" and action["type"] == "box.export"
    assert request["recovery_key"] not in r.text
    done = approve(client, action["id"])
    assert done["state"] == "succeeded", done
    return done["result"]["steps"][0]["copy_id"]


def test_copy_requires_owner_and_approval(client, copy_box, settings):
    svc, request, box, root, _ = copy_box
    for principal in (ADULT, AGENT):
        assert client.post(START, headers=principal, json=request).status_code == 403
        assert client.post(DISCOVER, headers=principal, json={**request, "box_id": box, "root_fingerprint": root}).status_code == 403
    assert client.post(START, headers=OWNER, json={**request, "recovery_key": new_owner_key().password}).status_code == 409
    r = client.post(START, headers=OWNER, json=request)
    assert r.status_code == 202, r.text
    action = r.json()
    assert action["state"] == "awaiting_approval"
    assert request["recovery_key"] not in repr(svc.gw.actions.get(action["id"]))
    assert not svc.agent.objects
    assert policy_may_cover("box.export") and automatable("box.export")
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
    identity = client.app.state.identity
    original = identity.passkeys_active
    identity.passkeys_active = lambda: True
    needs_passkey = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert needs_passkey.status_code == 401 and needs_passkey.json()["reason"] == "step_up_required"
    assert not svc.agent.objects
    identity.passkeys_active = original
    done = approve(client, action["id"])
    assert done["state"] == "succeeded", done
    assert request["recovery_key"] not in repr(done)
    assert request["recovery_key"] not in settings.audit_path.read_text()
    assert b"ONEMIND-BOX-BUNDLE\n" in copy.unb64(next(iter(svc.agent.objects.values()))["bundle"])


def test_discovery_checks_signed_generation_then_time_and_falls_back(client, clock, copy_box):
    svc, request, box, root, _ = copy_box
    svc.agent.generation = 2
    good = start_copy(client, request)
    clock.advance(1)
    newer = start_copy(client, request)
    clock.advance(1)
    latest = start_copy(client, request)
    clock.advance(1)
    svc.agent.generation = 1
    old_generation = start_copy(client, request)

    def discover(**changes):
        r = client.post(DISCOVER, headers=OWNER, json={**request, "box_id": box, "root_fingerprint": root, **changes})
        assert r.status_code == 200, r.text
        return r.json()

    assert discover()["candidate"]["copy_id"] == latest
    svc.agent.objects[latest]["bundle"] = copy.b64(b"partially uploaded bundle")
    assert discover()["candidate"]["copy_id"] == newer
    svc.agent.damage.add(newer)
    result = discover()
    assert result["candidate"]["copy_id"] == good and result["rejected_candidates"] == 2
    raw = copy.decode(copy.unb64(svc.agent.objects[good]["record"]))
    raw["completion"]["body"]["generation"] = 200
    svc.agent.objects[good]["record"] = copy.b64(canonical(raw))
    assert discover()["candidate"]["copy_id"] == old_generation
    assert discover(root_fingerprint="0" * 64)["candidate"] is None
    assert discover(recovery_key=new_owner_key().password)["candidate"] is None
    saved = client.put("/v1/onboarding/settings", headers=OWNER,
                       json={"box_name": "fresh", "time_zone": "UTC", "backup_choice": "later"})
    assert saved.status_code == 200
    assert client.post(DISCOVER, headers=OWNER, json={**request, "box_id": box, "root_fingerprint": root}).status_code == 409


def test_bundle_rejects_validly_signed_damaged_payload_layers_and_refs(clock, copy_box):
    svc, request, box, _, signer = copy_box
    private = copy.recipient(request["recovery_key"])
    point = copy.References(repository="a" * 64, run_id="run-1", snapshots=["b" * 64],
                            units=[{"id": "b" * 64, "unit": "system", "app_id": None, "app_revision": None}])
    layer, excluded = box_config.layer(svc.gw.db)
    now = clock.now

    def seal(layer):
        return copy.seal(layer, point, Source(box, None, "1"), now, "c" * 32, signer, private.public_key(), excluded)

    def open_it(bundle, **changes):
        values = dict(format=1, box_id=box, copy_id="c" * 32, generation=0, created_at=now, backed_up_at=now,
                      size=len(bundle), sha256=sha256(bundle), repository=point.repository,
                      run_id=point.run_id, snapshots=point.snapshots)
        return copy.open_bundle(bundle, copy.Completion(**(values | changes)), signer.public_key(), private)

    bundle = seal(layer)
    assert open_it(bundle)[0]["bundle_id"] == "bnd_" + "c" * 32
    line, _, ciphertext = bundle[len(copy.MAGIC):].partition(b"\n")
    body = copy.decode(line)["body"]
    corrupted = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
    body["payload_sha256"] = sha256(corrupted)
    signed_damage = copy.MAGIC + canonical(copy.signed(b"envelope/", signer, body)) + b"\n" + corrupted
    with pytest.raises(InvalidTag):
        open_it(signed_damage)
    with pytest.raises(BundleRefused, match="checksum"):
        open_it(seal(replace(layer, data=b"x" + layer.data[1:])))
    with pytest.raises(copy.CopyRefused, match="references"):
        open_it(bundle, repository="f" * 64)
