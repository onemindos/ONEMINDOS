# SPDX-License-Identifier: Apache-2.0
"""Regressions for what the api-fuzz job found on the landing branch (run 45746568014 and the local
seed sweep after it). Each test pins the published contract to what the server does; none loosens a
server check or a fuzz check.
"""
from __future__ import annotations

import json
import re

import pytest
from hypothesis import given, settings as hsettings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator, ValidationError

from conftest import AGENT, OWNER
from files_support import fc, files_root, files_settings  # noqa: F401
from onemind_core.dashboard_cards import SUBJECT_RE, event_pattern
from onemind_core.errors import ApiError, SemanticValueError
from onemind_core.files.errors import FilesError
from onemind_core.routers.sync import IF_MATCH_RE, _if_match
from onemind_core.routers.work import REVISION_RE, _revision
from test_datagrants import granted, live, write  # noqa: F401  (live is a fixture)


def spec(client) -> dict:
    return client.get("/openapi.json").json()


def header_param(op: dict, name: str) -> dict:
    return next(p for p in op["parameters"] if p["in"] == "header" and p["name"].lower() == name.lower())


# ---- GET /v1/custom-apps(/{app_id}): an agent's 403 is documented --------------------------------------
@pytest.mark.parametrize("path", ["/v1/custom-apps", "/v1/custom-apps/{app_id}"])
def test_custom_app_reads_document_the_403_an_agent_gets(client, path):
    assert "403" in spec(client)["paths"][path]["get"]["responses"]
    r = client.get(path.replace("{app_id}", "freshrss"), headers=AGENT)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied", r.text


# ---- GET /v1/data/classes/{data_class}/stream: each SSE event matches the documented event schema ------
def frames(resp):
    """Each dispatched SSE event as the fields a client sees: event, id, data (raw strings)."""
    cur: dict = {}
    for line in resp.iter_lines():
        if line == "":
            if "data" in cur:
                yield cur
            cur = {}
        elif not line.startswith(":"):
            k, _, v = line.partition(": ")
            if k != "retry":
                cur[k] = v


def check_event(schema: dict, frame: dict) -> None:
    Draft202012Validator(schema).validate(frame)
    branch = next(b for b in schema["oneOf"] if b["properties"]["event"]["const"] == frame["event"])
    Draft202012Validator(branch["properties"]["data"]["contentSchema"]).validate(json.loads(frame["data"]))


def test_the_data_stream_events_match_their_documented_schema(live, clock):  # noqa: F811
    op = live.get("/openapi.json").json()["paths"]["/v1/data/classes/{data_class}/stream"]["get"]
    schema = op["responses"]["200"]["content"]["text/event-stream"]["schema"]
    seen = []
    with live.stream("GET", "/v1/data/classes/location/stream", headers=AGENT) as r:
        seen += list(frames(r))  # no grant: one `end` and the stream closes
    granted(live, clock, "fz1", data_class="location", read=True, grantee={"kind": "agent", "id": "hermes"})
    with live.stream("GET", "/v1/data/classes/location/stream", headers=AGENT) as r:
        events = frames(r)
        assert write(live).status_code == 201
        seen.append(next(events))
    assert [f["event"] for f in seen] == ["end", "record"], seen
    assert json.loads(seen[0]["data"]) == {"reason": "no_grant"}
    for f in seen:
        check_event(schema, f)
    # The schema still refuses what the stream never sends.
    for bad in ({"event": "end", "data": json.dumps({"reason": "other"})},
                {"event": "record", "data": seen[1]["data"]},  # a record without its id
                {"event": "nope", "data": "{}"}):
        with pytest.raises(ValidationError):
            check_event(schema, bad) if bad["event"] == "end" else Draft202012Validator(schema).validate(bad)


# ---- POST /v1/sync/commit: If-Match is documented as the revision it must be ---------------------------
def test_sync_commit_documents_its_if_match_shape(client):
    param = header_param(spec(client)["paths"]["/v1/sync/commit"]["post"], "If-Match")
    assert param["schema"]["pattern"] == IF_MATCH_RE  # beside anyOf [string, null]: a pattern binds only strings


@hsettings(max_examples=200, deadline=None)
@given(st.from_regex(IF_MATCH_RE, fullmatch=True))
def test_every_if_match_the_schema_allows_is_a_revision(value):
    assert _if_match(value) == int(value.removeprefix("W/").strip('"'))


