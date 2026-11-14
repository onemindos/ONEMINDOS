# SPDX-License-Identifier: Apache-2.0
"""onemind-secrets: the terminal stand-in for the install form, against the real routes."""

import io
import json
import os

from conftest import OWNER, action_body
from onemind_core.appsecrets.cli import main

TOKEN = OWNER["Authorization"].split(" ", 1)[1]
APP, CRED = "vault-like", "vault-like-credentials"


def adapter(client):
    def http(method, url, token, body):
        path = url.split("://", 1)[1].split("/", 1)[1]
        r = client.request(method, "/" + path, json=body, headers={"Authorization": f"Bearer {token}"})
        return r.status_code, r.json()

    return http


class Tty(io.StringIO):
    def isatty(self):
        return True


def run(client, argv, stdin=None, ask=None):
    out = io.StringIO()
    rc = main(argv, http=adapter(client), stdin=stdin or io.StringIO(), stdout=out,
              ask=ask or (lambda prompt: ""), env={"ONEMIND_TOKEN": TOKEN})
    return rc, out.getvalue()


def test_approve_with_hidden_prompt_then_rotate_from_a_pipe(client, clock, executor, settings):
    value = "sk-test-" + os.urandom(8).hex()
    aid = client.post("/v1/actions", json=action_body(clock, app_id=APP), headers=OWNER).json()["id"]
    prompts = []
    rc, out = run(client, ["approve", aid, f"{CRED}/PROVIDER_API_KEY"], stdin=Tty(),
                  ask=lambda prompt: prompts.append(prompt) or value)
    assert rc == 0 and json.loads(out)["state"] == "succeeded"
    assert prompts == [f"{CRED}/PROVIDER_API_KEY (input hidden): "]
    assert executor.secrets[-1][0].data == {"PROVIDER_API_KEY": value}
    assert value not in out and value not in settings.audit_path.read_text()

    new = "sk-test-" + os.urandom(8).hex()
    rc, out = run(client, ["change", APP, "--set", f"{CRED}/PROVIDER_API_KEY", "--reason", "rotate"],
                  stdin=io.StringIO(new + "\n"))
    assert rc == 0 and out.startswith("filed ")
    action_id = out.split()[1].rstrip(";")
    rc, out = run(client, ["approve", action_id])
    assert rc == 0 and json.loads(out)["state"] == "succeeded"
    assert executor.secrets[-1][0].data == {"PROVIDER_API_KEY": new}

    rc, out = run(client, ["show", APP])
    assert rc == 0 and new not in out and json.loads(out)["missing_required"] == []


def test_errors_are_reported_without_values(client, clock, capsys):
    aid = client.post("/v1/actions", json=action_body(clock, app_id=APP), headers=OWNER).json()["id"]
    rc, _ = run(client, ["approve", aid])
    assert rc == 1 and "PROVIDER_API_KEY" in capsys.readouterr().err
    rc, _ = run(client, ["approve", aid, "no-slash"])
    assert rc == 1 and "not <secret>/<key>" in capsys.readouterr().err
    assert main(["show", APP], http=adapter(client), env={}) == 1
    assert "ONEMIND_TOKEN" in capsys.readouterr().err
