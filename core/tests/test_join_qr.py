# SPDX-License-Identifier: Apache-2.0
"""The join QR (docs/architecture/FABRIC.md §4.2): one builder (fabric.build_join_qr) and three parsers
(fabric.parse_join_qr, internal/fabric/join.go ParseQR, sdk/ts parseJoinQR) that all run the shared
vectors in sdk/testdata/join-qr/vectors.json, so no payload parses differently across languages."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from onemind_core.fabric import JOIN_KINDS, JoinQRError, build_join_qr, parse_join_qr

VECTORS = json.loads((Path(__file__).resolve().parents[2] / "sdk" / "testdata" / "join-qr" / "vectors.json").read_text())
CA = "0123456789abcdef" * 4


@pytest.mark.parametrize("case", VECTORS["valid"], ids=lambda c: c["name"])
def test_valid_vectors(case):
    assert parse_join_qr(case["payload"]).as_dict() == case["expect"]
    if "build" in case:
        assert build_join_qr(**case["build"]) == case["payload"]


@pytest.mark.parametrize("case", VECTORS["hostile"], ids=lambda c: c["name"])
def test_hostile_vectors(case):
    with pytest.raises(JoinQRError) as exc:
        parse_join_qr(case["payload"])
    assert exc.value.reason == case["reason"] and case["reason"] in VECTORS["reasons"]


def test_vectors_cover_every_kind_and_reason():
    assert {c["expect"]["kind"] for c in VECTORS["valid"] if c["expect"]["version"] == 2} == set(JOIN_KINDS)
    assert {c["reason"] for c in VECTORS["hostile"]} == set(VECTORS["reasons"])


def test_builder_refuses_what_no_parser_would_read():
    good = {"hub": "https://box1.local", "ca": CA, "code": "7KQ4-M2XP-9D3F", "kind": "worker"}
    for field, value, reason in [("hub", "http://box1.local", "hub"), ("hub", "https://box1.local/x", "hub"),
                                 ("ca", "token", "ca"), ("code", "7kq4-m2xp-9d3f", "code"),
                                 ("kind", "hub", "kind"), ("mdns", "box1.lan", "mdns"), ("alt", "https://u@x", "alt")]:
        with pytest.raises(JoinQRError) as exc:
            build_join_qr(**{**good, field: value})
        assert exc.value.reason == reason, field
    with pytest.raises(JoinQRError):
        build_join_qr(**good, mdns="box1.local", version=1)  # v1 has no mdns
    with pytest.raises(JoinQRError):
        build_join_qr(**good, version=3)
    # a value with '&' or '=' cannot smuggle a second field: it is escaped, then refused by shape
    with pytest.raises(JoinQRError) as exc:
        build_join_qr(**{**good, "code": "7KQ4-M2XP-9D3F&kind=leaf"})
    assert exc.value.reason == "code"
