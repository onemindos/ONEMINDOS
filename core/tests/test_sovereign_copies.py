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

START = "/v1/backups/copies"
DISCOVER = "/v1/onboarding/restore/copy"


class CopyAgent(FakeAgent):
    def __init__(self, clock):
        super().__init__(clock)
        self.objects = {}
        self.damage = set()
        self.generation = 0
        self.repository = sha256(b"test repository")

    def job(self, kind, params, *, action_id=None, timeout=None):
        if kind != "backup.copy":
            return super().job(kind, params, action_id=action_id, timeout=timeout)
        self.jobs.append((kind, params, action_id))
        op, cid = params["operation"], params.get("copy_id")
        if op == "prepare":
            return {"repository": self.repository, "generation": self.generation,
                    "snapshots": [s for s in self.snaps if s["id"] in params["snapshots"]]}
        if op == "publish":
            assert action_id and params["repository"] == self.repository
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


@pytest.fixture
def copy_box(client, clock, tmp_path):
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

    dest = client.post("/v1/backups/destinations", headers=OWNER, json={
        "kind": "usb", "label": "Owner NAS", "config": {"usb_uuid": "nas", "sovereign": True}}).json()
    assert approve(client, dest["id"])["state"] == "succeeded"
    dest_id = dest["params"]["destination_id"]
    assert svc.agent.jobs[-1][1]["targets"][0]["sovereign"] is True
    issued = client.post("/v1/backups/kit", headers=OWNER).json()
    kit = issued["one_time"]
    answers = {str(i): kit["groups"][i - 1] for i in issued["kit"]["positions"]}
    assert client.post("/v1/backups/kit/confirm", headers=OWNER, json={"answers": answers}).status_code == 200
    run = client.post("/v1/backups/runs", headers=OWNER, json={"destination_id": dest_id}).json()
    assert approve(client, run["id"])["state"] == "succeeded"

    return svc, {"destination_id": dest_id, "recovery_key": kit["owner_key"]}, box, sha256(root_pub), signer


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
