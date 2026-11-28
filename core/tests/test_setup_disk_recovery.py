# SPDX-License-Identifier: Apache-2.0
"""Keep encrypted first-owner setup bound to the disk component of the kit."""

import os

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from test_identity import LOCAL_PEER, csrf, id_settings
from test_identity_signin import LOGIN, screen_signup


def test_encrypted_setup_recovers_the_disk_kit_after_ram_handoff_is_lost(settings, clock, executor, tmp_path):
    disk_state = tmp_path / "crypt-state"
    disk_state.write_text('{"state": "encrypted", "unlock": "tpm2"}')
    disk_key = tmp_path / "disk-key"
    disk_key.write_text("the original disk key")

    cfg = id_settings(settings, recovery_key_file=disk_key, recovery_disk_state_file=disk_state)
    with TestClient(create_app(cfg, clock=clock, executor=executor), client=LOCAL_PEER) as client:
        screen_signup(client)
        kit = client.post("/v1/auth/setup/kit", headers=csrf(client)).json()
        assert kit["disk_recovery_key"] == "the original disk key"
        saved = {"saved": True, "method": "download", "recovery_code": kit["recovery_code"]}

    # The data disk unlocked normally after a reboot, but the tmpfs handoff disappeared.
    disk_key.unlink()
    with TestClient(create_app(cfg, clock=clock, executor=executor), client=LOCAL_PEER) as client:
        assert client.post("/v1/auth/login", json=LOGIN).status_code == 200
        for endpoint, body in (("finish", saved), ("kit", None)):
            refused = client.post(f"/v1/auth/setup/{endpoint}", headers=csrf(client), json=body)
            assert refused.status_code == 503
            assert refused.json()["reason"] == "disk_recovery_key_missing"
            assert "data-encrypt recover-kit" in refused.json()["message"]
        assert client.get("/v1/me").json()["setup_pending"] is True

        # Physical re-enrolment supplies a different key. The old kit cannot confirm that key.
        disk_key.write_text("the recovered disk key")
        assert client.post("/v1/auth/setup/finish", headers=csrf(client),
                           json={**saved, "disk_recovery_key": kit["disk_recovery_key"]}).status_code == 422
        recovered = client.post("/v1/auth/setup/kit", headers=csrf(client)).json()
        assert recovered["disk_recovery_key"] == "the recovered disk key"
        saved["recovery_code"] = recovered["recovery_code"]
        assert client.post("/v1/auth/setup/finish", headers=csrf(client), json=saved).status_code == 204
        assert disk_key.read_text() == ""
        assert client.get("/v1/me").json()["setup_pending"] is False


def test_saved_disk_kit_can_confirm_setup_after_reboot(settings, clock, executor, tmp_path):
    disk_state = tmp_path / "crypt-state"
    disk_state.write_text('{"state": "encrypted"}')
    disk_key = tmp_path / "disk-key"
    disk_key.write_text("disk key printed in the saved kit")
    cfg = id_settings(settings, recovery_key_file=disk_key, recovery_disk_state_file=disk_state)
    with TestClient(create_app(cfg, clock=clock, executor=executor), client=LOCAL_PEER) as client:
        screen_signup(client)
        kit = client.post("/v1/auth/setup/kit", headers=csrf(client)).json()
    disk_key.unlink()

    with TestClient(create_app(cfg, clock=clock, executor=executor), client=LOCAL_PEER) as client:
        assert client.post("/v1/auth/login", json=LOGIN).status_code == 200
        saved = {**kit, "saved": True, "method": "print"}
        bad_key = "a different disk key"
        wrong = client.post("/v1/auth/setup/finish", headers=csrf(client), json={**saved, "disk_recovery_key": bad_key})
        assert wrong.status_code == 422
        assert wrong.json()["reason"] == "recovery_kit_required"
        assert bad_key not in wrong.text
        assert client.get("/v1/me").json()["setup_pending"] is True

        disk_state.unlink()
        unknown = client.post("/v1/auth/setup/finish", headers=csrf(client), json=saved)
        assert unknown.status_code == 503
        assert unknown.json()["reason"] == "disk_recovery_key_unavailable"
        disk_state.write_text('{"state": "encrypted"}')
        assert client.post("/v1/auth/setup/finish", headers=csrf(client), json=saved).status_code == 204
        assert client.get("/v1/me").json()["setup_pending"] is False
        assert kit["disk_recovery_key"] not in settings.audit_path.read_text()


def test_gateway_uses_the_named_disk_key_descriptor_and_clears_it_after_confirmation(
    settings, clock, executor, tmp_path, monkeypatch,
):
    disk_state = tmp_path / "crypt-state"
    disk_state.write_text('{"state": "encrypted"}')
    key = tmp_path / "systemd-opened-file"
    key.write_bytes(b"disk key from systemd\n")
    key.chmod(0o600)
    with key.open("r+b") as systemd_file:
        fd = systemd_file.fileno()
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
        monkeypatch.setenv("LISTEN_FDS", str(fd - 2))
        monkeypatch.setenv("LISTEN_FDNAMES", ":".join(["unused"] * (fd - 3) + ["data-recovery-key"]))
        actual_fstat = os.fstat

        def root_owned(candidate):
            info = actual_fstat(candidate)
            if candidate == fd:
                return os.stat_result((*info[:4], 0, *info[5:]))
            return info

        monkeypatch.setattr(os, "fstat", root_owned)
        link = tmp_path / "symbolic-link"
        link.symlink_to(key)
        with pytest.raises(RuntimeError, match="root-only disk recovery key"):
            invalid = id_settings(settings, recovery_key_file=link, recovery_disk_state_file=disk_state)
            create_app(invalid, clock=clock, executor=executor)

        os.set_inheritable(fd, True)
        cfg = id_settings(settings, recovery_key_file=key, recovery_disk_state_file=disk_state)
        app = create_app(cfg, clock=clock, executor=executor)
        assert not os.get_inheritable(fd)
        with TestClient(app, client=LOCAL_PEER) as client:
            screen_signup(client)
            kit = client.post("/v1/auth/setup/kit", headers=csrf(client)).json()
            assert kit["disk_recovery_key"] == "disk key from systemd"
            saved = {"saved": True, "method": "print", "recovery_code": kit["recovery_code"]}
            assert client.post("/v1/auth/setup/finish", headers=csrf(client), json=saved).status_code == 204
        assert key.read_bytes() == b""
        assert key.stat().st_mode & 0o777 == 0o600
