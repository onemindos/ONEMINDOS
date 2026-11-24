# SPDX-License-Identifier: Apache-2.0
"""Work read identity for REST and the request-scoped MCP adapter."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import Request

from ..auth import Principal
from ..identity import ctx_of
from ..identity.scopes import has_any

OWN_TASK_ONLY_ROLES = frozenset({"child", "teen"})
WORK_ROLES = OWN_TASK_ONLY_ROLES | {"owner", "adult"}
_authenticated_reader: ContextVar[tuple[Principal, Principal | None] | None] = ContextVar(
    "work_authenticated_reader", default=None,
)


def delegated_reader(request: Request, actor: Principal) -> Principal | None:
    if actor.kind != "agent":
        return None
    ctx = ctx_of(request)
    if ctx is None or ctx.principal != actor or not has_any(ctx.scopes, ("work:read",)):
        return None
    owner_id = ctx.token.owner_user_id if ctx.token is not None and ctx.token.kind == "agent" else None
    owner = request.app.state.identity.user(owner_id) if owner_id else None
    if owner is None or owner.disabled or owner.role not in WORK_ROLES:
        return None
    return Principal(id=owner.id, kind="person", role=owner.role)


@contextmanager
def work_reader_context(request: Request, actor: Principal) -> Iterator[None]:
    """Bind only this authenticated token's delegation for the lifetime of a tool request."""
    token = _authenticated_reader.set((actor, delegated_reader(request, actor)))
    try:
        yield
    finally:
        _authenticated_reader.reset(token)


def current_delegated_reader(actor: Principal) -> Principal | None:
    context = _authenticated_reader.get()
    return context[1] if context is not None and context[0] == actor else None
