# SPDX-License-Identifier: Apache-2.0
"""The cluster replacement plan (lab-kits/cluster-replacement/targets.yaml) stays honest.

Every workload class on the old cluster must have a target on the box and a proof file that exists,
Market targets must be real apps, anything dropped must say its data is archived first (or be
plumbing that holds no data), and the message-bus authority flip must come after every other move.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLAN = yaml.safe_load((ROOT / "lab-kits/cluster-replacement/targets.yaml").read_text())
KINDS = {"market-app", "os-native", "private-deploy", "drop"}
PHASES = [p["id"] for p in PLAN["phases"]]
# Data-bearing drops must be archived; these hold no owner data.
NO_DATA = {"ci-runners", "cluster-plumbing", "old-front-door"}


def test_every_workload_has_a_known_kind_phase_and_proof():
    ids = [w["id"] for w in PLAN["workloads"]]
    assert len(ids) == len(set(ids))
    for w in PLAN["workloads"]:
        assert w["kind"] in KINDS, w["id"]
        assert w["phase"] in PHASES, w["id"]
        assert (ROOT / w["verify"]).is_file(), f"{w['id']}: missing proof file {w['verify']}"


def test_market_targets_are_real_apps():
    for w in PLAN["workloads"]:
        if w["kind"] == "market-app":
            assert (ROOT / "apps" / w["app"] / "onemind.app.yaml").is_file(), w["id"]
            assert w["verify"] == f"apps/{w['app']}/onemind.app.yaml", w["id"]


def test_drops_with_data_are_archived_first():
    for w in PLAN["workloads"]:
        if w["kind"] == "drop" and w["id"] not in NO_DATA:
            assert w.get("archive") is True, f"{w['id']} drops data without an archive step"


def test_bus_authority_flip_is_last_move_before_decommission():
    flip = [p["id"] for p in PLAN["phases"] if p["bus_flip"]]
    assert flip == ["P4"] and PHASES[-2:] == ["P4", "P5"]
    bus = [w for w in PLAN["workloads"] if w["id"] == "message-bus"]
    assert [w["phase"] for w in bus] == ["P4"]
    for w in PLAN["workloads"]:
        if w["id"] != "message-bus" and w["phase"] != "P5":
            assert PHASES.index(w["phase"]) < PHASES.index("P4"), w["id"]


def test_runbook_mentions_every_phase_and_workload():
    text = (ROOT / "lab-kits/cluster-replacement/RUNBOOK.md").read_text()
    for p in PHASES:
        assert f"## {p}" in text, p
    for w in PLAN["workloads"]:
        assert f"`{w['id']}`" in text, w["id"]
