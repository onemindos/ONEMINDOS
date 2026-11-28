# SPDX-License-Identifier: Apache-2.0
"""Owner approval binds real Files uploads to the machine and its CDI volumes."""
import hashlib
import json

import pytest

from onemind_core.errors import ApiError
from onemind_core.machines.media import CDIUpload
from files_support import ADULT, AGENT, OWNER, TUS, fc, files_root, files_settings, meta, upload
from test_machines_actions import PC, _ask, _guided_params


class Proxy:
    def __init__(self):
        self.sent = {}
        self.phases = {}

    def phase(self, name, action_id, volume, digest, *, authorize=False):
        assert action_id and name == "guest-os"
        return self.phases.get(volume, "UploadReady")

    def send(self, volume, stream, size):
        assert size == len(data := stream.read())
        self.sent[volume] = data
        self.phases[volume] = "Succeeded"


@pytest.fixture
def hub(fc, clock):
    fc.n, fc.clock = 0, clock
    svc = fc.app.state.machines
    svc.cdi = Proxy()
    svc.repo.move_extension("ready", clock(), only_from=("absent",))
    fc.app.state.registry.ingest(f"onemind.node.{PC['node_id']}.status", json.dumps(PC).encode())
    return fc


def stage(c, name, data, *, who=OWNER, root="home:owner"):
    created = c.post("/v1/files/uploads", headers={**who, **TUS, "Upload-Length": str(len(data)),
                     "Upload-Metadata": meta(root=root, filename=name)})
    assert created.status_code == 201, created.text
    path = created.headers["Location"]
    complete = c.patch(path, headers={**who, **TUS, "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream"}, content=data)
    assert complete.status_code == 204, complete.text
    return {"upload_id": path.rsplit("/", 1)[-1], "sha256": complete.headers["OneMind-File-Sha256"], "size_bytes": len(data)}


def ask(c, media, **kwargs):
    return _ask(c, "machine.create", {**_guided_params(), "source": media, **kwargs}, OWNER)


POST = "/v1/machines/guest-os/upload"


def test_two_approved_iso_transfers_resume_and_start_only_after_both(hub):
    src = {"kind": "iso", **stage(hub, "installer.iso", b"installer")}
    drivers = stage(hub, "drivers.iso", b"drivers")
    a = ask(hub, src, firmware="uefi", tpm=True, virtio_drivers=drivers)
    assert a.status_code == 201, a.text
    aid = a.json()["id"]
    assert hub.post(POST, headers=OWNER).status_code == 404
    assert hub.post(f"/v1/actions/{aid}/approve", headers=AGENT).status_code == 403
    assert hub.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()["state"] == "succeeded"
    svc = hub.app.state.machines
    proxy = svc.cdi
    assert svc.repo.get("guest-os")["state"] == "needs_media"
    assert hub.post(POST, headers=AGENT).status_code == 403
    assert hub.post(POST, headers=ADULT).status_code == 403
    assert _ask(hub, "machine.start", {"name": "guest-os"}, OWNER).status_code == 409
    proxy.phases["guest-os-drivers"] = "Pending"
    partial = hub.post(POST, headers=OWNER)
    assert partial.status_code == 409 and partial.json()["reason"] == "media_pending"
    assert proxy.sent == {"guest-os-installer": b"installer"}
    proxy.phases["guest-os-drivers"] = "UploadReady"
    result = hub.post(POST, headers=OWNER)
    assert result.status_code == 200, result.text
    assert result.json()["media"] == [{"volume": "guest-os-installer", "sha256": src["sha256"], "size_bytes": 9},
                                      {"volume": "guest-os-drivers", "sha256": drivers["sha256"], "size_bytes": 7}]
    assert proxy.sent["guest-os-drivers"] == b"drivers" and svc.repo.get("guest-os")["state"] == "stopped"
    proxy.send = lambda *_: pytest.fail("must not send an accepted volume twice")
    assert hub.post(POST, headers=OWNER).json() == result.json()


def test_wrong_owner_mismatch_and_modified_content_never_reach_cdi(hub):
    stolen = {"kind": "disk", **stage(hub, "adult.img", b"other", who=ADULT, root="home:adult")}
    assert ask(hub, stolen).status_code == 409
    src = {"kind": "disk", **stage(hub, "boot.img", b"boot")}
    assert ask(hub, {**src, "sha256": hashlib.sha256(b"else").hexdigest()}).status_code == 409
    assert ask(hub, {**src, "size_bytes": 1}).status_code == 409
    assert _ask(hub, "machine.create", {**_guided_params(), "source": src}, AGENT).status_code == 409
    a = ask(hub, src).json()["id"]
    assert hub.post(f"/v1/actions/{a}/approve", headers=OWNER).json()["state"] == "succeeded"
    assert upload(hub, OWNER, "home:owner", "/", "boot.img", b"same", overwrite=True).status_code == 204
    response = hub.post(POST, headers=OWNER)
    assert response.status_code == 409 and response.json()["reason"] == "media_changed"
    assert not hub.app.state.machines.cdi.sent
    assert hub.app.state.machines.repo.get("guest-os")["state"] == "needs_media"


