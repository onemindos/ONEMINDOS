# SPDX-License-Identifier: Apache-2.0
"""#724: one requires / recommends / supports block, with the older requires keys mapped onto it.

Pure checks on `onemind_core.machine_needs` over every app in apps/, then the fit code (cpufit, gpufit,
placement) on a manifest in the new spelling, then the real gateway: GET /v1/apps lists a new-spelling app
and GET /v1/apps/{id}/placement refuses it on a machine without a GPU.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from conftest import OWNER, make_client
from onemind_core import cpufit, gpufit, placement
from onemind_core.catalog import Catalog
from onemind_core.machine_needs import base_arch, errors, legacy_requires, machine_needs, overlays
from test_appstore import add_app
from test_cpufit import ingest

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "sdk" / "schema" / "onemind.app.schema.json"
HUB = {"node_id": "hub1", "role": "hub", "status": "online", "arch": "amd64", "cpu_level": "x86-64-v2",
       "gpu": {"nvidia": False, "model": None}, "mem_total_mb": 16000, "mem_available_mb": 9000,
       "k3s": {"present": True, "ready": True}}
GPU_HUB = {**HUB, "gpu": {"nvidia": True, "model": "RTX 3060", "count": 1}}


def repo_apps() -> list[dict]:
    return [yaml.safe_load(p.read_text()) for p in sorted((REPO / "apps").rglob("onemind.app.yaml"))]


def app(requires: dict, archs=("amd64", "arm64"), **more) -> dict:
    return {"metadata": {"id": "sim", "name": "Sim"}, "spec": {"archs": list(archs), "requires": requires, **more}}


def new_spelling(doc: dict) -> dict:
    """The same app with spec.requires / recommends written in the new keys only."""
    doc = copy.deepcopy(doc)
    needs = machine_needs(doc["spec"])
    doc["spec"]["requires"] = needs["requires"]
    for name in ("recommends", "supports"):
        if needs[name]:
            doc["spec"][name] = needs[name]
    return doc


def test_every_app_in_the_repo_maps_onto_the_new_keys():
    docs = repo_apps()
    assert len(docs) >= 66
    for doc in docs:
        spec, req = doc["spec"], doc["spec"]["requires"]
        needs = machine_needs(spec)
        assert needs["requires"]["memoryMb"] == req["minMemoryMb"], doc["metadata"]["id"]
        assert [base_arch(a) for a in needs["requires"]["arch"]] == spec["archs"]
        assert legacy_requires(spec) == req, "an older manifest must come back unchanged"


def test_every_app_in_the_new_spelling_validates_and_fits_the_same():
    catalog = Catalog(REPO / "apps", SCHEMA)
    for doc in repo_apps():
        moved = new_spelling(doc)
        assert catalog.check_manifest(moved) == [], (doc["metadata"]["id"], moved["spec"]["requires"])
        for node in (HUB, GPU_HUB, {**HUB, "arch": "arm64"}):
            assert placement.assess(moved, node) == placement.assess(doc, node), doc["metadata"]["id"]
            assert gpufit.wants_overlay(moved, node) == gpufit.wants_overlay(doc, node)


def test_the_older_keys_map_onto_the_new_ones():
    older = {"gpu": True, "minMemoryMb": 4096, "gpuCount": 2, "minVramMb": 8192, "cpuLevel": {"amd64": "x86-64-v3"}}
    assert machine_needs(app(older)["spec"]) == {
        "requires": {"arch": ["x86-64-v3", "arm64"], "memoryMb": 4096,
                     "accelerator": {"capability": "gpu-compute", "minMemoryMb": 8192, "count": 2}},
        "recommends": {}, "supports": {}}
    optional = {"gpu": False, "minMemoryMb": 4096,
                "accelerator": {"capability": "gpu-compute", "minMemoryMb": 4096, "optional": True, "overlay": "manifests-gpu"}}
    needs = machine_needs(app(optional)["spec"])
    assert "accelerator" not in needs["requires"]
    assert needs["recommends"]["accelerator"] == {"capability": "gpu-compute", "minMemoryMb": 4096, "overlay": "manifests-gpu"}


def test_the_new_keys_are_checked_by_the_existing_fit_code():
    sim = app({"arch": ["x86-64-v3", "arm64"], "memoryMb": 32768,
               "accelerator": {"capability": "gpu-compute", "minMemoryMb": 16384, "rtCores": True, "count": 2}})
    assert cpufit.refusal(sim, HUB)[0] == "cpu_level_too_low"
    codes = {r["code"] for r in placement.assess(sim, {**HUB, "cpu_level": "x86-64-v4"})["reasons"]}
    assert {"gpu_missing", "memory_too_small"} <= codes
    codes = {r["code"] for r in placement.assess(sim, {**GPU_HUB, "cpu_level": "x86-64-v4", "mem_total_mb": 65536,
                                                       "mem_available_mb": 60000})["reasons"]}
    assert {"gpu_count_too_low", "gpu_vram_unknown"} <= codes
    assert gpufit.refusal(sim, {**HUB, "cpu_level": "x86-64-v4"})[0] == "gpu_missing"
    faster = app({"memoryMb": 4096}, recommends={"accelerator": {"capability": "gpu-compute", "overlay": "manifests-gpu"}})
    assert gpufit.refusal(faster, HUB) is None
    assert gpufit.wants_overlay(faster, GPU_HUB) == "manifests-gpu"
    assert overlays(faster["spec"]) == ["manifests-gpu"]


def test_rules_the_schema_cannot_say():
    assert errors(app({"minMemoryMb": 1, "memoryMb": 1})["spec"]) == [
        "spec/requires: minMemoryMb and memoryMb say the same thing; keep memoryMb"]
    assert errors(app({"memoryMb": 1, "devices": ["nvidia.com/gpu", "/dev/ttyUSB0", "serial-port"]})["spec"]) == [
        "spec/requires/devices/0: nvidia.com/gpu names a vendor or a host path; use a vendor-neutral name",
        "spec/requires/devices/1: /dev/ttyUSB0 names a vendor or a host path; use a vendor-neutral name"]
    assert errors(app({"memoryMb": 1, "arch": ["amd64", "x86-64-v2"]}, archs=["amd64"])["spec"]) == [
        "spec/requires/arch: amd64 is named twice"]
    assert errors(app({"memoryMb": 1, "arch": ["arm64"]})["spec"]) == [
        "spec/requires/arch: must name the same architectures as spec.archs"]
    assert errors(app({"memoryMb": 1, "arch": ["x86-64-v3", "arm64"]})["spec"]) == []


@pytest.fixture
def sim_client(settings, clock, executor):
    add_app(settings, clock, "sim", requires={"memoryMb": 64, "accelerator": {"capability": "gpu-compute", "rtCores": True}},
            supports={"radios": ["lora"], "models": {"quantisations": ["q4_k_m"]}})
    with make_client(settings, clock, executor) as c:
        yield c


def test_the_gateway_lists_and_enforces_the_new_spelling(sim_client):
    apps = {a["id"]: a for a in sim_client.get("/v1/apps", headers=OWNER).json()}
    assert apps["sim"]["requires"]["accelerator"]["rtCores"] is True
    ingest(sim_client, node_id="hub1", gpu={"nvidia": False, "model": None})
    body = sim_client.get("/v1/apps/sim/placement", headers=OWNER).json()
    assert body["verdict"] == "nowhere"
    assert "gpu_missing" in {r["code"] for n in body["nodes"] for r in n["reasons"]}
