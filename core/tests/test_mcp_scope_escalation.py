# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions design PR 4 (gap 4, review item 17): an identity agent token never gets more at /mcp than
it was minted with, and a narrowed request token can still use /mcp, for that type only."""
from __future__ import annotations

from test_identity import csrf, idc, setup_owner  # noqa: F401 (pytest fixture)
from test_mcp import H, rpc


def mint(idc, scopes, name):
    r = idc.post("/v1/tokens", headers=csrf(idc), json={
        "name": name, "principal": {"kind": "agent", "id": f"agent:{name}"}, "scopes": scopes})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["one_time"]["token"]}


def tools(idc, bearer) -> set[str]:
    r = rpc(idc, "tools/list", {}, headers={**H, **bearer})
    assert r.status_code == 200, r.text
    return {t["name"] for t in r.json()["result"]["tools"]}


def test_broad_request_scope_does_not_inherit_the_v0_bundle(idc):
    setup_owner(idc)
    got = tools(idc, mint(idc, ["actions:request"], "broad"))
    assert "request_action" in got  # what it was minted with
    assert "get_instance" in got  # instance:read is always granted
    # v0 would have added every read it was never given:
    assert not got & {"list_nodes", "list_apps", "list_actions", "search_audit", "get_backup_status", "list_alerts"}


def test_narrowed_request_token_reaches_mcp_for_that_type_only(idc):
    setup_owner(idc)
    bearer = mint(idc, ["actions:request:app.install"], "narrow")
    assert "request_action" in tools(idc, bearer)
    assert not tools(idc, bearer) & {"list_nodes", "list_apps", "search_audit"}
    body = {"type": "app.remove", "params": {"app_id": "whoami"}, "reason": "no"}
    denied = rpc(idc, "tools/call", {"name": "request_action", "arguments": body}, headers={**H, **bearer})
    result = denied.json()["result"]
    assert result["isError"] and result["structuredContent"]["scope"] == "actions:request:app.remove"


def test_a_token_with_a_read_scope_gets_that_read_and_not_the_rest(idc):
    setup_owner(idc)
    got = tools(idc, mint(idc, ["actions:request", "apps:read"], "reader"))
    assert "list_apps" in got and "get_app" in got
    assert "list_nodes" not in got


def test_work_reader_still_reaches_only_work_tools(idc):
    setup_owner(idc)
    got = tools(idc, mint(idc, ["work:read"], "work"))
    assert "work_tasks_list" in got and "request_action" not in got and "list_nodes" not in got
