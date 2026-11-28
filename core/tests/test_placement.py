# SPDX-License-Identifier: Apache-2.0
"""CORE-FABRIC-4 (#171): capability labels from onemindd facts, placement from `spec.requires`, and
the Market verdict per app (here / elsewhere / nowhere).

Done when: an app needing a GPU is placed on the GPU node and refused on a node without one. Pure
checks on `onemind_core.placement`, then the real gateway: heartbeats go into the node registry
exactly as from NATS, `GET /v1/apps/{id}/placement` answers, and `POST /v1/actions` refuses an
install no machine can run.
"""
from __future__ import annotations


import pytest

from conftest import OWNER, make_client
from onemind_core import placement
from onemind_core.machines.fit import fit
from test_appstore import add_app, install, request
from test_cpufit import ingest

GPU_APP = {"metadata": {"id": "ollama", "name": "Ollama"},
           "spec": {"archs": ["amd64", "arm64"], "requires": {"gpu": True, "minMemoryMb": 4096}}}
PLAIN_APP = {"metadata": {"id": "notes", "name": "Notes"},
             "spec": {"archs": ["amd64", "arm64"], "requires": {"gpu": False, "minMemoryMb": 64}}}

HUB = {"node_id": "hub1", "role": "hub", "status": "online", "arch": "amd64", "board": "x86_64-efi",
       "cpu_level": "x86-64-v3", "gpu": {"nvidia": False, "model": None}, "kvm": True,
       "mem_total_mb": 16000, "mem_available_mb": 9000, "k3s": {"present": True, "ready": True}}
GPU_NODE = {**HUB, "node_id": "gpu1", "role": "node", "board": "jetson-orin", "arch": "arm64", "cpu_level": "",
            "gpu": {"nvidia": True, "model": "Orin"}, "fabric": {"role": "worker", "leaf_link": "up"}}


# ---- labels -------------------------------------------------------------------------------------

def test_labels_come_from_the_heartbeat_facts():
    assert placement.labels(GPU_NODE) == {
        "onemind.io/arch": "arm64", "onemind.io/board": "jetson-orin", "onemind.io/role": "worker",
        "onemind.io/gpu": "nvidia", "onemind.io/kvm": "true", "onemind.io/memory-mb": "16000",
    }
    assert placement.labels(HUB)["onemind.io/gpu"] == "none"
    assert placement.labels(HUB)["onemind.io/cpu-level"] == "x86-64-v3"


def test_an_unreported_fact_gives_no_label():
    assert placement.labels({"node_id": "old", "role": "hub"}) == {"onemind.io/role": "hub"}


# ---- placement (the done-when, pure) -------------------------------------------------------------

def test_an_app_needing_a_gpu_is_placed_on_the_gpu_node():
    got = placement.place(GPU_APP, [HUB, GPU_NODE])
    assert got["verdict"] == "elsewhere" and got["node_id"] == "gpu1"
    assert got["message"] == "Ollama runs on another machine: gpu1."
    by = {n["node_id"]: n for n in got["nodes"]}
    assert by["gpu1"]["verdict"] == "fits"
    assert by["hub1"]["verdict"] == "no"
    assert [r["code"] for r in by["hub1"]["reasons"]] == ["gpu_missing"]


def test_an_app_needing_a_gpu_is_refused_where_no_node_has_one():
    got = placement.place(GPU_APP, [HUB])
    assert got["verdict"] == "nowhere" and got["node_id"] is None
    assert got["message"] == "Ollama cannot run on any machine here. Ollama needs a graphics card (GPU), and machine hub1 has none."


def test_an_older_agent_without_the_gpu_fact_is_not_guessed_to_have_one():
    old = {k: v for k, v in HUB.items() if k != "gpu"}
    line = placement.assess(GPU_APP, old)
    assert line["verdict"] == "no" and line["reasons"][0]["code"] == "gpu_unknown"


def test_an_app_without_needs_runs_here_on_the_hub():
    got = placement.place(PLAIN_APP, [GPU_NODE, HUB])
    assert got["verdict"] == "here" and got["node_id"] == "hub1"


def test_no_node_reported_is_unknown_not_nowhere():
    assert placement.place(GPU_APP, [])["verdict"] == "unknown"


def test_memory_too_small_blocks_and_busy_memory_warns():
    small = {**HUB, "mem_total_mb": 2000, "mem_available_mb": 1000}
    busy = {**HUB, "mem_available_mb": 1000}
    app = {**GPU_APP, "spec": {"requires": {"gpu": False, "minMemoryMb": 4096}}}
    assert placement.assess(app, small)["reasons"][0]["code"] == "memory_too_small"
    line = placement.assess(app, busy)
    assert line["verdict"] == "fits_with_warning" and line["reasons"][0]["code"] == "memory_busy"


def test_a_clean_fit_wins_over_a_warning_and_an_offline_worker_is_skipped():
    busy_hub = {**HUB, "gpu": {"nvidia": True}, "mem_available_mb": 100}
    assert placement.place(GPU_APP, [busy_hub, GPU_NODE])["node_id"] == "gpu1"
    assert placement.place(GPU_APP, [busy_hub, {**GPU_NODE, "status": "offline"}])["node_id"] == "hub1"


