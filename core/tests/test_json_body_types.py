# SPDX-License-Identifier: Apache-2.0
"""Request bodies take booleans and numbers only as JSON booleans and numbers (api-fuzz ST201).

api-fuzz found PUT /v1/agents/kill-switch {"on": 0} and PUT /v1/family/apps/{app_id} {"min_age": false}
answered 200 (run 44982704938): pydantic's lax mode converted the value. The strict=True fix then refused
{"min_age": 3.0}, which JSON Schema's integer allows (run 44984786513). onemind_core.jsonbody.JsonBody fixes
the whole class: this file checks every request model the gateway mounts uses it, that every such field at
every route refuses the wrong JSON type with 422, and that 3.0 still counts as an integer.
"""

from __future__ import annotations

import inspect
import re
import types
import typing

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from conftest import OWNER
from onemind_core.app import create_app
from onemind_core.config import Settings
from onemind_core.family import AppClassification, FamilyProfile
from onemind_core.jsonbody import JsonBody, scalar_check
from onemind_core.machines.spec import MachineCreateParams
from onemind_core.smbshares import CreateParams as ShareCreateParams

# Wrong JSON for each declared type: what lax mode used to convert.
WRONG = {"bool": [0, 1, 0.0, "true", "false"], "int": [False, True, "5"], "float": [False, True, "1.5"]}
RIGHT = {"bool": [True, False], "int": [3, 3.0], "float": [1, 1.5]}
# Request models validated by POST /v1/actions (FeatureAction.params_model), not by a route signature.
FEATURE_PARAMS = [MachineCreateParams, ShareCreateParams]
# Every route whose body (or a model inside it) this fix moved to JsonBody.
CHANGED_ROUTES = {
    ("POST", "/v1/alerts/{alert_id}/fix"), ("POST", "/v1/approval-policies"), ("POST", "/v1/automation/rules"),
    ("PATCH", "/v1/automation/rules/{rule_id}"), ("POST", "/v1/backups/destinations"), ("POST", "/v1/backups/runs"),
    ("POST", "/v1/backups/verify"), ("POST", "/v1/fabric/join-tickets"), ("PUT", "/v1/me/home"),
    ("POST", "/v1/migrate/plans/{plan_id}/cutover"), ("POST", "/v1/onboarding/restore/apps"),
    ("POST", "/v1/photos/sources/{source_id}/check"), ("POST", "/v1/restores"), ("POST", "/v1/storage/actions"),
    ("POST", "/v1/storage/plans"), ("POST", "/v1/tokens"), ("POST", "/v1/tokens/{token_id}/rotate"),
    ("PUT", "/v1/agents/kill-switch"), ("PUT", "/v1/family/apps/{app_id}"), ("PUT", "/v1/family/profiles/{user_id}"),
    ("PUT", "/v1/update-policy"),
}


def _kind(annotation) -> str | None:
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin is typing.Annotated:
        return _kind(args[0])
    if origin in (typing.Union, types.UnionType):
        members = [a for a in args if a is not type(None)]
        return _kind(members[0]) if len(members) == 1 else None
    return {bool: "bool", int: "int", float: "float"}.get(annotation)


def _models(annotation):
    """Every pydantic model an annotation mentions (the model itself, list items, union members)."""
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        yield annotation
        for f in annotation.model_fields.values():
            yield from _models(f.annotation)
    for a in typing.get_args(annotation):
        yield from _models(a)


def _app(tmp_path):
    (tmp_path / "apps").mkdir(exist_ok=True)
    return create_app(Settings(
        tokens_file=None, db_url=f"sqlite:///{tmp_path / 'e.db'}", apps_dir=tmp_path / "apps", dashboard_dist=None,
        executor="noop", nats_url=None, audit_path=tmp_path / "audit.jsonl", node_id="t", instance_name="t",
        app_schema_path=None, kubectl="kubectl", executor_timeout_s=1, host="127.0.0.1", port=8080,
    ))


def _body_models(app) -> dict[tuple[str, str], BaseModel]:
    """(method, path) -> the top-level body model of every mounted JSON route."""
    out = {}
    for r in app.routes:
        if isinstance(r, APIRoute):
            for b in r.dependant.body_params:
                a = b.field_info.annotation
                for m in [x for x in typing.get_args(a) or (a,) if inspect.isclass(x) and issubclass(x, BaseModel)]:
                    for method in r.methods:
                        out[(method, r.path)] = m
    return out


def _lax_scalar_fields(model) -> list[str]:
    # A field pydantic validates strictly already (files.py's StrictBool) is not lax.
    return [n for n, f in model.model_fields.items()
            if _kind(f.annotation) and not any(getattr(m, "strict", False) for m in f.metadata)
            and "StrictBool" not in str(f.annotation) and "_not_a_bool" not in str(f.annotation)]


