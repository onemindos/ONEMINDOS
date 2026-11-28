# SPDX-License-Identifier: Apache-2.0
"""Exercise the installed gateway as its Unix user, using isolated owner and ledger state."""

import os
import secrets
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from onemind_core.actions import HOLD_MIN_MS
from onemind_core.app import create_app
from onemind_core.config import Settings


def approved_release(authenticator, job, title, no_output):
    with TemporaryDirectory() as tmp:
        token = secrets.token_hex(32)
        token_file = Path(tmp, "setup-token")
        token_file.write_text(token + "\n")
        settings = Settings.from_env({
            "ONEMIND_DATA_DIR": tmp, "ONEMIND_NATS_URL": "",
            "ONEMIND_IDENTITY_SETUP_TOKEN_FILE": str(token_file),
            "ONEMIND_IDENTITY_RP_ID": "localhost", "ONEMIND_IDENTITY_COOKIE_SECURE": "0",
        })
        with TestClient(create_app(settings), base_url="http://localhost") as gateway:
            def post(path, body, expected, headers=None):
                reply = gateway.post(path, json=body, headers=headers)
                assert reply.status_code == expected, f"{path}: {reply.status_code} (expected {expected})"
                return reply.json()

            post("/v1/auth/setup", {"username": "print-owner", "password": secrets.token_urlsafe(24)}, 201,
                 {"Authorization": "Bearer " + token})
            gateway.headers["OneMind-CSRF"] = gateway.cookies["onemind_csrf"]
            body = {"type": "print.job.release", "params": {"job": job, "title": title},
                    "idempotency_key": secrets.token_hex(16),
                    "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}
            action = post("/v1/actions", body, 201)
            assert action["state"] == "awaiting_approval" and action["approval"]["physical"] is True
            no_output()
            path = f"/v1/actions/{action['id']}/approve"
            proof = {"plan_sha256": action["plan_sha256"], "hold_ms": HOLD_MIN_MS}
            assert post(path, proof, 401)["reason"] == "step_up_required"
            no_output()
            assert post("/v1/actions", {**body, "idempotency_key": secrets.token_hex(16),
                                       "params": {**body["params"], "title": title[:-1] + "!"}}, 409)["reason"] == "print_job_unavailable"
            key = authenticator()
            options = post("/v1/auth/passkeys/register/options", {}, 200)
            post("/v1/auth/passkeys/register", {"label": "test key", "credential": key.register(options)}, 201)
            challenge = post(path + "-options", {}, 200)
            assert challenge["plan_sha256"] == proof["plan_sha256"]
            assertion = key.assert_(challenge["publicKey"]["challenge"])
            result = post(path, {**proof, "webauthn": assertion}, 200)
            assert result["state"] == "succeeded", result.get("result")


if __name__ == "__main__":
    auth, job, title, output = sys.argv[1:]

    def no_file_output():
        time.sleep(0.2)
        assert not os.path.exists(output), "a job reached the printer before owner approval"

    approved_release(run_path(auth)["SoftAuthenticator"], job, title, no_file_output)
    print("QUEUED_OWNER_RELEASE=ok")
