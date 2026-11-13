# SPDX-License-Identifier: Apache-2.0
"""A5's production boundary repairs, without networking, databases or cleanup fixtures."""
from __future__ import annotations

import ipaddress
import json
from types import SimpleNamespace
from typing import cast

import pytest

from onemind_core.auth import Principal
from onemind_core.context import Gateway
from onemind_core.mcp.untrusted import MAX_DEPTH, TOO_DEEP, mark
from onemind_core.notify.channels import DeliveryError, check_address
from onemind_core.routers.notifications import _denied


def ipv4(*octets):
    return ipaddress.IPv4Address(bytes(octets))


def embedded(address, encoding):
    value = int(address)
    if encoding == "mapped":
        return ipaddress.IPv6Address((0xffff << 32) | value)
    if encoding == "6to4":
        return ipaddress.IPv6Address((0x2002 << 112) | (value << 80))
    server = int(ipv4(8, 8, 8, 8))
    return ipaddress.IPv6Address((0x20010000 << 96) | (server << 64) | (value ^ 0xffffffff))


@pytest.mark.parametrize("encoding", ["mapped", "6to4", "teredo"])
@pytest.mark.parametrize("lan_ok", [False, True])
@pytest.mark.parametrize("address", [ipv4(0, 1, 2, 3), ipv4(169, 254, 169, 254)])
def test_embedded_reserved_destination_is_always_refused(address, encoding, lan_ok):
    with pytest.raises(DeliveryError, match="not allowed"):
        check_address(embedded(address, encoding), lan_ok)


@pytest.mark.parametrize("encoding", ["mapped", "6to4", "teredo"])
def test_embedded_lan_destination_needs_owner_opt_in(encoding):
    address = embedded(ipv4(10, 1, 2, 3), encoding)
    with pytest.raises(DeliveryError, match="only an owner"):
        check_address(address, False)
    check_address(address, True)


def test_deprecated_site_local_needs_owner_opt_in():
    address = ipaddress.IPv6Address((0xfec0 << 112) | 1)
    with pytest.raises(DeliveryError, match="only an owner"):
        check_address(address, False)
    check_address(address, True)


@pytest.mark.parametrize("encoding", ["mapped", "6to4", "teredo"])
def test_public_embedded_destination_is_not_blanket_refused(encoding):
    check_address(embedded(ipv4(8, 8, 8, 8), encoding), False)


def test_untrusted_copy_bounds_nesting_without_mutating_the_input():
    nested = "leaf"
    for _ in range(900):
        nested = [nested]
    source = {"nodes": [{"hostname": "safe\u202ename", "extra": nested}]}
    structured, text, paths = mark(source, ["nodes.*.hostname"])
    assert structured["nodes"][0]["hostname"] == "safename"
    assert source["nodes"][0]["hostname"] == "safe\u202ename"
    assert source["nodes"][0]["extra"] is nested
    assert paths == ["nodes[0].hostname"]
    current = structured["nodes"][0]["extra"]
    for _ in range(MAX_DEPTH):
        if not isinstance(current, list):
            break
        current = current[0]
    assert current == TOO_DEEP
    assert json.loads(text)
    assert "<untrusted " in text and "</untrusted>" in text


def test_handler_denial_records_the_same_principal_and_reason():
    records = []
    gateway = SimpleNamespace(audit=SimpleNamespace(append=lambda *args: records.append(args)))
    principal = Principal("test-agent", "agent", "agent")
    error = _denied(cast(Gateway, gateway), principal, "approve an alert's fix", "only an owner may approve")
    assert (error.status, error.error) == (403, "permission_denied")
    assert records == [("authz.denied", principal.as_dict(), None,
                        {"attempted": "approve an alert's fix", "reason": "permission_denied"})]
