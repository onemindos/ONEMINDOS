# SPDX-License-Identifier: Apache-2.0
"""Device grants (#690): USB and GPU passthrough to a machine, only with the owner's approval.

Real gateway, real routes, real ledger and approval rule; the device runtime is the noop one the
gateway picks with the noop executor, and the kubectl one runs against a scripted runner. One test
per refusal of the issue: a busy device until the owner confirms, a GPU sharing its IOMMU group or
in no group the box reported, and an agent's request that no person approved. Virtual machines
stay gated off on real hardware until LT-MACH-2; lab-kits/LT-MACH-DEV-01 is the VT-d test.
"""

from __future__ import annotations

import copy
import json
import subprocess
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.automation.registry import policy_may_cover
from onemind_core.machines.devices import KubectlDevices, kubevirt_patch, vm_patch

GPU = {"class": "gpu", "model": None, "driver_version": None, "vram_mb": None, "compute_capability": None, "device": None}
CAPS = {
    "schema": "onemind.node.capabilities/v1", "data_disk": {"kind": "nvme", "ssd": True},
    "memory": {"total_mb": 31_800, "unified": False},
    "accelerators": [
        {**GPU, "vendor": "intel", "pci_id": "8086:46d1", "pci_slot": "0000:00:02.0", "driver": "i915", "integrated": True},
        # The spare card, already bound to vfio-pci (lab kit step 3): free, and alone in its group with its HDMI audio.
        {**GPU, "vendor": "nvidia", "pci_id": "10de:2882", "pci_slot": "0000:01:00.0", "driver": "vfio-pci", "integrated": False},
        {**GPU, "vendor": "amd", "pci_id": "1002:744c", "pci_slot": "0000:05:00.0", "driver": None, "integrated": False},
    ],
    "usb": [{"port": "1-1", "id": "046d:c31c", "class": "00", "interface_classes": ["03"]},
            {"port": "1-2", "id": "0781:5583", "class": "00", "interface_classes": ["08"]},
            {"port": "1-3", "id": "1a86:55d4", "class": "ff", "interface_classes": ["ff"]}],
    "tty_ports": [], "radios": [], "cameras": [],
    "power": {"source": "mains", "battery_pct": None, "undervoltage": None}, "thermal": {"max_c": 45.0, "state": "normal"},
    "passthrough": {
        "iommu_groups": [{"group": 0, "devices": ["0000:00:02.0"]}, {"group": 1, "devices": ["0000:01:00.0", "0000:01:00.1"]},
                         {"group": 7, "devices": ["0000:05:00.0", "0000:06:00.0"]}],
        "usb_drivers": {"1-1": ["usbhid"], "1-2": ["usb-storage"]},
    },
}
PC = {"schema": "onemind.node.status/v1", "node_id": "pc0123456789", "hostname": "tower", "role": "hub",
      "board": "x86_64-efi", "arch": "amd64", "mem_total_mb": 31_800, "cpus": 8, "kvm": True,
      "k3s": {"present": True, "role": "server", "ready": True}, "capabilities": CAPS}
VM = {"name": "win", "ram_mb": 4096, "cpus": 2, "disk_gb": 40, "image_url": "https://images.example.org/debian.qcow2"}
SPARE = {"name": "win", "kind": "gpu", "device": "0000:01:00.0"}


