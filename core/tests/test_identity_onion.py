# SPDX-License-Identifier: Apache-2.0
"""The sign-in accepts this box's own .onion address as a WebAuthn origin (NET-TOR-01, #284)."""

from __future__ import annotations

from types import SimpleNamespace

from onemind_core.identity.service import IdentityService
from onemind_core.identity.settings import IdentitySettings

ONION = "a" * 55 + "b" + ".onion"


def rp(host: str, **cfg):
    svc = SimpleNamespace(cfg=IdentitySettings(**cfg))
    request = SimpleNamespace(headers={"host": host}, url=SimpleNamespace(hostname=host.split(":")[0]))
    return IdentityService.rp(svc, request)


def test_onion_host_is_the_relying_party_over_http():
    rp_id, origins = rp(ONION)
    assert rp_id == ONION
    assert f"http://{ONION}" in origins and f"https://{ONION}" in origins


def test_onion_host_with_port():
    assert f"http://{ONION}:8080" in rp(f"{ONION}:8080")[1]


def test_plain_http_stays_refused_for_other_names():
    for host in ("box.example.com", "onemind.local"):
        assert not [o for o in rp(host)[1] if o.startswith("http://")], host


def test_only_well_formed_v3_onion_addresses():
    for host in ("short.onion", "a" * 16 + ".onion", ("a" * 56 + ".onion.evil.com"), "A" * 56 + ".onion",
                 "1" * 56 + ".onion"):
        assert not [o for o in rp(host)[1] if o.startswith("http://")], host


def test_configured_origins_still_win():
    assert rp(ONION, origins=("https://box.example.com",))[1] == ["https://box.example.com"]
