# SPDX-License-Identifier: Apache-2.0
"""Tasks extension (io.modelcontextprotocol/tasks, SEP-2663) over the approval wait (DEV-MCP-10).

Only for a 2026-07-28 client that declared the extension. A task is the agent's own action: the
task id is the action id, so a task exists exactly as long as the ledger row does. Status follows
the action; the owner's approval happens out of band in the OneMind app, so a task never reaches
`input_required` and `tasks/update` has nothing to answer. `tasks/cancel` is cooperative and
acknowledges without touching the action: an agent has no path to approve, deny or cancel it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .tools import ACTION_FIELDS, POLL_AFTER_S, REQUEST_TTL, Catalogue, RpcError, _source, result
from .versions import TASK_DONE

INVALID_PARAMS = -32602


def _iso(v) -> str | None:
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return v


def task_of(action: dict) -> dict:
    status = TASK_DONE.get(action["state"], "working")
    msg = {"awaiting_approval": "Waiting for the owner to approve in the OneMind app",
           "requested": "Waiting for the owner to approve in the OneMind app"}.get(action["state"], action["state"])
    return {
        "taskId": action["id"], "status": status, "statusMessage": msg,
        "createdAt": _iso(action.get("created_at")),
        "lastUpdatedAt": _iso(action.get("updated_at") or action.get("created_at")),
        "ttlMs": int(REQUEST_TTL.total_seconds() * 1000), "pollIntervalMs": POLL_AFTER_S * 1000,
    }


def create_result(filed_action: dict) -> dict:
    """CreateTaskResult for a request_action that was just filed (or was already waiting)."""
    return {"resultType": "task", **task_of(filed_action)}


def _task_id(params: dict) -> str:
    tid = params.get("taskId")
    if not isinstance(tid, str) or not tid or len(tid) > 200:
        raise RpcError(INVALID_PARAMS, "taskId must be a non-empty string")
    return tid


def get(cat: Catalogue, p, params: dict) -> dict:
    a = cat._own_action(p, _task_id(params))
    if a is None:  # someone else's task looks exactly like a missing one
        raise RpcError(INVALID_PARAMS, "no such task among your requests")
    out = {"resultType": "complete", **task_of(a)}
    if out["status"] == "completed":
        out["result"] = result(a, ACTION_FIELDS, _source(a, "", "id", "action"))
    elif out["status"] == "failed":
        # The executor message can hold third-party text: mark it exactly as get_action does.
        failed = result({"id": a["id"], "result": {"message": (a.get("result") or {}).get("message") or "action failed"}},
                        ACTION_FIELDS, _source(a, "", "id", "action"))
        out["error"] = {"code": -32000, "message": json.loads(failed["content"][0]["text"])["result"]["message"]}  # the wrapped text
        if "_meta" in failed:
            out["error"]["data"] = {"_meta": failed["_meta"]}
    return out


def update(cat: Catalogue, p, params: dict) -> dict:
    _task_id(params)
    return {"resultType": "complete"}  # no inputRequests are ever issued: nothing to answer


def cancel(cat: Catalogue, p, params: dict) -> dict:
    if cat._own_action(p, _task_id(params)) is None:
        raise RpcError(INVALID_PARAMS, "no such task among your requests")
    return {"resultType": "complete"}  # acknowledged; the action itself is untouched