@pytest.mark.parametrize("value", ["null", "*", "", "²", "١٢", '"-1"', "1" * 19])
def test_an_if_match_outside_the_schema_is_a_named_422(value):
    with pytest.raises(FilesError) as e:
        _if_match(value)
    assert e.value.status == 422 and e.value.reason == "invalid_precondition"


def test_a_superscript_digit_in_if_match_is_a_422_not_a_500(fc):  # noqa: F811
    r = fc.post("/v1/sync/commit", headers={**OWNER, "If-Match": b"\xb2"}, json={
        "root": "shared", "path": "/x.txt", "size": 0, "sha256": "0" * 64, "chunks": [], "base_revision": 0})
    assert r.status_code == 422 and r.json()["reason"] == "invalid_precondition", r.text


# ---- PATCH /v1/work/projects/{project_id}/tasks/{task_id}: If-Match is a task revision ------------------
def test_work_task_update_documents_its_if_match_shape(client):
    op = spec(client)["paths"]["/v1/work/projects/{project_id}/tasks/{task_id}"]["patch"]
    assert header_param(op, "If-Match")["schema"]["pattern"] == REVISION_RE


@hsettings(max_examples=200, deadline=None)
@given(st.from_regex(REVISION_RE, fullmatch=True).filter(lambda v: len(v) <= 12))
def test_every_task_revision_the_schema_allows_is_taken(value):
    assert _revision(value) >= 1


@pytest.mark.parametrize("value", ["0", '"0"', "abc", "²", '"5'])
def test_a_task_revision_outside_the_schema_is_a_named_422(value):
    with pytest.raises(ApiError) as e:
        _revision(value)
    assert e.value.status == 422 and e.value.reason == "bad_revision"