@pytest.fixture
def box(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        def report(caps=CAPS):
            hb = {**PC, "capabilities": caps}
            if caps is None:
                hb.pop("capabilities")
            assert app.state.registry.ingest(f"onemind.node.{PC['node_id']}.status", json.dumps(hb).encode())
        c.report, c.n = report, 0

        def ask(typ, params, who=OWNER):
            c.n += 1
            return c.post("/v1/actions", headers=who, json={
                "type": typ, "params": params, "idempotency_key": f"k{c.n}",
                "expires_at": (clock.now + timedelta(minutes=10)).isoformat()})
        c.ask = ask
        report()
        done(c, "machine.create", VM)
        yield c


def done(c, typ, params, who=OWNER):
    r = c.ask(typ, params, who)
    assert r.status_code == 201, r.text
    a = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert a.status_code == 200 and a.json()["state"] == "succeeded", a.text
    return a.json()


def refused(r, reason):
    assert r.status_code == 409 and r.json()["reason"] == reason, r.text


def device(c, kind, dev, machine="win"):
    rows = c.get(f"/v1/machines/{machine}/devices", headers=OWNER).json()["devices"]
    return next(d for d in rows if d["kind"] == kind and d["device"] == dev)


def test_owner_grants_a_free_gpu_that_applies_at_the_next_start_and_takes_it_back(box):
    inv = box.get("/v1/machines/win/devices", headers=OWNER).json()
    assert inv["iommu"] is True and inv["applies"] == "next_start"
    spare = device(box, "gpu", "0000:01:00.0")
    assert spare["refusal"] is None and spare["busy"] is False and spare["granted_to"] is None
    queued = box.ask("machine.attach_device", SPARE)
    assert queued.status_code == 201 and queued.json()["state"] == "awaiting_approval"
    assert device(box, "gpu", "0000:01:00.0")["granted_to"] is None  # nothing before approval
    a = box.post(f"/v1/actions/{queued.json()['id']}/approve", headers=OWNER).json()
    assert a["state"] == "succeeded" and "next time win starts" in a["result"]["message"], a
    assert device(box, "gpu", "0000:01:00.0")["granted_to"] == "win"
    refused(box.ask("machine.attach_device", SPARE), "already_granted")
    done(box, "machine.detach_device", {"name": "win", "kind": "gpu", "device": "0000:01:00.0"})
    assert device(box, "gpu", "0000:01:00.0")["granted_to"] is None


def test_a_busy_usb_device_is_refused_until_the_owner_confirms(box):
    stick = device(box, "usb", "1-2")
    assert stick["busy"] is True and stick["drivers"] == ["usb-storage"] and stick["refusal"]["code"] == "device_busy"
    r = box.ask("machine.attach_device", {"name": "win", "kind": "usb", "device": "1-2"})
    refused(r, "device_busy")
    assert "usb-storage" in r.json()["message"]
    done(box, "machine.attach_device", {"name": "win", "kind": "usb", "device": "1-2", "confirm_busy": True})
    assert device(box, "usb", "1-2")["granted_to"] == "win"
    # A dongle no driver holds is free without a confirmation.
    assert device(box, "usb", "1-3")["busy"] is False
    done(box, "machine.attach_device", {"name": "win", "kind": "usb", "device": "1-3"})


def test_a_gpu_the_host_drives_is_busy_until_the_owner_confirms(box):
    refused(box.ask("machine.attach_device", {"name": "win", "kind": "gpu", "device": "0000:00:02.0"}), "device_busy")


def test_a_gpu_sharing_its_iommu_group_is_refused_even_when_confirmed(box):
    r = box.ask("machine.attach_device", {"name": "win", "kind": "gpu", "device": "0000:05:00.0", "confirm_busy": True})
    refused(r, "iommu_group_shared")
    assert "0000:06:00.0" in r.json()["message"]
    assert device(box, "gpu", "0000:05:00.0")["refusal"]["code"] == "iommu_group_shared"


def test_a_gpu_in_no_reported_group_is_refused_even_when_confirmed(box):
    # The Go probe leaves out a group whose members are not all PCI addresses (an ACPI or platform
    # device under VT-d ANDD, an ARM SMMU client): such a member would go to the machine with the
    # card, so the group cannot be vouched for. The card then sits in no reported group.
    queued = box.ask("machine.attach_device", SPARE).json()
    caps = copy.deepcopy(CAPS)
    caps["passthrough"]["iommu_groups"] = [g for g in caps["passthrough"]["iommu_groups"] if g["group"] != 1]
    box.report(caps)
    r = box.ask("machine.attach_device", {**SPARE, "confirm_busy": True})
    refused(r, "iommu_group_unknown")
    assert device(box, "gpu", "0000:01:00.0")["refusal"]["code"] == "iommu_group_unknown"
    # A grant queued while the group still looked isolated is checked again at approval.
    a = box.post(f"/v1/actions/{queued['id']}/approve", headers=OWNER)
    assert a.status_code == 409 and a.json()["error"] == "stale_precondition", a.text
    assert device(box, "gpu", "0000:01:00.0")["granted_to"] is None


def test_an_agent_request_is_never_granted_without_a_person(box):
    r = box.ask("machine.attach_device", SPARE, AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval" and r.json()["requested_by"]["kind"] == "agent"
    assert box.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
    assert box.get(f"/v1/actions/{r.json()['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert device(box, "gpu", "0000:01:00.0")["granted_to"] is None
    assert policy_may_cover("machine.attach_device", SPARE) is not None  # no standing approval covers it
    # Confirming that a busy device may be taken from the host is the owner's word, never an agent's.
    refused(box.ask("machine.attach_device", {"name": "win", "kind": "usb", "device": "1-2", "confirm_busy": True}, AGENT),
            "owner_confirms")


def test_a_box_without_an_iommu_refuses_every_grant(box):
    box.report({k: v for k, v in CAPS.items() if k != "passthrough"})
    assert box.get("/v1/machines/win/devices", headers=OWNER).json()["iommu"] is False
    refused(box.ask("machine.attach_device", SPARE), "iommu_off")
    box.report(None)
    refused(box.ask("machine.attach_device", SPARE), "no_profile")


def test_unknown_taken_and_ungranted_devices(box):
    refused(box.ask("machine.attach_device", {"name": "win", "kind": "usb", "device": "2-9"}), "device_unknown")
    refused(box.ask("machine.attach_device", {**SPARE, "name": "ghost"}), "machine_unknown")
    refused(box.ask("machine.detach_device", {"name": "win", "kind": "gpu", "device": "0000:01:00.0"}), "not_granted")
    done(box, "machine.create", {**VM, "name": "lab"})
    done(box, "machine.attach_device", SPARE)
    refused(box.ask("machine.attach_device", {**SPARE, "name": "lab"}), "device_granted")


def test_the_device_is_checked_again_at_approval(box):
    queued = box.ask("machine.attach_device", {"name": "win", "kind": "usb", "device": "1-3"}).json()
    caps = copy.deepcopy(CAPS)
    caps["passthrough"]["usb_drivers"]["1-3"] = ["ch341"]  # the host took it in between
    box.report(caps)
    r = box.post(f"/v1/actions/{queued['id']}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition", r.text
    assert box.get(f"/v1/actions/{queued['id']}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_params_are_strict(box):
    for bad in ({**SPARE, "device": "1-2"}, {**SPARE, "kind": "pci"}, {"name": "win", "kind": "usb", "device": "0000:01:00.0"},
                {**SPARE, "extra": 1}):
        assert box.ask("machine.attach_device", bad).status_code == 422, bad


def test_the_devices_route(box):
    assert box.get("/v1/machines/ghost/devices", headers=OWNER).status_code == 404
    assert box.get("/v1/machines/win/devices").status_code == 401


def test_kubevirt_is_told_which_devices_it_may_hand_out_and_the_machine_which_it_gets():
    grants = [{"machine": "win", "kind": "gpu", "hw_id": "10de:2882"}, {"machine": "win", "kind": "usb", "hw_id": "0781:5583"},
              {"machine": "lab", "kind": "usb", "hw_id": "1a86:55d4"}]
    phd = kubevirt_patch(grants)["spec"]["configuration"]["permittedHostDevices"]
    assert phd["pciHostDevices"] == [{"pciVendorSelector": "10DE:2882", "resourceName": "onemind.io/gpu-10de-2882"}]
    assert phd["usb"] == [{"resourceName": "onemind.io/usb-0781-5583", "selectors": [{"vendor": "0781", "product": "5583"}]},
                          {"resourceName": "onemind.io/usb-1a86-55d4", "selectors": [{"vendor": "1a86", "product": "55d4"}]}]
    devs = vm_patch([g for g in grants if g["machine"] == "win"])["spec"]["template"]["spec"]["domain"]["devices"]
    assert devs == {"gpus": [{"name": "gpu0", "deviceName": "onemind.io/gpu-10de-2882"}],
                    "hostDevices": [{"name": "usb0", "deviceName": "onemind.io/usb-0781-5583"}]}
    # Taking the last device back writes empty lists, so nothing stays permitted.
    assert kubevirt_patch([])["spec"]["configuration"]["permittedHostDevices"] == {"pciHostDevices": [], "usb": []}

    calls = []

    def runner(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")
    res = KubectlDevices("kubectl", runner=runner).apply("win", grants, grants[:2])
    assert res.outcome == "succeeded"
    assert calls[0][:6] == ["kubectl", "patch", "kubevirt", "kubevirt", "-n", "kubevirt"]
    assert calls[1][:4] == ["kubectl", "patch", "virtualmachine", "win"]
    assert json.loads(calls[1][-1]) == vm_patch(grants[:2])
