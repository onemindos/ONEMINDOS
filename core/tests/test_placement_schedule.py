# SPDX-License-Identifier: Apache-2.0
"""CORE-FABRIC-4 (#171), second slice: RAM and GPU fit, and the verdict written into the pods.

Done when: with a hub and a worker, a big app (Ollama) is placed on the worker and its pods are
pinned there; an app that asks for a GPU gets the runtime class and a GPU limit; asking for more
cards or card memory than a machine reports is refused; and the machine goes into the plan the
owner approves, so a different machine is a different plan.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import OWNER, FakeKubectl, make_client
from onemind_core import placement, policy
from onemind_core.catalog import AppEntry
from onemind_core.executors import KubernetesExecutor
from onemind_core.lifecycle import ExecContext
from test_appstore import CtxSpyExecutor, add_app, install
from test_cpufit import ingest

REPO = Path(__file__).resolve().parents[2]
RULES = policy.load_rules(REPO / "sdk" / "policy" / "app-objects.yaml")

HUB = {"node_id": "hub1", "hostname": "Hub-One", "role": "hub", "status": "online", "arch": "amd64",
       "gpu": {"nvidia": False, "model": None}, "mem_total_mb": 16000, "mem_available_mb": 11000,
       "k3s": {"present": True, "ready": True}}
WORKER = {**HUB, "node_id": "wk1", "hostname": "R530-Worker", "role": "node", "mem_total_mb": 78000,
          "mem_available_mb": 70000, "fabric": {"role": "worker", "leaf_link": "up"}}
GPU_BOX = {**WORKER, "node_id": "gpu1", "hostname": "gpu-box",
           "gpu": {"nvidia": True, "model": "RTX", "count": 2, "vram_mb": 16384}}


def app(requires: dict) -> dict:
    return {"metadata": {"id": "ollama", "name": "Ollama"},
            "spec": {"archs": ["amd64"], "requires": {"gpu": False, "minMemoryMb": 64, **requires}}}


# ---- RAM: a big app does not take the hub's room ------------------------------------------------

def test_a_big_app_lands_on_the_worker_not_the_hub():
    big = app({"minMemoryMb": 4096})
    got = placement.place(big, [HUB, WORKER])
    assert got["verdict"] == "elsewhere" and got["node_id"] == "wk1"
    hub_line = next(n for n in got["nodes"] if n["node_id"] == "hub1")
    assert hub_line["verdict"] == "fits_with_warning" and hub_line["reasons"][0]["code"] == "hub_heavy"


def test_a_small_app_stays_on_the_hub():
    assert placement.place(app({"minMemoryMb": 1024}), [HUB, WORKER])["verdict"] == "here"


def test_a_big_app_still_runs_on_a_hub_with_no_second_machine():
    got = placement.place(app({"minMemoryMb": 4096}), [HUB])
    assert got["verdict"] == "here" and "big app for the hub" in got["message"]


def test_an_app_bigger_than_every_machine_is_refused():
    got = placement.place(app({"minMemoryMb": 90000}), [HUB, WORKER])
    assert got["verdict"] == "nowhere" and "78000 MB in all" in got["message"]


# ---- GPU: how many cards, how much card memory ------------------------------------------------------

@pytest.mark.parametrize("requires, code", [
    ({"gpuCount": 3}, "gpu_count_too_low"),
    ({"minVramMb": 24000}, "gpu_vram_too_small"),
])
def test_more_cards_or_card_memory_than_reported_is_refused(requires, code):
    line = placement.assess(app({"gpu": True, **requires}), GPU_BOX)
    assert line["verdict"] == "no" and [r["code"] for r in line["reasons"]] == [code]


def test_a_number_the_node_did_not_report_is_refused_not_assumed():
    old = {**GPU_BOX, "gpu": {"nvidia": True, "model": "RTX"}}
    assert placement.assess(app({"gpu": True, "minVramMb": 8000}), old)["reasons"][0]["code"] == "gpu_vram_unknown"
    assert placement.assess(app({"gpu": True, "gpuCount": 2}), old)["reasons"][0]["code"] == "gpu_count_unknown"
    assert placement.assess(app({"gpu": True}), old)["verdict"] == "fits"  # one card, no size asked


def test_a_fitting_gpu_box_wins():
    got = placement.place(app({"gpu": True, "gpuCount": 2, "minVramMb": 16000}), [HUB, WORKER, GPU_BOX])
    assert got["verdict"] == "elsewhere" and got["node_id"] == "gpu1"


# ---- the schedule ------------------------------------------------------------------------------------

def test_schedule_pins_to_another_machine_by_hostname_and_asks_for_the_gpu():
    s = placement.schedule(app({"gpu": True, "gpuCount": 2}), [HUB, GPU_BOX])
    assert s == {"node_id": "gpu1", "hostname": "gpu-box", "pin": True, "gpu": {"count": 2}}
    s = placement.schedule(app({"minMemoryMb": 4096}), [HUB, WORKER])
    assert s == {"node_id": "wk1", "hostname": "r530-worker", "pin": True, "gpu": None}  # k3s lowercases


def test_schedule_is_none_when_nothing_changes():
    assert placement.schedule(app({}), [HUB, WORKER]) is None  # on the hub, no GPU
    assert placement.schedule(app({}), []) is None  # nobody reported
    assert placement.schedule(app({"gpu": True}), [HUB]) is None  # nowhere: the install is refused anyway


def test_a_worker_without_a_hostname_is_not_pinned():
    nameless = {k: v for k, v in WORKER.items() if k != "hostname"}
    s = placement.schedule(app({"minMemoryMb": 4096}), [HUB, nameless])
    assert s is None


def test_apply_writes_the_schedule_into_the_pod_template_only():
    docs = [{"kind": "Deployment", "metadata": {"name": "a"}, "spec": {"template": {"spec": {
        "nodeSelector": {"disk": "ssd"}, "containers": [{"name": "main"}, {"name": "side"}]}}}},
        {"kind": "Service", "metadata": {"name": "a"}, "spec": {}}]
    out = placement.apply(docs, {"node_id": "gpu1", "hostname": "gpu-box", "pin": True, "gpu": {"count": 2}})
    pod = out[0]["spec"]["template"]["spec"]
    assert pod["nodeSelector"] == {"disk": "ssd", "kubernetes.io/hostname": "gpu-box"}
    assert pod["runtimeClassName"] == "nvidia"
    assert pod["containers"][0]["resources"]["limits"] == {"nvidia.com/gpu": "2"}
    assert "resources" not in pod["containers"][1]  # sidecars take no card
    assert out[1] == docs[1]
    assert "nodeSelector" not in docs[0]["spec"]["template"]["spec"]["containers"][0]  # input untouched
    assert "runtimeClassName" not in docs[0]["spec"]["template"]["spec"]


# ---- the executor: what is applied is what was checked ---------------------------------------------

def _entry(tmp_path: Path) -> AppEntry:
    d = tmp_path / "ollama"
    shutil.copytree(REPO / "sdk" / "policy" / "fixtures" / "good-minimal", d)
    manifest = yaml.safe_load((d / "onemind.app.yaml").read_text())
    manifest["metadata"]["id"] = "ollama"
    return AppEntry(id="ollama", dir=d, manifest=manifest)


def test_install_applies_the_pinned_gpu_pods_and_records_it_in_the_plan(tmp_path):
    k = FakeKubectl()
    sched = {"node_id": "gpu1", "hostname": "gpu-box", "pin": True, "gpu": {"count": 1}}
    res = KubernetesExecutor(runner=k, rules=RULES).run("app.install", _entry(tmp_path), ctx=ExecContext(placement=sched))
    assert res.outcome == "succeeded", res.message
    applied = list(yaml.safe_load_all(k.cluster_calls[-1][1]))
    dep = next(d for d in applied if d["kind"] == "Deployment")
    pod = dep["spec"]["template"]["spec"]
    assert pod["nodeSelector"] == {"kubernetes.io/hostname": "gpu-box"} and pod["runtimeClassName"] == "nvidia"
    assert pod["containers"][0]["resources"]["limits"]["nvidia.com/gpu"] == "1"
    assert res.plan["placement"] == sched


def test_install_without_a_schedule_applies_exactly_the_render(tmp_path):
    k = FakeKubectl()
    res = KubernetesExecutor(runner=k, rules=RULES).run("app.install", _entry(tmp_path), ctx=ExecContext())
    assert res.outcome == "succeeded" and "placement" not in res.plan
    assert "nodeSelector" not in k.cluster_calls[-1][1] and "runtimeClassName" not in k.cluster_calls[-1][1]


# ---- through the gateway: refused, planned, and hashed -----------------------------------------------

@pytest.fixture
def client(settings, clock, executor):
    add_app(settings, clock, "ollama", requires={"gpu": False, "minMemoryMb": 4096})
    with make_client(settings, clock, executor) as c:
        yield c


def _plan_hash(client, node_ids: list[str]) -> tuple[str, dict]:
    for nid in node_ids:
        ingest(client, node_id=nid, role="hub" if nid == "hub1" else "node", hostname=nid, mem_total_mb=16000,
               mem_available_mb=11000)
    r = client.get("/v1/apps/ollama/plan", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()["plan_sha256"], r.json()["plan"]


def test_the_plan_names_the_machine_and_a_different_machine_is_a_different_plan(client):
    alone, plan_alone = _plan_hash(client, ["hub1"])
    assert plan_alone["nodes"] == []  # on the hub: the plan is what it always was
    with_worker, plan = _plan_hash(client, ["wk1"])
    assert plan["nodes"] == [{"node_id": "wk1", "pinned": True, "gpu": None}]
    assert any("not the hub" in w for w in plan["warnings"])
    assert with_worker != alone


def test_the_executor_receives_the_schedule_of_the_approved_machine(settings, clock):
    add_app(settings, clock, "ollama", requires={"gpu": False, "minMemoryMb": 4096})
    spy = CtxSpyExecutor()
    with make_client(settings, clock, spy) as c:
        ingest(c, node_id="hub1", role="hub", hostname="hub1", mem_total_mb=16000, mem_available_mb=11000)
        ingest(c, node_id="wk1", role="node", hostname="Wk1", mem_total_mb=64000, mem_available_mb=60000)
        install(c, clock, "ollama")
    ctx = [x for t, x in spy.ctxs if t == "app.install"][0]
    assert ctx.placement == {"node_id": "wk1", "hostname": "wk1", "pin": True, "gpu": None}
