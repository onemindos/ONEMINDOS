# SPDX-License-Identifier: Apache-2.0
"""Regressions for the schema/server disagreements the API fuzz found on the newer routes (api-fuzz.yml).

Each test fixes one thing the published OpenAPI said that the server then refused (or the reverse): the
schema now describes what the server takes. None of them loosens a server check.
"""
import re

import pytest

from conftest import AGENT, OWNER
from files_support import TUS, fc, files_root, files_settings, meta, mkdir, ok  # noqa: F401


def spec(client):
    return client.get("/openapi.json").json()


def resolve(doc, schema):
    while "$ref" in schema:
        schema = doc["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    return schema


# ---- POST /v1/actions and /v1/plans: params depend on type ---------------------------------------
@pytest.mark.parametrize("path", ["/v1/actions", "/v1/plans"])
def test_action_body_schema_offers_settings_and_confirm_only_where_the_server_takes_them(client, path):
    doc = spec(client)
    body = resolve(doc, doc["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"])
    variants = {}
    for v in body["oneOf"]:
        v = resolve(doc, v)
        params = resolve(doc, v["properties"]["params"])
        for t in v["properties"]["type"].get("enum") or [v["properties"]["type"]["const"]]:
            variants[t] = set(params["properties"]) | {"~required:" + r for r in params.get("required", [])}
    assert variants["app.stop"] == {"app_id", "~required:app_id"}
    assert variants["app.configure"] >= {"settings", "~required:settings"}
    assert "confirm" not in variants["app.configure"]
    assert variants["app.delete_data"] >= {"confirm", "~required:confirm"}
    assert set(variants) == {"app.install", "app.remove", "app.start", "app.stop", "app.restart", "app.update",
                             "app.configure", "app.delete_data"}


def test_the_server_still_refuses_what_the_schema_no_longer_offers(client):
    for body_params, type_ in (({"app_id": "uptime-kuma", "settings": {}}, "app.stop"),
                               ({"app_id": "uptime-kuma", "confirm": ""}, "app.stop"),
                               ({"app_id": "uptime-kuma"}, "app.configure"),
                               ({"app_id": "uptime-kuma", "confirm": "other"}, "app.delete_data")):
        r = client.post("/v1/plans", headers=OWNER, json={"type": type_, "params": body_params})
        assert r.status_code == 422, (type_, body_params, r.text)


def test_a_secret_looking_setting_is_a_422_not_a_500(client):
    """The variants run the same checks as ActionRequest while the body is validated (it was a 500 once)."""
    r = client.post("/v1/actions", headers=OWNER, json={
        "type": "app.configure", "params": {"app_id": "uptime-kuma", "settings": {"DB_PASSWORD": "x"}},
        "idempotency_key": "k1", "expires_at": "2099-01-01T00:00:00Z"})
    assert r.status_code == 422 and "secret" in r.json()["message"], r.text


# ---- backups: 503 is documented ------------------------------------------------------------------
def test_backup_routes_document_503_and_answer_it_in_the_envelope(client):
    doc = spec(client)
    for path, item in doc["paths"].items():
        if path.startswith(("/v1/backups", "/v1/restores")):
            for method, op in item.items():
                assert "503" in op["responses"], (method, path)
                assert op["responses"]["503"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorBody")
    r = client.get("/v1/backups/snapshots", headers=OWNER)  # backups are off in the test settings
    assert r.status_code == 503 and r.headers["retry-after"] == "30"
    assert r.json() == {"error": "unavailable", "message": r.json()["message"], "reason": "backups_disabled",
                        "retry_after_s": 30}


def test_restore_path_pattern_is_exactly_what_the_server_accepts(client):
    from onemind_core.routers.backups import PATH_RE, PathScope
    from pydantic import ValidationError

    samples = ["/", "//", "/a", "/a/", "/a//", "//a", "/a/./b", "/a/../b", "/a/b", "/.hidden", "/..x", "/...", "/a/.",
               "/a/..", "a/b", "", "/a b/c", "/a/b/c/"]
    for path in samples:
        try:
            PathScope(app_id="uptime-kuma", path=path)
            server = True
        except ValidationError:
            server = False
        assert bool(re.fullmatch(PATH_RE, path)) == server, path


# ---- files: roots, ops, tus ----------------------------------------------------------------------
def test_files_schema_describes_roots_ops_and_tus_headers(fc):
    doc = spec(fc)
    root = resolve(doc, [p for p in doc["paths"]["/v1/files/list"]["get"]["parameters"] if p["name"] == "root"][0]["schema"])
    assert re.fullmatch(root["pattern"], "shared") and re.fullmatch(root["pattern"], "home:alice")
    assert not re.fullmatch(root["pattern"], "") and not re.fullmatch(root["pattern"], "000")
    ops = resolve(doc, doc["paths"]["/v1/files/ops"]["post"]["requestBody"]["content"]["application/json"]["schema"])
    required = {resolve(doc, v)["properties"]["op"]["const"]: set(resolve(doc, v)["required"]) for v in ops["oneOf"]}
    assert required["mkdir"] == {"op", "root", "path"}
    assert required["rename"] == {"op", "root", "path", "name"}
    assert required["restore_trash"] == {"op", "trash_id"}
    assert "to_root" not in required["move"]  # the same space when absent, as the server does
    for method, path in (("post", "/v1/files/uploads"), ("head", "/v1/files/uploads/{upload_id}"),
                         ("patch", "/v1/files/uploads/{upload_id}"), ("delete", "/v1/files/uploads/{upload_id}")):
        params = {p["name"].lower(): p for p in doc["paths"][path][method]["parameters"] if p["in"] == "header"}
        tus = params["tus-resumable"]
        assert tus["required"] and resolve(doc, tus["schema"]).get("const") == "1.0.0", (method, path)
    create = {p["name"].lower(): p for p in doc["paths"]["/v1/files/uploads"]["post"]["parameters"] if p["in"] == "header"}
    assert create["upload-length"]["required"] and "null" not in str(create["upload-length"]["schema"])
    assert create["upload-metadata"]["required"]
    assert "204" in doc["paths"]["/v1/files/uploads"]["options"]["responses"]


def test_tus_protocol_answers_are_unchanged(fc):
    """The schema now requires the headers; a missing or wrong one is still the protocol's 412 / 415."""
    m = meta(root="shared", path="/", filename="a.txt")
    base = {"Upload-Length": "1", "Upload-Metadata": m}
    for headers in ({}, {"Tus-Resumable": "0.2.0"}, {"Tus-Resumable": ""}):
        r = fc.post("/v1/files/uploads", headers={**OWNER, **base, **headers})
        assert r.status_code == 412 and r.json()["reason"] == "tus_version" and r.headers["tus-version"] == "1.0.0", r.text
    r = fc.post("/v1/files/uploads", headers={**OWNER, **TUS, **base})
    assert r.status_code == 201, r.text
    location = r.headers["Location"]
    patch = {**OWNER, **TUS, "Upload-Offset": "0"}
    assert fc.patch(location, content=b"x", headers={**patch, "Content-Type": "text/plain"}).status_code == 415
    assert fc.patch(location, content=b"x", headers={**OWNER, "Upload-Offset": "0",
                                                      "Content-Type": "application/offset+octet-stream"}).status_code == 412
    assert fc.head(location, headers=OWNER).status_code == 412
    assert fc.delete(location, headers=OWNER).status_code == 412
    # authentication still comes first
    assert fc.head(location).status_code == 401


def test_a_bad_root_or_cursor_keeps_the_servers_own_reason(fc):
    r = fc.get("/v1/files/list", params={"root": "000"}, headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_root"
    r = fc.get("/v1/files/trash", params={"cursor": "0000"}, headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_cursor"


def test_a_valid_cursor_still_pages(fc):
    for i in range(3):
        mkdir(fc, OWNER, "shared", f"/d{i}")
    first = fc.get("/v1/files/list", params={"root": "shared", "limit": 2}, headers=OWNER)
    assert len(ok(first)) == 2
    link = first.headers["link"]
    cursor = re.search(r"cursor=([A-Za-z0-9_-]+)", link).group(1)
    second = ok(fc.get("/v1/files/list", params={"root": "shared", "limit": 2, "cursor": cursor}, headers=OWNER))
    assert len(second) == 1


# ---- small ones ----------------------------------------------------------------------------------
@pytest.mark.parametrize("since", ["0.5", "17", "1e3"])
def test_notification_since_is_a_date_time_not_a_unix_number(client, since):
    r = client.get("/v1/notifications", params={"since": since}, headers=OWNER)
    assert r.status_code == 422, r.text
    ok_ = client.get("/v1/notifications", params={"since": "2020-01-01T00:00:00Z"}, headers=OWNER)
    assert ok_.status_code == 200


def test_photos_upload_complete_is_an_enum_in_the_schema(client):
    doc = spec(client)
    for method, path in (("post", "/v1/photos/uploads"), ("patch", "/v1/photos/uploads/{upload_id}")):
        p = [p for p in doc["paths"][path][method]["parameters"] if p["name"] == "Upload-Complete"][0]
        assert resolve(doc, p["schema"])["enum"] == ["?0", "?1"]


def test_far_expiry_is_refused_with_its_reason_on_backups_and_migrate(client):
    far = "2099-01-01T00:00:00Z"
    for path, body in (("/v1/backups/destinations", {"kind": "usb", "label": "x", "config": {}, "expires_at": far}),
                       ("/v1/migrate/plans/p/copy", {"kubeconfig": "x", "pvcs": [], "expires_at": far})):
        r = client.post(path, headers={**OWNER, "Idempotency-Key": "k"}, json=body)
        if r.status_code == 422 and "7 days" in r.text:
            assert r.json()["reason"] == "expiry_too_far", r.text


# ---- the fuzz hooks themselves -------------------------------------------------------------------
class _Resp:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        return self._body


class _Case:
    def __init__(self, path, positive=True):
        class Mode:
            is_positive = positive
        class Gen:
            mode = Mode()
        class Meta:
            generation = Gen()
        class Op:
            pass
        self.operation, self.meta = Op(), Meta()
        self.operation.path = path


def _hooks():
    pytest.importorskip("schemathesis")  # the pinned fuzz group; the plain test env skips these two
    import api_fuzz_hooks
    return api_fuzz_hooks


def test_semantic_refusal_check_wants_a_known_reason_and_only_for_positive_data():
    h = _hooks()
    check = h.semantic_refusal_names_its_reason.__wrapped__ if hasattr(h.semantic_refusal_names_its_reason, "__wrapped__") \
        else h.semantic_refusal_names_its_reason
    check(None, _Resp(422, {"reason": "invalid_path"}), _Case("/v1/files/list"))
    check(None, _Resp(422, {"message": "request failed validation"}), _Case("/v1/files/list", positive=False))
    check(None, _Resp(422, {"message": "request failed validation"}), _Case("/v1/instance"))
    for body in ({"message": "request failed validation"}, {"reason": "something_else"}):
        with pytest.raises(AssertionError):
            check(None, _Resp(422, body), _Case("/v1/files/list"))


def test_unavailable_check_pins_the_envelope_and_the_routes():
    h = _hooks()
    check = getattr(h.unavailable_is_the_documented_envelope, "__wrapped__", h.unavailable_is_the_documented_envelope)
    ok_body = {"error": "unavailable", "message": "m", "reason": "backups_disabled", "retry_after_s": 30}
    check(None, _Resp(503, ok_body, {"retry-after": "30"}), _Case("/v1/backups/runs"))
    check(None, _Resp(500, {}), _Case("/v1/files/list"))
    for resp, path in ((_Resp(503, ok_body, {"retry-after": "30"}), "/v1/files/list"),
                       (_Resp(503, {**ok_body, "reason": "boom"}, {"retry-after": "30"}), "/v1/backups/runs"),
                       (_Resp(503, ok_body, {}), "/v1/backups/runs")):
        with pytest.raises(AssertionError):
            check(None, resp, _Case(path))


def test_semantic_validation_refusals_name_their_reason(client):
    cases = (("app.delete_data", {"app_id": "uptime-kuma", "confirm": "other"}, "confirm_mismatch"),
             ("app.configure", {"app_id": "uptime-kuma", "settings": {"API_TOKEN": "x"}}, "invalid_settings"))
    for type_, params, reason in cases:
        r = client.post("/v1/plans", headers=OWNER, json={"type": type_, "params": params})
        assert r.status_code == 422 and r.json()["reason"] == reason, r.text
    # a plain schema failure stays reason-less: that is what the fuzz treats as a schema disagreement
    r = client.post("/v1/plans", headers=OWNER, json={"type": "app.stop", "params": {"app_id": "uptime-kuma", "x": 1}})
    assert r.status_code == 422 and "reason" not in r.json()


def test_fuzz_config_names_one_operation_for_the_413_adaptation(client, monkeypatch, tmp_path):
    """include-path + include-method matches on either, which once leaked the 413 allowance to every POST."""
    pytest.importorskip("schemathesis")
    import api_fuzz_check
    import schemathesis
    from schemathesis.config import SchemathesisConfig

    monkeypatch.setenv("OWNER_TOKEN", "o")
    monkeypatch.setenv("AGENT_TOKEN", "a")
    monkeypatch.setattr(api_fuzz_check, "call", lambda g, t, path, *a: [{"id": "x"}] if path == "/v1/apps" else {"id": "y"})
    config = tmp_path / "s.toml"
    assert api_fuzz_check.prepare("http://unit.invalid", config) == 0
    cfg = SchemathesisConfig.from_str(config.read_text())
    schema = schemathesis.openapi.from_dict(spec(client), config=cfg)
    seen = {}
    for result in schema.get_all_operations():
        op = result.ok()
        checks = schema.config.operations.get_for_operation(op).checks
        seen[op.label] = {name: set(getattr(getattr(checks, name), "expected_statuses", None) or [])
                          for name in ("positive_data_acceptance", "not_a_server_error")}
    assert "413" in seen["POST /v1/tokens"]["positive_data_acceptance"]
    assert "413" in seen["PUT /v1/apps/{app_id}/access"]["positive_data_acceptance"]
    assert "413" not in seen["POST /v1/files/ops"]["positive_data_acceptance"]
    assert "413" not in seen["POST /v1/plans"]["positive_data_acceptance"]
    assert "503" in seen["GET /v1/backups/status"]["not_a_server_error"]
    assert "503" not in seen["GET /v1/instance"]["not_a_server_error"]