def test_transfer_refuses_a_replaced_cluster_target(monkeypatch):
    cdi = CDIUpload("kubectl")
    objects = {
        "virtualmachine": {"metadata": {"uid": "vm-current", "labels": {"onemind.io/create-action": "approved"}},
                           "spec": {"runStrategy": "Halted", "template": {"spec": {"volumes": [{"dataVolume": {"name": "guest-disk"}}]}}}},
        "datavolume": {"metadata": {"uid": "dv-current", "ownerReferences": [{"controller": True, "kind": "VirtualMachine", "uid": "vm-current"}]},
                       "spec": {"source": {"upload": {}}}, "status": {"phase": "UploadReady"}},
        "persistentvolumeclaim": {"metadata": {"ownerReferences": [{"controller": True, "kind": "DataVolume", "uid": "dv-current"}]}},
    }
    monkeypatch.setattr(cdi, "_object", lambda ns, get, kind, name: objects[kind])
    assert cdi.phase("guest", "approved", "guest-disk", "digest") == "UploadReady"
    with pytest.raises(ApiError):
        cdi.phase("guest", "older-approval", "guest-disk", "digest")
    objects["datavolume"]["status"]["phase"] = "Failed"
    with pytest.raises(ApiError) as failed:
        cdi.phase("guest", "approved", "guest-disk", "digest")
    assert failed.value.reason == "media_failed"
    objects["datavolume"]["status"]["phase"] = "Succeeded"
    with pytest.raises(ApiError):
        cdi.phase("guest", "approved", "guest-disk", "digest")
    objects["datavolume"]["metadata"]["annotations"] = {"onemind.io/verified-upload": "approved/digest"}
    assert cdi.phase("guest", "approved", "guest-disk", "digest") == "Succeeded"
    objects["persistentvolumeclaim"]["metadata"]["ownerReferences"][0]["uid"] = "foreign"
    with pytest.raises(ApiError):
        cdi.phase("guest", "approved", "guest-disk", "digest")


def test_proxy_uses_cdi_service_certificate_and_volume_token_without_redirects(monkeypatch):
    import io
    import ssl
    import httpx

    cdi = CDIUpload("kubectl")
    # Any real CA certificate will do. The system store can be empty on a CI runner (lazy capath),
    # so take the first one from certifi's bundle, which httpx always ships with.
    import certifi
    bundle = open(certifi.where(), encoding="ascii").read()
    end = "-----END CERTIFICATE-----"
    ca = bundle[bundle.index("-----BEGIN CERTIFICATE-----"):bundle.index(end) + len(end)] + "\n"
    def objects(ns, *args, body=None):
        if args[0] == "create":
            assert ns == "machines" and body["spec"] == {"pvcName": "guest-disk"}
            return {"status": {"token": "test-upload-ticket"}}
        assert ns == "cdi"
        return {"data": {"ca-bundle.crt": ca}} if args[1] == "configmap" else {"spec": {"clusterIP": "192.0.2.23"}}
    monkeypatch.setattr(cdi, "_object", objects)
    reply = 200
    sends = []
    def handler(request):
        assert str(request.url) == "https://192.0.2.23/v1beta1/upload"
        assert request.headers["content-length"] == "5" and request.headers["authorization"] == "Bearer test-upload-ticket"
        assert request.extensions["sni_hostname"] == "cdi-uploadproxy.cdi.svc"
        sends.append(request.read())
        return httpx.Response(reply, headers={"Location": "https://example.org/elsewhere"})
    original = httpx.Client
    def client(*, verify, trust_env, timeout):
        assert verify.check_hostname and verify.verify_mode == ssl.CERT_REQUIRED and not trust_env
        return original(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "Client", client)
    cdi.send("guest-disk", io.BytesIO(b"image"), 5)
    reply = 307
    with pytest.raises(ApiError) as err:
        cdi.send("guest-disk", io.BytesIO(b"image"), 5)
    assert "test-upload-ticket" not in err.value.message and sends == [b"image", b"image"]


def test_foreign_cluster_disk_stops_import_before_vm_mutation():
    import subprocess
    from onemind_core.machines.runtime import KubectlRuntime
    from onemind_core.machines.spec import MachineCreateParams

    calls = []
    def runner(args, **opts):
        calls.append((args, opts["input"]))
        output = "persistentvolumeclaim/guest-os-disk" if "get" in args else ""
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")
    params = MachineCreateParams(**_guided_params(), source={"kind": "disk", "size_bytes": 9, "sha256": "a" * 64})
    assert KubectlRuntime(runner=runner).create(params, media_action="approved").outcome == "failed"
    assert len(calls) == 2 and json.loads(calls[0][1])["kind"] == "Namespace"
