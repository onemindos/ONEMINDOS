# SPDX-License-Identifier: Apache-2.0
"""S-5: an app declares the accelerator it needs in vendor-neutral words; a box without it is refused clearly.

Pure checks on `onemind_core.gpufit`, then the real gateway: a hub heartbeat goes into the node registry
as from NATS and `POST /v1/actions` answers 409 with a sentence a person can act on. No GPU is needed:
the heartbeat is what a GPU box would send (shape: internal/heartbeat GPU).
"""
from __future__ import annotations

import json

import pytest

from conftest import make_client
from onemind_core import gpufit
from test_appstore import add_app, install, request
from test_nodes_catalog import heartbeat

ACC = {"capability": "gpu-compute", "minMemoryMb": 8192}
NO_GPU = {"arch": "amd64", "gpu": {"nvidia": False, "model": None}}
GPU_8G = {"arch": "amd64", "gpu": {"nvidia": True, "model": "RTX 3060", "memory_mb": 12288}}
GPU_4G = {"arch": "amd64", "gpu": {"nvidia": True, "model": "GTX 1050", "memory_mb": 4096}}
GPU_UNSIZED = {"arch": "amd64", "gpu": {"nvidia": True, "model": "RTX 3060"}}


def manifest(requires, name="Ollama"):
    return {"metadata": {"id": "ollama", "name": name}, "spec": {"archs": ["amd64"], "requires": requires}}


def req(**acc):
    return {"gpu": True, "minMemoryMb": 4096, "accelerator": {**ACC, **acc}}


# ---- pure ---------------------------------------------------------------------------------------

def test_no_gpu_on_the_box_is_a_clear_refusal_not_a_crash():
    code, message, details = gpufit.refusal(manifest(req()), NO_GPU)
    assert code == "gpu_missing"
    assert message.startswith("Ollama needs a graphics card (GPU) and this box has none.")
    assert "GPU image" in message
    assert details[0]["field"] == "spec.requires.accelerator"


def test_gpu_true_alone_is_a_required_accelerator_of_any_size():
    plain = manifest({"gpu": True, "minMemoryMb": 64})
    assert gpufit.accelerator(plain) == {"capability": "gpu-compute", "minMemoryMb": 0,
                                         "optional": False, "overlay": None}
    assert gpufit.refusal(plain, NO_GPU)[0] == "gpu_missing"
    assert gpufit.refusal(plain, GPU_UNSIZED) is None


def test_a_gpu_with_enough_memory_fits():
    assert gpufit.refusal(manifest(req()), GPU_8G) is None


def test_a_gpu_with_too_little_memory_is_refused_with_both_numbers():
    code, message, details = gpufit.refusal(manifest(req()), GPU_4G)
    assert code == "gpu_memory_too_small"
    assert "8192 MB" in message and "4096 MB" in message
    assert details == [{"field": "spec.requires.accelerator.minMemoryMb", "problem": "needs 8192; box has 4096"}]


@pytest.mark.parametrize("node", [
    None,                                   # no hub has reported
    {"arch": "amd64"},                      # an older agent without the gpu object
    {"arch": "amd64", "gpu": "yes"},        # malformed
    {"arch": "amd64", "gpu": {}},           # no nvidia fact
    GPU_UNSIZED,                            # a GPU whose memory is not reported: size not guessed
])
def test_what_the_box_cannot_tell_is_not_guessed(node):
    assert gpufit.refusal(manifest(req()), node) is None


def test_an_optional_accelerator_never_refuses():
    optional = manifest({"gpu": False, "minMemoryMb": 4096, "accelerator": {**ACC, "optional": True}})
    assert gpufit.refusal(optional, NO_GPU) is None
    assert gpufit.refusal(optional, GPU_4G) is None


def test_an_app_with_no_accelerator_is_never_refused():
    assert gpufit.accelerator(manifest({"gpu": False, "minMemoryMb": 64})) is None
    assert gpufit.refusal(manifest({"gpu": False, "minMemoryMb": 64}), NO_GPU) is None


@pytest.mark.parametrize("bad", ["gpu-compute", ["gpu-compute"], {"capability": "tpu"}, {"capability": 7}, None])
def test_a_malformed_accelerator_is_ignored_not_a_crash(bad):
    assert gpufit.accelerator(manifest({"gpu": False, "minMemoryMb": 64, "accelerator": bad})) is None


def test_the_gpu_overlay_applies_only_on_a_box_with_a_big_enough_gpu():
    m = manifest({"gpu": False, "minMemoryMb": 4096,
                  "accelerator": {**ACC, "minMemoryMb": 4096, "optional": True, "overlay": "manifests-gpu"}})
    assert gpufit.wants_overlay(m, GPU_8G) == "manifests-gpu"
    assert gpufit.wants_overlay(m, GPU_4G) == "manifests-gpu"      # exactly 4096 is enough
    assert gpufit.wants_overlay(m, GPU_UNSIZED) == "manifests-gpu"
    assert gpufit.wants_overlay(m, NO_GPU) is None
    assert gpufit.wants_overlay(m, {"arch": "amd64"}) is None   # unknown: the safe CPU manifests
    assert gpufit.wants_overlay(m, None) is None
    small = manifest({"gpu": False, "minMemoryMb": 4096,
                      "accelerator": {**ACC, "minMemoryMb": 16384, "optional": True, "overlay": "manifests-gpu"}})
    assert gpufit.wants_overlay(small, GPU_8G) is None
    assert gpufit.wants_overlay(manifest({"gpu": False, "minMemoryMb": 64}), GPU_8G) is None


# ---- through the gateway ------------------------------------------------------------------------

def ingest(client, **hb):
    raw = heartbeat(**hb)
    node_id = json.loads(raw)["node_id"]
    assert client.app.state.registry.ingest(f"onemind.node.{node_id}.status", raw)


@pytest.fixture
def gpu_client(settings, clock, executor):
    add_app(settings, clock, "llm", requires={"gpu": True, "minMemoryMb": 64, "accelerator": ACC})
    add_app(settings, clock, "notes")
    with make_client(settings, clock, executor) as c:
        yield c


def test_install_refused_on_a_box_with_no_gpu(gpu_client, clock):
    ingest(gpu_client, gpu={"nvidia": False, "model": None})
    r = request(gpu_client, clock, "app.install", {"app_id": "llm"})
    assert r.status_code == 409, r.text
    assert r.json()["reason"] == "gpu_missing"
    assert "has none" in r.json()["message"]
    install(gpu_client, clock, "notes")   # an app that needs no GPU still installs


def test_install_allowed_on_a_box_with_a_big_enough_gpu(gpu_client, clock):
    ingest(gpu_client, gpu={"nvidia": True, "model": "RTX 3060", "memory_mb": 12288})
    install(gpu_client, clock, "llm")


def test_install_refused_when_the_gpu_is_too_small(gpu_client, clock):
    ingest(gpu_client, gpu={"nvidia": True, "model": "GTX 1050", "memory_mb": 4096})
    r = request(gpu_client, clock, "app.install", {"app_id": "llm"})
    assert r.status_code == 409 and r.json()["reason"] == "gpu_memory_too_small", r.text
