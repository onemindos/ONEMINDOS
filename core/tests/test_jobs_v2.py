# SPDX-License-Identifier: Apache-2.0
"""The onemind.job/v2 envelope the gateway signs for one machine (D-029, N2 groundwork).

The machine's refusals (another machine, an unknown kid, an old epoch, a replay) are proven in Go
(internal/backup/job_v2_test.go), where the verifier runs. Here: the gateway signs exactly the bytes
the Go side checks (the shared vector), names the machine, and never signs a malformed envelope.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from onemind_core.backups.jobs import (JOB_SCHEMA_V2, POLICY_EPOCH, canonical, job_kid, lazy_job_key,
                                       load_or_create_job_key, public_pem, sign_job, sign_job_v2)

VECTOR = Path(__file__).resolve().parents[2] / "internal" / "backup" / "testdata" / "job-v2-vector.json"
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def test_matches_the_go_vector_byte_for_byte():
    vec = json.loads(VECTOR.read_text())
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(vec["seed_hex"]))
    assert public_pem(key).decode() == vec["public_pem"]
    assert job_kid(key.public_key()) == vec["kid"]
    env = vec["envelope"]
    again = sign_job_v2(key, env["kind"], env["params"], NOW, node_id="nodea", policy_epoch=env["policy_epoch"],
                        action_id=env["action_id"], ttl=timedelta(hours=1), job_id=env["job_id"])
    assert again == env  # Ed25519 is deterministic: the same seed and fields give the same sig


def test_v2_names_the_machine_the_key_and_the_epoch():
    key = Ed25519PrivateKey.generate()
    env = sign_job_v2(key, "update.apply", {"version": "1.2.3"}, NOW, node_id="n1", action_id="a1")
    assert env["schema"] == JOB_SCHEMA_V2 and env["aud"] == "node:n1"
    assert env["kid"] == job_kid(key.public_key()) and env["kid"].startswith("job-") and len(env["kid"]) == 20
    assert env["policy_epoch"] == POLICY_EPOCH
    sig = base64.b64decode(env.pop("sig"))
    key.public_key().verify(sig, canonical(env))
    # aud, kid and policy_epoch are inside the signature: rewriting one breaks it.
    for field, value in (("aud", "node:n2"), ("kid", "job-0000000000000000"), ("policy_epoch", POLICY_EPOCH + 1)):
        with pytest.raises(InvalidSignature):
            key.public_key().verify(sig, canonical({**env, field: value}))


def test_v1_stays_for_the_loopback_agent_only():
    env = sign_job(Ed25519PrivateKey.generate(), "backup.run", {}, NOW)
    assert env["schema"] == "onemind.job/v1" and not {"aud", "kid", "policy_epoch"} & env.keys()


@pytest.mark.parametrize("node_id", ["", "node:n1", "a.b", "x" * 65, None])
def test_refuses_a_bad_node_id(node_id):
    with pytest.raises(ValueError):
        sign_job_v2(Ed25519PrivateKey.generate(), "update.apply", {}, NOW, node_id=node_id)


@pytest.mark.parametrize("epoch", [-1, True, 1.0, "1"])
def test_refuses_a_bad_epoch(epoch):
    with pytest.raises(ValueError):
        sign_job_v2(Ed25519PrivateKey.generate(), "update.apply", {}, NOW, node_id="n1", policy_epoch=epoch)


def test_lazy_key_reads_once_and_retries_a_failure(tmp_path):
    path = tmp_path / "custodian" / "job.key"
    path.parent.mkdir()
    path.write_text("not a key")
    get = lazy_job_key(path)
    with pytest.raises(ValueError):
        get()
    path.unlink()
    first = get()
    assert get() is first and job_kid(first.public_key()) == job_kid(load_or_create_job_key(path).public_key())
