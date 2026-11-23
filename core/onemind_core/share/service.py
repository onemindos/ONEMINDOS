# SPDX-License-Identifier: Apache-2.0
"""Send to: hand one typed object to one app (#612).

A share is a hand-off of a reference, never of the object's content: the receiving app opens the
object through its own routes, with its own access checks. The gateway hands an object only to an
app that

1. the caller may see (the §12.6 sharing filters, as GET /v1/apps) and that is switched on;
2. accepts the type in its descriptor (`spec.share.accepts`) and the verb (`spec.share.verbs`);
3. holds the grant for the type's data class (`spec.data.owns` or `spec.data.reads`, types.py).

A hand-off is the event `share.sent`: one audit line (the record) and `onemind.event.share.sent`
on NATS, which the receiving app listens to. Its payload carries ids only (app, verb, type, ref),
never a title or content, because audit lines are kept for a year. Only a person sends: an agent
may list where an object could go, but handing it over is the person's tap (AI never actuates).

A send may carry an `Idempotency-Key` (contract §12.1, docs/leap/dev/API.md): the same key, person
and share within 24 hours replays the first answer instead of handing the object over twice; the
same key with a different share is 409 `idempotency_mismatch`. Keys are kept hashed, in this
gateway process only (a restart forgets them), at most REPLAY_MAX of them.

Apps come from the built-in descriptors (builtins.py) today; a Market app joins once the share
block moves into onemind.app.schema.json.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import Request

from ..audit import canonical_json
from ..auth import Principal
from ..builtins import Builtins, Descriptor
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import ApiError
from .types import TYPES, deep_link, holds_grant

SENDER_ROLES = frozenset({"owner", "adult"})
REPLAY_TTL = timedelta(hours=24)
REPLAY_MAX = 4096


class ShareService:
    def __init__(self, gw: Gateway, registry: Callable[[], Builtins | None]):
        self.gw = gw
        self.registry = registry
        # (principal kind, id, sha256 of the key) -> (expires, sha256 of the share, the first answer)
        self._replays: OrderedDict[tuple[str, str, str], tuple[datetime, str, dict]] = OrderedDict()
        self._lock = threading.Lock()

    def _apps(self) -> dict[str, Descriptor]:
        reg = self.registry()
        return dict(reg.descriptors) if reg is not None else {}

    def _off(self) -> frozenset[str]:
        reg = self.registry()
        return reg.disabled() if reg is not None else frozenset()

    def _visible(self, request: Request, p: Principal, app_id: str) -> bool:
        return all(f(request, p, app_id) for f in self.gw.app_filters)

    def types(self) -> list[dict]:
        return [{"name": t.name, "title": t.title, "data_class": t.data_class, "ref": t.ref} for t in TYPES.values()]

    def targets(self, request: Request, p: Principal, share_type: str) -> list[dict]:
        """The switched-on apps this caller sees that would take an object of this type."""
        off = self._off()
        out = []
        for app_id, d in sorted(self._apps().items()):
            share = d.spec.get("share")
            if (app_id in off or not share or share_type not in share["accepts"]
                    or not holds_grant(d.spec, share_type) or not self._visible(request, p, app_id)):
                continue
            out.append({"app_id": app_id, "name": d.name, "verbs": list(share["verbs"])})
        return out

    def _refuse(self, p: Principal, status: int, error: str, message: str, reason: str, facts: dict) -> ApiError:
        self.gw.audit.append("share.refused", p.as_dict(), None, {**facts, "reason": reason})
        return ApiError(status, error, message, reason=reason)

    def send(self, request: Request, p: Principal, to: str, verb: str, obj: dict,
             idempotency_key: str | None = None) -> tuple[dict, bool]:
        """Hand the object over. Returns (the share, True when it is a replay of an earlier send)."""
        if p.kind != "person" or p.role not in SENDER_ROLES:
            self.gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "share.send", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only a person sends; an agent may list targets and draft")
        if idempotency_key is None:
            return self._send(request, p, to, verb, obj), False
        slot = (p.kind, p.id, hashlib.sha256(idempotency_key.encode()).hexdigest())
        digest = hashlib.sha256(canonical_json({"to": to, "verb": verb, "object": obj}).encode()).hexdigest()
        with self._lock:  # one keyed send at a time, so two racing retries cannot both hand over
            now = self.gw.clock()
            while self._replays and next(iter(self._replays.values()))[0] <= now:
                self._replays.popitem(last=False)
            hit = self._replays.get(slot)
            if hit is not None:
                if hit[1] != digest:
                    raise ApiError(409, "conflict", "Idempotency-Key was already used for a different share",
                                   reason="idempotency_mismatch")
                return hit[2], True
            out = self._send(request, p, to, verb, obj)
            self._replays[slot] = (now + REPLAY_TTL, digest, out)
            while len(self._replays) > REPLAY_MAX:
                self._replays.popitem(last=False)
            return out, False

    def _send(self, request: Request, p: Principal, to: str, verb: str, obj: dict) -> dict:
        facts = {"to": to, "verb": verb, "type": obj["type"]}
        d = self._apps().get(to) if APP_ID_RE.match(to) else None
        if d is None or not self._visible(request, p, to):
            raise self._refuse(p, 404, "not_found", "no such app", "unknown_app", facts)
        if to in self._off():
            raise self._refuse(p, 409, "stale_precondition", f"{d.name} is switched off", "app_disabled", facts)
        share = d.spec.get("share") or {"accepts": [], "verbs": []}
        if obj["type"] not in share["accepts"]:
            raise self._refuse(p, 409, "conflict", f"{d.name} does not accept a {obj['type']}", "type_not_accepted", facts)
        if verb not in share["verbs"]:
            raise self._refuse(p, 409, "conflict", f"{d.name} cannot {verb} a shared object", "verb_not_accepted", facts)
        if not holds_grant(d.spec, obj["type"]):
            data_class = TYPES[obj["type"]].data_class
            raise self._refuse(p, 409, "conflict", f"{d.name} does not hold the {data_class} grant a {obj['type']} needs",
                               "no_grant", facts)
        link = deep_link(to, obj["type"], obj["ref"])
        payload = {**facts, "ref": obj["ref"], "source": obj.get("source"), "link": link}
        env = self.gw.events.publish_event("share", "sent", payload, principal=p.as_dict(),
                                           resource={"kind": "app", "id": to})
        return {"id": env["id"], "to": to, "verb": verb, "object": obj, "link": link, "sent_at": env["ts"]}