def test_every_mounted_request_model_with_a_boolean_or_number_is_a_json_body(tmp_path):
    """The sweep, kept: a new route whose body takes bool/int/float must derive from JsonBody."""
    app = _app(tmp_path)
    models = {m for top in _body_models(app).values() for m in _models(top)} | set(FEATURE_PARAMS)
    lax = sorted(f"{m.__module__}.{m.__name__}.{n}" for m in models if not issubclass(m, JsonBody)
                 for n in _lax_scalar_fields(m))
    assert lax == [], "request fields that lax mode would coerce; derive the model from JsonBody: " + ", ".join(lax)


def _list_item(annotation):
    """The item type of `list[X]` / `list[X] | None`, else None."""
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin is typing.Annotated:
        return _list_item(args[0])
    if origin in (typing.Union, types.UnionType):
        members = [a for a in args if a is not type(None)]
        return _list_item(members[0]) if len(members) == 1 else None
    return args[0] if origin is list and args else None


def _submodel(annotation):
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin is typing.Annotated:
        return _submodel(args[0])
    if origin in (typing.Union, types.UnionType):
        members = [a for a in args if a is not type(None)]
        return _submodel(members[0]) if len(members) == 1 else None
    return annotation if inspect.isclass(annotation) and issubclass(annotation, BaseModel) else None


def _wrong_bodies(model, depth=0):
    """(JSON fragment, field name, wrong value) for every bool/int/float field of a JsonBody, nested ones too."""
    for name, f in model.model_fields.items():
        key = f.alias or name
        if issubclass(model, JsonBody) and (kind := _kind(f.annotation)):
            for wrong in WRONG[kind]:
                yield {key: wrong}, name, wrong
        elif issubclass(model, JsonBody) and (item := _list_item(f.annotation)) is not None and _kind(item):
            for wrong in WRONG[_kind(item)]:
                yield {key: [wrong]}, name, wrong
        elif depth < 3:
            for sub, wrap in ((_submodel(f.annotation), dict), (_submodel(_list_item(f.annotation)), list)):
                if sub is not None:
                    for frag, n, w in _wrong_bodies(sub, depth + 1):
                        yield {key: frag if wrap is dict else [frag]}, n, w


def _route_cases():
    import tempfile
    from pathlib import Path
    app = _app(Path(tempfile.mkdtemp()))
    cases = []
    for (method, path), model in sorted(_body_models(app).items(), key=lambda kv: kv[0]):
        for body, name, wrong in _wrong_bodies(model):
            cases.append(pytest.param(method, path, body, name, id=f"{method} {path} {name}={wrong!r}"))
    app.state.repo.close()
    return cases


ROUTE_CASES = _route_cases()


def test_the_sweep_covers_the_routes_api_fuzz_found():
    ids = {p.id for p in ROUTE_CASES}
    assert "PUT /v1/agents/kill-switch on=0" in ids
    assert "PUT /v1/family/apps/{app_id} min_age=False" in ids
    routes = {(p.values[0], p.values[1]) for p in ROUTE_CASES}
    assert routes >= CHANGED_ROUTES, sorted(CHANGED_ROUTES - routes)


@pytest.mark.parametrize("method,path,body,field", ROUTE_CASES)
def test_wrong_json_type_is_refused_at_the_route(client, method, path, body, field):
    url = re.sub(r"\{[^}]+\}", "fuzz-x", path)
    r = client.request(method, url, json=body, headers=OWNER)
    assert r.status_code == 422, (r.status_code, r.text)
    body = r.json()
    assert body["error"] == "conflict" and body.get("reason") is None  # a schema violation, not a semantic refusal
    assert f"{field} should be a JSON " in body["message"], body["message"]


@pytest.mark.parametrize("model", sorted(
    {m for m in [*FEATURE_PARAMS, FamilyProfile, AppClassification]} , key=lambda m: m.__name__))
def test_feature_and_nested_models_refuse_wrong_json_types(model):
    for name, field in model.model_fields.items():
        if (kind := _kind(field.annotation)) is None:
            continue
        check = scalar_check(field.annotation)
        for wrong in WRONG[kind]:
            assert check(wrong) is not None, (model.__name__, name, wrong)
        for right in RIGHT[kind]:
            assert check(right) is None, (model.__name__, name, right)


def test_family_window_days_items_and_minutes_are_checked_inside_the_list():
    from pydantic import ValidationError
    good = {"days": [1.0, 2], "start_minute": 60.0, "end_minute": 120}
    assert FamilyProfile.model_validate({"windows": [good]}).windows[0].days == [1, 2]
    for bad in ({**good, "days": [1, True]}, {**good, "start_minute": "60"}, {**good, "end_minute": False}):
        with pytest.raises(ValidationError, match="should be a JSON integer"):
            FamilyProfile.model_validate({"windows": [bad]})


def test_an_integral_float_is_a_json_integer_at_the_route(client):
    """api-fuzz run 44984786513: {"min_age": 3.0} is schema-valid and was refused by strict=True."""
    r = client.put("/v1/family/apps/uptime-kuma", json={"min_age": 3.0, "tags": []}, headers=OWNER)
    assert r.status_code == 200, r.text
    assert r.json()["min_age"] == 3
    assert client.put("/v1/family/apps/uptime-kuma", json={"min_age": 3.5}, headers=OWNER).status_code == 422
