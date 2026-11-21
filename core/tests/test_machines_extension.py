# SPDX-License-Identifier: Apache-2.0
"""The machines extension (MACH-2, #281): KubeVirt and CDI, turned on by an approved action.

Real gateway, real routes, real ledger and approval rule. The noop extension is what the noop executor
picks (it never touches a cluster); the kubectl extension is run with a scripted runner.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.executors import ExecResult
from onemind_core.machines.extension import FILES, KubectlExtension, Layer, NoopExtension

PC = {"schema": "onemind.node.status/v1", "node_id": "pc0123456789", "hostname": "beelink", "role": "hub",
      "board": "x86_64-efi", "arch": "amd64", "mem_total_mb": 15_800, "cpus": 8, "kvm": True,
      "k3s": {"present": True, "role": "server", "ready": True}}
VM = {"name": "web", "ram_mb": 2048, "cpus": 2, "disk_gb": 20, "image_url": "https://images.example.org/debian.qcow2"}
SHIPPED = Path(__file__).resolve().parents[2] / "os/rootfs/layers/machines/usr/lib/onemind/extensions/machines"


@pytest.fixture
def box(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        def report(**changes):
            hb = {**PC, **changes}
            assert app.state.registry.ingest(f"onemind.node.{hb['node_id']}.status", json.dumps(hb).encode())
        c.report, c.clock, c.n, c.svc = report, clock, 0, app.state.machines
        c.ask = lambda typ, params, who=OWNER: _ask(c, typ, params, who)
        yield c


def _ask(c, typ, params, who):
    c.n += 1
    return c.post("/v1/actions", headers=who, json={
        "type": typ, "params": params, "idempotency_key": f"k{c.n}", "expires_at": (c.clock.now + timedelta(minutes=10)).isoformat()})


def approve(c, action_id, who=OWNER):
    """Approve, then wait for the background install to settle (the answer to approve is `dispatched`)."""
    r = c.post(f"/v1/actions/{action_id}/approve", headers=who)
    if r.status_code != 200:
        return r
    for _ in range(200):
        r = c.get(f"/v1/actions/{action_id}", headers=OWNER)
        if r.json()["state"] != "dispatched":
            break
        time.sleep(0.02)
    return r


def caps(c):
    return c.get("/v1/machines/capabilities", headers=OWNER).json()


def layer_dir(tmp_path: Path, **override: bytes) -> Path:
    """A layer on disk: the four manifests (tiny stand-ins) and an extension.json with their real hashes."""
    bodies = {n: f"# stand-in for {n}\n".encode() for n in FILES} | override
    for n, b in bodies.items():
        (tmp_path / n).write_bytes(b)
    (tmp_path / "extension.json").write_text(json.dumps({"files": {n: hashlib.sha256(b).hexdigest() for n, b in bodies.items()}}))
    return tmp_path


# ---- the layer the image ships -------------------------------------------------------------------

def test_the_shipped_layer_lists_exactly_the_four_manifests_and_the_image_fetches_them_before_use(tmp_path):
    meta = json.loads((SHIPPED / "extension.json").read_text())
    assert set(meta["files"]) == set(FILES) and all(len(h) == 64 for h in meta["files"].values())
    layer, why = Layer.load(SHIPPED)  # the manifests are fetched at image build: absent in the repo
    assert layer is None and "missing" in why


def test_a_whole_layer_loads_and_a_changed_or_emulating_one_is_refused(tmp_path):
    ok, _ = Layer.load(layer_dir(tmp_path))
    assert ok is not None
    (tmp_path / "x").mkdir()
    bad = layer_dir(tmp_path / "x")
    (bad / "cdi-operator.yaml").write_bytes(b"tampered")
    layer, why = Layer.load(bad)
    assert layer is None and "cdi-operator.yaml" in why and "checksum" in why
    (tmp_path / "y").mkdir()
    emu = layer_dir(tmp_path / "y", **{"kubevirt-cr.yaml": b"spec:\n  configuration:\n    developerConfiguration:\n      useEmulation: true\n"})
    layer, why = Layer.load(emu)
    assert layer is None and "emulation" in why


# ---- refusals: small boxes, no KVM, no layer ------------------------------------------------------

@pytest.mark.parametrize("changes, code", [
    ({"board": "rpi5", "arch": "arm64", "mem_total_mb": 7_800, "kvm": False}, "not_x86"),
    ({"mem_total_mb": 7_800}, "memory_below_16gb"),
    ({"kvm": False}, "no_kvm"),
])
def test_a_pi_a_small_box_and_a_box_without_kvm_are_refused_with_reasons_on_both_routes(box, changes, code):
    box.report(**changes)
    for r in (box.post("/v1/machines/enable", headers=OWNER), box.ask("machines.enable", {})):
        assert r.status_code == 409, r.text
        assert r.json()["reason"] == "machines_unsupported"
    assert code in {d["code"] for d in box.post("/v1/machines/enable", headers=OWNER).json()["details"]}
    assert box.svc.repo.extension()["state"] == "absent"


def test_a_box_without_the_layer_says_so_and_never_runs_kubectl(box, tmp_path):
    box.report()
    box.svc.ext = KubectlExtension(tmp_path, runner=lambda *a, **k: pytest.fail("kubectl must not run"))
    r = box.post("/v1/machines/enable", headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "extension_unavailable"
    assert caps(box)["extension"]["state"] == "unavailable" and caps(box)["enabled"] is False


# ---- the approved path ----------------------------------------------------------------------------

def test_the_noop_path_never_touches_a_cluster(box, monkeypatch):
    assert isinstance(box.svc.ext, NoopExtension)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("the noop executor must not run any command"))
    box.report()
    queued = box.post("/v1/machines/enable", headers=OWNER)
    done = approve(box, queued.json()["id"])
    assert done.status_code == 200 and done.json()["state"] == "succeeded"
    assert done.json()["result"]["steps"][0]["would"].startswith("apply KubeVirt and CDI")


def test_owner_turns_machines_on_then_off_and_every_step_waits_for_approval(box):
    box.report()
    queued = box.post("/v1/machines/enable", headers=OWNER)
    assert queued.status_code == 202 and queued.json()["state"] == "awaiting_approval"
    again = box.post("/v1/machines/enable", headers=OWNER)  # a double click is the same request
    assert again.json()["id"] == queued.json()["id"]
    assert caps(box)["enabled"] is False and caps(box)["extension"]["state"] == "absent"
    assert approve(box, queued.json()["id"]).json()["state"] == "succeeded"
    assert caps(box)["enabled"] is True and caps(box)["extension"]["state"] == "ready"
    refused = box.post("/v1/machines/enable", headers=OWNER)
    assert refused.status_code == 409 and refused.json()["reason"] == "already_enabled"

    off = box.post("/v1/machines/disable", headers=OWNER)
    assert off.status_code == 202 and off.json()["type"] == "machines.disable"
    assert caps(box)["enabled"] is True  # still on until approved
    assert approve(box, off.json()["id"]).json()["state"] == "succeeded"
    assert caps(box)["enabled"] is False and caps(box)["extension"]["state"] == "absent"
    assert box.post("/v1/machines/disable", headers=OWNER).json()["reason"] == "already_off"


def test_an_agent_can_ask_but_never_approve_and_never_press_the_button(box):
    box.report()
    asked = box.ask("machines.enable", {}, AGENT)
    assert asked.status_code == 201 and asked.json()["state"] == "awaiting_approval"
    assert approve(box, asked.json()["id"], AGENT).status_code == 403
    assert caps(box)["enabled"] is False
    assert box.post("/v1/machines/enable", headers=AGENT).status_code == 403
    assert approve(box, asked.json()["id"]).json()["state"] == "succeeded"  # a person decides
    assert caps(box)["enabled"] is True


def test_turning_machines_off_is_refused_while_a_machine_exists(box):
    box.report()
    approve(box, box.post("/v1/machines/enable", headers=OWNER).json()["id"])
    create = box.ask("machine.create", VM)
    assert approve(box, create.json()["id"]).status_code == 200
    r = box.post("/v1/machines/disable", headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "machines_exist"
    assert box.ask("machines.disable", {}).status_code == 409


def test_the_request_takes_no_parameters(box):
    box.report()
    assert box.ask("machines.enable", {"use_emulation": True}).status_code == 422


class Failing:
    name = "fake"

    def __init__(self, outcome):
        self.outcome = outcome

    def available(self):
        return True, ""

    def install(self):
        return ExecResult(self.outcome, "kubectl exited 1", [])

    remove = install


def test_a_failed_install_stays_off_says_why_and_can_be_tried_again(box):
    box.report()
    box.svc.ext = Failing("failed")
    done = approve(box, box.post("/v1/machines/enable", headers=OWNER).json()["id"]).json()
    assert done["state"] == "failed"
    c = caps(box)
    assert c["enabled"] is False and c["extension"]["state"] == "failed" and "kubectl exited 1" in c["extension"]["message"]
    box.svc.ext = NoopExtension()
    retry = box.ask("machines.enable", {})
    assert retry.status_code == 201
    assert approve(box, retry.json()["id"]).json()["state"] == "succeeded" and caps(box)["enabled"] is True


def test_an_install_with_an_unclear_end_is_marked_unknown_not_ready(box):
    box.report()
    box.svc.ext = Failing("outcome_unknown")
    approve(box, box.post("/v1/machines/enable", headers=OWNER).json()["id"])
    c = caps(box)
    assert c["enabled"] is False and c["extension"]["state"] == "unknown"


# ---- the kubectl extension, with a scripted runner ------------------------------------------------

class Script:
    def __init__(self, answers=None, fail_on=None, timeout_on=None):
        self.calls, self.answers, self.fail_on, self.timeout_on = [], answers or {}, fail_on, timeout_on

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        line = " ".join(argv)
        if self.timeout_on and self.timeout_on in line:
            raise subprocess.TimeoutExpired(argv, 1)
        if self.fail_on and self.fail_on in line:
            return subprocess.CompletedProcess(argv, 1, "", "boom")
        for key, out in self.answers.items():
            if key in line:
                return subprocess.CompletedProcess(argv, 0, out, "")
        return subprocess.CompletedProcess(argv, 0, "", "")


def test_install_applies_in_order_waits_and_checks_emulation_is_off(tmp_path):
    run = Script()
    res = KubectlExtension(layer_dir(tmp_path), allow_tag_images=True, runner=run).install()
    assert res.outcome == "succeeded"
    lines = [" ".join(c[1:]) for c in run.calls]
    order = [next(i for i, l in enumerate(lines) if k in l) for k in ("kubevirt-operator", "virt-operator", "kubevirt-cr", "cdi-operator", "deploy/cdi-operator", "cdi-cr")]
    assert order == sorted(order)
    assert all(not l.startswith("delete") for l in lines)


def test_install_refuses_a_cluster_that_runs_on_software_emulation(tmp_path):
    run = Script(answers={"useEmulation": "true"})
    res = KubectlExtension(layer_dir(tmp_path), allow_tag_images=True, runner=run).install()
    assert res.outcome == "failed" and "emulation" in res.message


def test_install_refuses_a_layer_whose_file_changed_before_any_kubectl_call(tmp_path):
    d = layer_dir(tmp_path)
    (d / "kubevirt-operator.yaml").write_bytes(b"changed")
    run = Script()
    assert KubectlExtension(d, allow_tag_images=True, runner=run).install().outcome == "failed" and run.calls == []


def test_install_outcomes_follow_the_executor_rules(tmp_path):
    d = layer_dir(tmp_path)
    assert KubectlExtension(d, allow_tag_images=True, runner=Script(fail_on="cdi-cr")).install().outcome == "failed"
    assert KubectlExtension(d, allow_tag_images=True, runner=Script(timeout_on="wait")).install().outcome == "outcome_unknown"
    assert KubectlExtension(d, allow_tag_images=True, kubectl="nope", runner=lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())).install().outcome == "failed"


def test_remove_succeeds_only_when_no_crd_or_webhook_is_left(tmp_path):
    d = layer_dir(tmp_path)
    clean = Script(answers={"get crd": "customresourcedefinition.apiextensions.k8s.io/certificates.cert-manager.io\n"})
    assert KubectlExtension(d, allow_tag_images=True, runner=clean).remove().outcome == "succeeded"
    dirty = Script(answers={"get crd": "customresourcedefinition.apiextensions.k8s.io/kubevirts.kubevirt.io\n"
                                       "validatingwebhookconfiguration.admissionregistration.k8s.io/virt-api-validator\n"})
    res = KubectlExtension(d, allow_tag_images=True, runner=dirty).remove()
    assert res.outcome == "failed" and "kubevirts.kubevirt.io" in res.message and "virt-api-validator" in res.message
    deletes = [" ".join(c[1:]) for c in clean.calls if "delete" in c]
    assert [("cdi-cr" in l, "cdi-operator" in l, "kubevirt kubevirt" in l, "kubevirt-operator" in l) for l in deletes] == [
        (True, False, False, False), (False, True, False, False), (False, False, True, False), (False, False, False, True)]


def test_install_and_enable_are_refused_while_the_images_are_only_tags(box, tmp_path):
    d = layer_dir(tmp_path)
    run = Script()
    ext = KubectlExtension(d, runner=run)  # default: tags not allowed
    res = ext.install()
    assert res.outcome == "failed" and "digest" in res.message and run.calls == []
    box.report()
    box.svc.ext = ext
    r = box.post("/v1/machines/enable", headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "extension_unavailable"
    assert run.calls == [] and box.svc.repo.extension()["state"] == "absent"
    assert KubectlExtension(d, runner=run, allow_tag_images=True).available() == (True, "")


def test_the_tag_switch_is_off_unless_the_environment_sets_it():
    from onemind_core.config import Settings
    assert Settings.from_env({}).machines_allow_tag_images is False
    assert Settings.from_env({"ONEMIND_MACHINES_ALLOW_TAG_IMAGES": "1"}).machines_allow_tag_images is True