def test_a_leaf_never_runs_apps():
    leaf = {**GPU_NODE, "fabric": {"role": "leaf", "leaf_link": "up"}}
    assert placement.assess(GPU_APP, leaf)["reasons"][0]["code"] == "no_cluster"


def test_the_cpu_check_is_reused_per_node():
    app = {**PLAIN_APP, "spec": {"archs": ["amd64"], "requires": {"gpu": False, "minMemoryMb": 64}}}
    line = placement.assess(app, GPU_NODE)
    assert line["verdict"] == "no" and line["reasons"][0]["code"] == "arch_unsupported"
    assert "machine gpu1 is ARM (arm64)" in line["reasons"][0]["message"]


# ---- through the gateway ------------------------------------------------------------------------

@pytest.fixture
def gpu_client(settings, clock, executor):
    add_app(settings, clock, "ollama", requires={"gpu": True, "minMemoryMb": 64})
    add_app(settings, clock, "notes")
    with make_client(settings, clock, executor) as c:
        yield c


def test_the_market_verdict_endpoint_places_a_gpu_app_on_the_gpu_node(gpu_client):
    ingest(gpu_client, node_id="hub1", gpu={"nvidia": False, "model": None})
    ingest(gpu_client, node_id="gpu1", role="node", mem_total_mb=8192, gpu={"nvidia": True, "model": "Orin"})
    r = gpu_client.get("/v1/apps/ollama/placement", headers=OWNER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["app_id"] == "ollama" and body["verdict"] == "elsewhere" and body["node_id"] == "gpu1"
    assert {n["node_id"]: n["labels"]["onemind.io/gpu"] for n in body["nodes"]} == {"hub1": "none", "gpu1": "nvidia"}
    assert body["fit"]["passing_nodes"] == ["gpu1"]
    assert {row["node_id"]: row["verdict"] for row in body["fit"]["nodes"]} == {
        "hub1": "not-on-this-machine", "gpu1": "yes",
    }
    assert gpu_client.get("/v1/apps/notes/placement", headers=OWNER).json()["verdict"] == "here"


def test_install_refused_when_no_node_has_a_gpu(gpu_client, clock):
    ingest(gpu_client, node_id="hub1", gpu={"nvidia": False, "model": None})
    r = request(gpu_client, clock, "app.install", {"app_id": "ollama"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["reason"] == "no_node_fits"
    assert "needs a graphics card (GPU)" in body["message"]
    assert body["details"] == [{"field": "node:hub1", "problem": "gpu_missing"}]
    install(gpu_client, clock, "notes")  # an app without a GPU need still installs


def test_install_allowed_once_a_gpu_node_has_joined(gpu_client, clock):
    ingest(gpu_client, node_id="hub1", gpu={"nvidia": False, "model": None})
    ingest(gpu_client, node_id="gpu1", role="node", gpu={"nvidia": True, "model": "Orin"})
    install(gpu_client, clock, "ollama")


def test_a_silent_hub_does_not_block_installs(gpu_client, clock):
    ingest(gpu_client, node_id="hub1")
    clock.advance(300)
    install(gpu_client, clock, "notes")


def test_placement_of_an_unknown_app_is_404(gpu_client):
    assert gpu_client.get("/v1/apps/nope/placement", headers=OWNER).status_code == 404


def test_fit_reports_known_failures_and_unknown_profiles_without_changing_placement():
    app = {"metadata": {"id": "simulator"}, "spec": {"archs": ["amd64"], "requires": {
        "arch": ["x86-64-v3"], "memoryMb": 16_000, "accelerator": {"capability": "gpu-compute", "minMemoryMb": 12_000},
    }}}
    memory = {"mem_total_mb": 32_000, "mem_available_mb": 22_000}
    rtx = {**HUB, **memory, "node_id": "rtx", "role": "node", "gpu": {"nvidia": True, "vram_mb": 24_000}}
    unknown = {**rtx, "node_id": "unknown", "gpu": {"nvidia": True}}
    pi = {**HUB, "node_id": "pi", "arch": "arm64", "mem_total_mb": 8_000}
    x86 = {**HUB, **memory, "node_id": "x86"}
    nodes = [pi, x86, rtx, unknown]
    assert {row["node_id"]: row["verdict"] for row in fit(app, nodes)["nodes"]} == {
        "pi": "not-on-this-machine", "x86": "not-on-this-machine", "rtx": "yes", "unknown": "not-checked",
    }
    assert fit(app, nodes)["passing_nodes"] == ["rtx"]
    assert placement.place(app, nodes)["node_id"] == "rtx"


def test_fit_describes_the_optional_accelerator_as_a_performance_warning():
    app = {"spec": {"archs": ["amd64"], "requires": {"memoryMb": 1024},
                    "recommends": {"accelerator": {"capability": "gpu-compute", "minMemoryMb": 4096}}}}
    report = fit(app, [HUB])
    assert report["nodes"][0]["verdict"] == "yes-but-slow"
    assert report["passing_nodes"] == ["hub1"]
