# SPDX-License-Identifier: Apache-2.0
"""FD-18: an account's default is an actual accessible app for that purpose."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from jsonschema import Draft202012Validator

from conftest import ADULT, AGENT, OWNER

HOME = "/v1/me/home"


def save(client, who, doc, etag):
    return client.put(HOME, headers={**who, "If-Match": etag}, json=doc)


def test_personal_defaults_survive_old_clients_and_conflicts(client, clock):
    client.app.state.repo.set_app_state("whoami", "installed", clock())
    first = client.get(HOME, headers=ADULT)
    assert first.json()["default_apps"] == {}
    defaults = {"developer": "whoami"}
    chosen = save(client, ADULT, {**first.json(), "default_apps": defaults}, first.headers["etag"])
    assert chosen.status_code == 200, chosen.text
    assert client.get(HOME, headers=ADULT).json()["default_apps"] == defaults
    assert client.get(HOME, headers=OWNER).json()["default_apps"] == {}
    assert save(client, ADULT, first.json(), first.headers["etag"]).status_code == 412
    legacy = chosen.json()
    del legacy["default_apps"]
    legacy["layout"] = "classic"
    old_client = save(client, ADULT, legacy, chosen.headers["etag"])
    assert old_client.json()["default_apps"] == defaults
    cleared = save(client, ADULT, {**old_client.json(), "default_apps": {}}, old_client.headers["etag"])
    assert cleared.json()["default_apps"] == {}
    assert save(client, AGENT, {}, "*").status_code == 403


def test_invalid_or_inaccessible_defaults_cannot_be_set_or_seen(client, clock):
    repo = client.app.state.repo
    repo.set_app_state("whoami", "installed", clock())
    first = client.get(HOME, headers=ADULT)
    for mapping in ({"browser": "whoami"}, {"ai": "hermes-like"}, {"media": "missing"}):
        r = save(client, ADULT, {**first.json(), "default_apps": mapping}, first.headers["etag"])
        assert r.status_code == 422, r.text
    chosen = {"developer": "whoami"}
    assert save(client, ADULT, {**first.json(), "default_apps": chosen}, first.headers["etag"]).status_code == 200
    repo.set_app_state("whoami", "removed", clock())
    assert client.get(HOME, headers=ADULT).json()["default_apps"] == {}
    repo.set_app_state("whoami", "installed", clock())
    gateway = client.app.state.gateway
    gateway.app_filters.append(lambda _req, p, app: p.id != "adult" or app != "whoami")
    hidden = client.get(HOME, headers=ADULT)
    assert hidden.json()["default_apps"] == {}
    assert save(client, ADULT, {**hidden.json(), "default_apps": chosen}, hidden.headers["etag"]).status_code == 422


def test_simultaneous_choices_require_one_device_to_refresh(client, clock, monkeypatch):
    for app in ("whoami", "uptime-kuma"):
        client.app.state.repo.set_app_state(app, "installed", clock())
    first = client.get(HOME, headers=ADULT)
    barrier = Barrier(2)
    svc = client.app.state.home
    original = svc.save

    def together(*args):
        barrier.wait(timeout=10)
        return original(*args)

    monkeypatch.setattr(svc, "save", together)

    def choose(pair):
        return save(client, ADULT, {**first.json(), "default_apps": dict([pair])}, first.headers["etag"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(choose, [("developer", "whoami"), ("monitoring", "uptime-kuma")]))
    assert sorted(r.status_code for r in replies) == [200, 412]
    saved = next(r.json()["default_apps"] for r in replies if r.status_code == 200)
    assert client.get(HOME, headers=ADULT).json()["default_apps"] == saved


def test_default_app_schema_rejects_invalid_purpose_and_app_ids(client):
    schema = client.app.openapi()["components"]["schemas"]["HomeBody"]["properties"]["default_apps"]
    validator = Draft202012Validator(schema)
    assert validator.is_valid({"browser": "firefox"})
    assert not validator.is_valid({"": "firefox"})
    assert not validator.is_valid({"browser": "not/an/app"})