# ---- non-ASCII digits: a 422 or ignored, never int() raising into a 500 --------------------------------
def test_a_superscript_digit_cursor_on_data_records_is_a_named_422(client):
    r = client.get("/v1/data/classes/public/records", params={"cursor": "²"}, headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_cursor", r.text


def test_a_superscript_digit_last_event_id_on_the_data_stream_is_ignored(live):  # noqa: F811
    with live.stream("GET", "/v1/data/classes/location/stream", headers={**AGENT, "Last-Event-ID": b"\xb2"}) as r:
        assert r.status_code == 200
        assert [f["event"] for f in frames(r)] == ["end"]


def test_a_superscript_totp_code_does_not_match():
    from onemind_core.identity.crypto import totp_match
    assert totp_match("JBSWY3DPEHPK3PXP", "²²²²²²") is None


def test_sync_commit_if_match_is_not_nullable(client):
    """A nullable header schema made the fuzzer send the text "null" as a schema-valid If-Match."""
    schema = header_param(spec(client)["paths"]["/v1/sync/commit"]["post"], "If-Match")["schema"]
    assert schema["type"] == "string" and "anyOf" not in schema, schema


# ---- work tasks: priority 3.0 is the integer 3, a number is no due date --------------------------------
def test_a_work_capture_takes_priority_3_point_0_and_refuses_a_numeric_due_date(client):
    r = client.post("/v1/work/capture", headers={**OWNER, "Idempotency-Key": "fz-cap-1"},
                    json={"title": "t", "priority": 3.0})
    assert r.status_code == 201 and r.json()["priority"] == 3, r.text
    for bad in ({"priority": True}, {"priority": "3"}, {"priority": 3.5}, {"due_at": 0}, {"due_at": False}):
        r = client.post("/v1/work/capture", headers={**OWNER, "Idempotency-Key": f"fz-cap-{bad}"},
                        json={"title": "t", **bad})
        assert r.status_code == 422, (bad, r.text)


# ---- PUT /v1/me/dashboard-card: the subject pattern is the validator's rule ----------------------------
@hsettings(max_examples=300, deadline=None)
@given(st.from_regex(SUBJECT_RE, fullmatch=True))
def test_every_subject_the_schema_allows_is_enrolled(subject):
    event_pattern(subject)  # raises SemanticValueError (422 bad_subject) otherwise


@pytest.mark.parametrize("subject", ["onemind.event.backup.done", "onemind.event.node.*", "onemind.event.node.a.*.c.d"])
def test_good_subjects_match_the_pattern(subject):
    assert re.fullmatch(SUBJECT_RE, subject)
    event_pattern(subject)


@pytest.mark.parametrize("subject", ["0", "onemind.event.photos.x", "onemind.event.node", "onemind.event.node.*.*",
                                     "onemind.event.node.a.b.c.d.e", "onemind.event.node.A", "x.node.a"])
def test_bad_subjects_miss_the_pattern_and_the_validator(subject):
    assert not re.fullmatch(SUBJECT_RE, subject)
    with pytest.raises(SemanticValueError):
        event_pattern(subject)


def test_dashboard_card_subject_is_documented_with_its_pattern(client):
    doc = spec(client)
    assert doc["components"]["schemas"]["SubjectSource"]["properties"]["subject"]["pattern"] == SUBJECT_RE


def test_automation_dry_run_documents_the_403_a_household_member_gets(client):
    assert "403" in spec(client)["paths"]["/v1/automation/rules/{rule_id}/dry-run"]["post"]["responses"]


# ---- refusals only the server can judge: each named with a reason on the fuzz hook's closed list -------
def test_app_password_scopes_name_each_space_once(client):
    r = client.post("/v1/files/app-passwords", headers=OWNER, json={"label": "fz", "scopes": ["home:r", "home:rw"]})
    assert r.status_code == 422 and r.json()["reason"] == "invalid_scopes", r.text


def test_quick_add_with_an_unknown_time_zone_names_its_reason(client):
    r = client.post("/v1/work/quick-add", headers={**OWNER, "Idempotency-Key": "fz-qa"},
                    json={"text": "Pay rent tomorrow", "tz": "Mars/Olympus"})
    assert r.status_code == 422 and r.json()["reason"] == "bad_quick_add", r.text


def test_a_work_cursor_from_another_project_is_invalid_cursor(client):
    r = client.get("/v1/work/tasks", params={"project_id": "prj_a", "cursor": "prj_b/tsk_x"}, headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_cursor", r.text


def test_the_fuzz_hook_lists_these_reasons_and_still_fails_any_other():
    pytest.importorskip("schemathesis")
    from types import SimpleNamespace

    from api_fuzz_hooks import FILES_SEMANTIC_REFUSALS, semantic_refusal_names_its_reason
    assert {"invalid_expiry", "invalid_manifest", "invalid_scopes", "bad_quick_add", "invalid_cursor",
            "unknown_item"} <= FILES_SEMANTIC_REFUSALS
    assert "invalid_precondition" not in FILES_SEMANTIC_REFUSALS  # If-Match is described by its pattern instead
    positive = SimpleNamespace(meta=SimpleNamespace(generation=SimpleNamespace(mode=SimpleNamespace(is_positive=True))))
    for reason, ok in (("invalid_scopes", True), (None, False), ("bad_subject", False), ("invalid_precondition", False)):
        resp = SimpleNamespace(status_code=422, json=lambda reason=reason: {"error": "conflict", "reason": reason})
        if ok:
            semantic_refusal_names_its_reason(None, resp, positive)
        else:
            with pytest.raises(AssertionError):
                semantic_refusal_names_its_reason(None, resp, positive)

    sync_commit = SimpleNamespace(path="/v1/sync/commit", method="post")
    unrelated = SimpleNamespace(path="/v1/sync/chunks/missing", method="post")
    resp = SimpleNamespace(status_code=422, json=lambda: {"error": "conflict", "reason": "hash_mismatch"})
    positive.operation = sync_commit
    semantic_refusal_names_its_reason(None, resp, positive)
    positive.operation = unrelated
    with pytest.raises(AssertionError, match="hash_mismatch"):
        semantic_refusal_names_its_reason(None, resp, positive)

    positive.operation = sync_commit
    resp = SimpleNamespace(status_code=422, json=lambda: {"error": "conflict", "reason": "chunks_or_manifest"})
    with pytest.raises(AssertionError, match="chunks_or_manifest"):
        semantic_refusal_names_its_reason(None, resp, positive)


# ---- bring your own domain switched off: a setup state (409), not a server fault ----------------------
def test_domains_switched_off_is_409_on_every_write(client):
    for method, path, body in (("POST", "/v1/domains", {"domain": "example.org"}),
                               ("POST", "/v1/domains/example.org/check", None),
                               ("DELETE", "/v1/domains/example.org", None)):
        r = client.request(method, path, headers=OWNER, json=body)
        assert (r.status_code, r.json()["reason"]) == (409, "domains_disabled"), (path, r.text)


# ---- a single-valued query parameter sent twice: 422, not "the last copy wins" ------------------------
def test_a_repeated_single_valued_query_parameter_is_refused(client):
    r = client.get("/v1/audit/verify?from_seq=t&from_seq=%3D%2F&from_seq=5%0D", headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_request", r.text
    assert client.get("/v1/audit/verify?from_seq=1", headers=OWNER).status_code == 200
    # a key the route does not declare is ignored as before, repeated or not
    assert client.get("/v1/audit/verify?x=1&x=2", headers=OWNER).status_code == 200


def test_an_unauthenticated_repeated_parameter_is_401_not_422(client):
    for q in ("from_seq=1&from_seq=2", "from_seq=abc"):
        r = client.get(f"/v1/audit/verify?{q}")
        assert r.status_code == 401 and r.json()["error"] == "unauthenticated", (q, r.text)
    r = client.get("/v1/audit/verify?from_seq=1&from_seq=2", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401, r.text


def test_the_query_guard_is_linear_in_the_number_of_parameters(client, monkeypatch):
    from starlette.datastructures import QueryParams

    size = 200
    comparisons = 0
    multi_items = QueryParams.multi_items

    class MeasuredKey(str):
        __hash__ = str.__hash__

        def __eq__(self, other):
            nonlocal comparisons
            comparisons += 1
            assert comparisons <= 3 * size, "query guard repeatedly scans the query keys"
            return super().__eq__(other)

    def measured_items(params):
        return [(MeasuredKey(key), value) for key, value in multi_items(params)]

    monkeypatch.setattr(QueryParams, "multi_items", measured_items)
    r = client.get("/v1/audit/verify", params=[("from_seq", "1")] * size, headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_request", r.text
    assert "from_seq" in r.json()["message"], r.text


def test_a_list_query_parameter_still_takes_many_values():
    from fastapi import Depends, FastAPI, Query
    from fastapi.testclient import TestClient

    from onemind_core.errors import install_handlers
    from onemind_core.querystrict import one_value_per_query_parameter
    app = FastAPI(dependencies=[Depends(one_value_per_query_parameter)])
    install_handlers(app)

    def page(cursor: str | None = Query(None)):
        return cursor

    @app.get("/t")
    def t(types: list[str] | None = Query(None), limit: int = 5, cursor=Depends(page)):
        return {"types": types, "limit": limit, "cursor": cursor}

    c = TestClient(app)
    assert c.get("/t?types=a&types=b").json() == {"types": ["a", "b"], "limit": 5, "cursor": None}
    for q in ("limit=1&limit=2", "cursor=a&cursor=b"):  # a route's own and a dependency's parameter
        r = c.get(f"/t?{q}")
        assert r.status_code == 422 and r.json()["reason"] == "invalid_request", (q, r.text)


# ---- work names and labels: length on what was sent, at least one non-space character -----------------
def test_work_labels_and_titles_document_and_enforce_a_non_blank_value(client):
    import sys

    from onemind_core.work.service import NONBLANK, SPACE_CHARS
    assert set(SPACE_CHARS) == {chr(i) for i in range(sys.maxunicode + 1) if chr(i).isspace()}
    doc = spec(client)
    capture = resolve(doc, doc["paths"]["/v1/work/capture"]["post"]["requestBody"]["content"]["application/json"]["schema"])
    assert capture["properties"]["title"]["pattern"] == NONBLANK
    for bad in ({"labels": ["\u0085"]}, {"title": "   "}, {"title": "\x1c"}, {"title": " " * 10 + "x" * 155}):
        r = client.post("/v1/work/capture", headers={**OWNER, "Idempotency-Key": f"fz-blank-{len(str(bad))}-{bad!r}"[:80]},
                        json={"title": "t", **bad})
        assert r.status_code == 422, (bad, r.text)
    r = client.post("/v1/work/capture", headers={**OWNER, "Idempotency-Key": "fz-blank-ok"},
                    json={"title": "  Pay rent  ", "labels": [" home "]})
    assert r.status_code == 201 and (r.json()["title"], r.json()["labels"]) == ("Pay rent", ["home"]), r.text


def resolve(doc, schema):
    while "$ref" in schema:
        schema = doc["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    return schema


def test_a_task_change_uses_the_same_title_and_label_rule(client):
    task = client.post("/v1/work/capture", headers={**OWNER, "Idempotency-Key": "fz-chg"}, json={"title": "t"}).json()
    url = f"/v1/work/projects/{task['project_id']}/tasks/{task['id']}"
    for bad in ({"labels": [""]}, {"labels": ["\u0085"]}, {"title": "  "}):
        r = client.patch(url, headers={**OWNER, "If-Match": f'"{task["revision"]}"'}, json=bad)
        assert r.status_code == 422, (bad, r.text)
    r = client.patch(url, headers={**OWNER, "If-Match": f'"{task["revision"]}"'}, json={"title": " New ", "labels": [" x "]})
    assert r.status_code == 200 and (r.json()["title"], r.json()["labels"]) == ("New", ["x"]), r.text


def test_a_task_change_allows_null_for_assignee_due_date_and_dependencies(client):
    doc = spec(client)
    props = resolve(doc, doc["paths"]["/v1/work/projects/{project_id}/tasks/{task_id}"]["patch"]["requestBody"]
                    ["content"]["application/json"]["schema"])["properties"]
    for name in ("title", "body", "status", "priority", "labels"):
        assert "anyOf" not in props[name] and "default" not in props[name], (name, props[name])
    for name in ("assignee", "due_at", "dependencies"):
        assert {"type": "null"} in props[name]["anyOf"], name
    task = client.post("/v1/work/capture", headers={**OWNER, "Idempotency-Key": "fz-null"}, json={"title": "t"}).json()
    url = f"/v1/work/projects/{task['project_id']}/tasks/{task['id']}"
    r = client.patch(url, headers={**OWNER, "If-Match": f'"{task["revision"]}"'}, json={"labels": None, "priority": 4})
    assert r.status_code == 422 and r.json().get("reason") != "bad_task", r.text  # a schema violation, not a refusal
    r = client.patch(url, headers={**OWNER, "If-Match": f'"{task["revision"]}"'}, json={"due_at": None, "priority": 2})
    assert r.status_code == 200 and r.json()["priority"] == 2, r.text


# ---- sync commit: exactly one of chunks / manifest_chunks is in the schema, not only in the server ----
def test_commit_schema_says_exactly_one_of_chunks_or_manifest_chunks(client):
    doc = spec(client)
    schema = doc["components"]["schemas"]["CommitBody"]
    assert schema["oneOf"] == [{"required": ["chunks"]}, {"required": ["manifest_chunks"]}]
    for name in ("chunks", "manifest_chunks"):
        assert "null" not in json.dumps(schema["properties"][name]), schema["properties"][name]
    validator = Draft202012Validator(schema)
    base = {"root": "shared", "path": "/x.txt", "size": 0, "sha256": "0" * 64}
    assert not validator.is_valid(base)
    assert not validator.is_valid({**base, "chunks": [], "manifest_chunks": []})
    assert validator.is_valid({**base, "chunks": []})
    assert validator.is_valid({**base, "manifest_chunks": []})


@pytest.mark.parametrize("extra", [{}, {"chunks": [], "manifest_chunks": []}])
def test_commit_refuses_neither_or_both_with_422_chunks_or_manifest(client, extra):
    r = client.post("/v1/sync/commit", headers=OWNER,
                    json={"root": "shared", "path": "/x.txt", "size": 0, "sha256": "0" * 64, **extra})
    assert r.status_code == 422 and r.json()["reason"] == "chunks_or_manifest", (extra, r.text)


@pytest.mark.parametrize("extra", [{"chunks": None, "manifest_chunks": []}, {"chunks": [], "manifest_chunks": None},
                                   {"chunks": None}])
def test_commit_refuses_a_null_list_as_a_schema_violation(client, extra):
    r = client.post("/v1/sync/commit", headers=OWNER,
                    json={"root": "shared", "path": "/x.txt", "size": 0, "sha256": "0" * 64, **extra})
    assert r.status_code == 422 and r.json().get("reason") is None, (extra, r.text)
