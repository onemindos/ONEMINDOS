# SPDX-License-Identifier: Apache-2.0
"""CORE-SEC-4 (#161): the hub's own NATS clients (gateway, onemindd) sign in with their own nkeys.

internal/leaf/accounts_test.go loads hub-accounts-services.golden.conf into a real nats-server and
proves a client with no nkey, or an nkey the hub does not list, is refused.
"""
from __future__ import annotations

import asyncio
import base64
import os
import stat
from pathlib import Path

import pytest

from onemind_core import natsconf
from onemind_core.bus import NatsBus, SeedClient
from onemind_core.natsconf import (
    HUB_LOCAL_USER, NodeAccount, ServiceKey, load_seed, load_service_keys, make_service_key, new_user_key,
    render_accounts,
)
from onemind_core.nodes import NodeRegistry

GOLDEN = Path(__file__).resolve().parents[2] / "internal" / "leaf" / "testdata" / "hub-accounts-services.golden.conf"
PUB_A = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"
PUB_B = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3"
PUB_GW = "UAIETCIAFQAMTEIL47WBJYZ7OVLKMFPNIJ4P5T6XMGO7EHNVADUNJAAR"
PUB_OD = "UC4NBEYQFAATYOQQ7SNT66S4WUDHAPZJ76SYNNSFMH2RXR3A6YESSM3V"
NODES = [NodeAccount("bbb222", PUB_B), NodeAccount("aaa111", PUB_A)]
# Reference vector made with the nkeys library (nkeys.py 0.2.1, from_seed + sign), which is what
# nats-py itself signs with. A throwaway test key: nothing trusts it.
REF_SEED = "SUAFYZMM7JSOKPMRRXMGNWNLWIJIIS52NZTGPO3VXYLYLEKU5YGD7E3LJ4"
REF_PUB = "UCN22NCNRTF5KMIS5S3H5SCIWNUS2HZK4T2B6JJWLL6MTHD77QKC33B4"
REF_SIG = "8POp6YQDSsf1pawtVYIaA92zdVsPXkXArJQpsiudXiRWswOMk0Z1daTpD5k2oj5zubMUqLDl3AXyLLdZmfNiAg=="


def test_services_golden_matches_the_go_refusal_test():
    services = [ServiceKey("onemindd", PUB_OD), ServiceKey("gateway", PUB_GW)]
    assert render_accounts(NODES, services) == GOLDEN.read_text()


def test_strict_hub_has_no_passwordless_user():
    strict = render_accounts(NODES, [ServiceKey("gateway", PUB_GW)])
    assert "no_auth_user" not in strict and HUB_LOCAL_USER not in strict
    assert f'{{nkey: "{PUB_GW}", allowed_connection_types: ["STANDARD"]}}' in strict
    # Without service keys (dev compose, boxes installed before #161) the fallback stays.
    legacy = render_accounts(NODES)
    assert f'no_auth_user: "{HUB_LOCAL_USER}"' in legacy


def test_seed_loading_matches_the_nkeys_library(tmp_path):
    f = tmp_path / "ref.nk"
    f.write_text(REF_SEED + "\n")
    pub, sign = load_seed(f)
    assert pub == REF_PUB
    assert base64.b64encode(sign(b"hub-nonce-123")).decode() == REF_SIG  # Ed25519 is deterministic


def test_generated_key_round_trips(tmp_path):
    seed, pub = new_user_key()
    assert seed.startswith("SU") and natsconf.is_user_public_nkey(pub)
    f = tmp_path / "k.nk"
    f.write_text(seed)
    assert load_seed(f)[0] == pub
    assert new_user_key()[1] != pub
    for bad in ("", "SUNOTASEED", REF_PUB, REF_SEED[:-1] + ("A" if REF_SEED[-1] != "A" else "B")):
        f.write_text(bad)
        with pytest.raises(ValueError):
            load_seed(f)


def test_gateway_client_signs_the_nonce_like_nats_py_does(tmp_path):
    """SeedClient fills the fields nats-py puts in CONNECT (nkey, sig), without the nkeys package."""
    f = tmp_path / "gateway.nk"
    f.write_text(REF_SEED + "\n")
    c = SeedClient()
    c._nkeys_seed = str(f)
    c._setup_nkeys_seed_connect()
    assert c._public_nkey == REF_PUB
    assert c._signature_cb("hub-nonce-123").decode() == REF_SIG


def test_service_key_files(tmp_path):
    d = tmp_path / "keys"
    pub = make_service_key(d, "gateway")
    assert (d / "gateway.pub").read_text().strip() == pub
    assert stat.S_IMODE(os.stat(d / "gateway.nk").st_mode) == 0o600
    assert make_service_key(d, "gateway") == pub  # kept, not replaced
    make_service_key(d, "onemindd")
    assert [s.name for s in load_service_keys(d)] == ["gateway", "onemindd"]
    assert load_service_keys(tmp_path / "missing") == [] and load_service_keys(None) == []
    (d / "bad.pub").write_text("UNOTAKEY\n")
    with pytest.raises(ValueError):  # a broken key file must not silently lock a service out
        load_service_keys(d)
    with pytest.raises(ValueError):
        make_service_key(d, "../escape")


def test_installer_cli(tmp_path, capsys):
    keys, acc = tmp_path / "keys", tmp_path / "accounts.conf"
    assert natsconf.main(["service-key", str(keys), "gateway"]) == 0
    pub = capsys.readouterr().out.strip()
    assert natsconf.main([str(acc), str(keys)]) == 0
    text = acc.read_text()
    assert pub in text and "no_auth_user" not in text
    assert natsconf.main([str(acc)]) == 0 and acc.read_text() == text  # an existing file is left alone
    assert natsconf.main(["service-key", str(keys)]) == 2


def test_gateway_connects_with_its_seed(monkeypatch, tmp_path):
    seen = {}

    async def fake_connect(self, url, **kw):
        seen.update(kw, url=url)
        raise OSError("stop here")

    monkeypatch.setattr(SeedClient, "connect", fake_connect)
    seed = tmp_path / "gateway.nk"

    async def go(bus):
        await bus.start()
        await asyncio.sleep(0.05)
        await bus.stop()

    asyncio.run(go(NatsBus("nats://127.0.0.1:4222", NodeRegistry(lambda: None), nkey_seed=seed)))
    assert seen["nkeys_seed"] == str(seed)
    seen.clear()
    asyncio.run(go(NatsBus("nats://127.0.0.1:4222", NodeRegistry(lambda: None))))
    assert "nkeys_seed" not in seen


def test_public_key_encoding_round_trips():
    _, pub = new_user_key()
    raw = base64.b32decode(pub + "=" * (-len(pub) % 8))
    assert raw[0] == 20 << 3 and len(raw) == 35
