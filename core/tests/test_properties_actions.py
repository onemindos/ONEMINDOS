# SPDX-License-Identifier: Apache-2.0
"""Property tests: the action state machine and idempotency keys (contract §3, actions.py, ledger.py).

"AI never actuates without human approval" (CLAUDE.md, contract §3) as properties:

1. The transition table: no edge leaves a terminal state, nothing goes back to awaiting approval,
   and `accepted` (an approval) is entered only from `awaiting_approval`. The repository refuses
   every pair the table does not list.
2. A stateful model (Hypothesis RuleBasedStateMachine) drives ActionService with random requests,
   approvals, denials, clock jumps, executor outcomes and crashes, and gateway restarts, from
   owners, adults, guests, an operator agent, an app's agent principal (§11.2) and principals
   that are misconfigured on purpose (an agent with role owner). After every step:
   - every state an action was seen in follows from the one before through the table;
   - every action that was approved, denied or ran was decided by a person with role owner, and
     the audit log says the same; no agent, whatever its role, is ever the decider;
   - the executor ran exactly once per dispatched action, and only for owner-approved ones;
   - nothing is left half-dispatched, and an app's agent token is live exactly while the app is
     installed;
   - the audit chain verifies.
3. Any expires_at the request model accepts is answered with an action or an ApiError (a
   4xx the client can act on), never an unhandled exception (a 500 with no audit entry).
4. Idempotency keys (§3): replaying a request returns the same action (created=False), the same
   key with any other request is 409 conflict, a key that was refused stays free, the same
   instant written with another UTC offset is the same request, and every refusal is audited.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st
from pydantic import ValidationError
from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, multiple, rule
from sqlalchemy import select

from conftest import FIXTURES, Clock, ScriptedExecutor, write_scan
from onemind_core.actions import ActionRequest, ActionService
from onemind_core.audit import AuditLog, verify
from onemind_core.auth import Principal
from onemind_core.catalog import Catalog
from onemind_core.errors import ApiError
from onemind_core.ledger import ALLOWED, STATES, TERMINAL, AgentTokenRow, SqlActionRepository, make_engine, utc
from props import budget
from api_fuzz_check import decision_problems

OWNER = Principal("owner", "person", "owner")
SECOND_OWNER = Principal("co-owner", "person", "owner")
PRINCIPALS = [
    OWNER,
    SECOND_OWNER,
    Principal("adult", "person", "adult"),
    Principal("guest", "person", "guest"),
    Principal("hermes", "agent", "agent"),
    Principal("agent:hermes-like", "agent", "agent"),  # the §11.2 principal of an installed app
    Principal("rogue", "agent", "owner"),  # misconfigured: an agent must never count as an owner
    Principal("odd", "person", "agent"),  # misconfigured the other way: may neither request nor decide
]
# The oracle comes from the contract (§3), not from Principal.is_owner, so a bug there cannot
# hide itself: only a person with role owner decides; owners and agents (role agent) request.
OWNERS = [OWNER, SECOND_OWNER]
NOT_OWNERS = [p for p in PRINCIPALS if p not in OWNERS]
REQUESTERS = {OWNER, SECOND_OWNER, PRINCIPALS[4], PRINCIPALS[5]}
APPROVED = frozenset({"accepted", "dispatched", "succeeded", "failed", "outcome_unknown"})
APPS = ["uptime-kuma", "hermes-like", "whoami", "no-such-app"]  # whoami has no scan record


def reachable(src: str) -> set[str]:
    seen, todo = {src}, [src]
    while todo:
        for nxt in ALLOWED.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


# ---- 1. the table ------------------------------------------------------------------------------

def test_transition_table_shape():
    assert set(ALLOWED) | {s for v in ALLOWED.values() for s in v} <= set(STATES)
    assert not TERMINAL & set(ALLOWED), "a terminal state has an outgoing edge"
    assert all(TERMINAL & reachable(s) for s in STATES), "a state that can never finish"
    entering = {s: {src for src, dst in ALLOWED.items() if s in dst} for s in STATES}
    assert entering["accepted"] == {"awaiting_approval"}
    assert entering["requested"] == set() and entering["awaiting_approval"] == {"requested"}
    assert all("awaiting_approval" not in reachable(s) for s in APPROVED | TERMINAL)


@budget(100)
@given(src=st.sets(st.sampled_from(STATES), min_size=1, max_size=3), dst=st.sampled_from(STATES))
def test_repository_refuses_every_transition_the_table_does_not_list(src, dst):
    repo = SqlActionRepository(make_engine("sqlite://"))
    try:
        legal = all(dst in ALLOWED.get(s, set()) for s in src)
        if legal:  # a legal pair on a missing action is a lost compare-and-swap, not an error
            assert repo.transition("missing", src, dst, Clock()()) is None
        else:
            with pytest.raises(ValueError, match="illegal transition"):
                repo.transition("missing", src, dst, Clock()())
    finally:
        repo.close()


# ---- 2. the stateful model ---------------------------------------------------------------------

class Gateway:
    """An ActionService on an in-memory ledger, a temporary catalog and audit file."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.apps = root / "apps"
        shutil.copytree(FIXTURES / "apps", self.apps)
        self.clock = Clock()
        for app in ("uptime-kuma", "hermes-like"):
            write_scan(self.apps / app, self.clock.now - timedelta(days=1))
        self.audit_path = root / "audit.jsonl"
        self.repo = SqlActionRepository(make_engine("sqlite://"))
        self.executor = ScriptedExecutor()
        self.start()

    def start(self) -> None:
        """(Re)start: a fresh AuditLog resumes the chain, then the service reconciles."""
        self.audit = AuditLog(self.audit_path, self.clock)
        self.svc = ActionService(self.repo, Catalog(self.apps), self.executor, self.audit, self.clock)
        self.svc.reconcile_interrupted()

    def close(self) -> None:
        self.repo.close()
        self.tmp.cleanup()

    def audit_records(self) -> list[dict]:
        if not self.audit_path.exists():  # nothing audited yet
            return []
        return [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").split("\n") if line]


class ActionMachine(RuleBasedStateMachine):
    actions = Bundle("actions")

    def __init__(self):
        super().__init__()
        self.gw = Gateway()
        self.seen: dict[str, str] = {}
        self.keys = 0

    def teardown(self):
        self.gw.close()

    # -- rules --
    @rule(target=actions, who=st.sampled_from(PRINCIPALS), app=st.sampled_from(APPS),
          type_=st.sampled_from(["app.install", "app.install", "app.remove"]),
          ttl=st.sampled_from([-5, 60, 3600, 86400]))
    def request(self, who, app, type_, ttl):
        self.keys += 1
        req = ActionRequest(type=type_, params={"app_id": app}, idempotency_key=f"k{self.keys}",
                            expires_at=self.gw.clock.now + timedelta(seconds=ttl))
        try:
            action, created = self.gw.svc.create(who, req)
        except ApiError as e:
            if who not in REQUESTERS:
                assert e.status == 403 and e.error == "permission_denied"
            else:
                assert e.status in (404, 409), e
            return multiple()
        assert who in REQUESTERS and created
        assert action["state"] == "awaiting_approval" and action["decided_by"] is None
        return action["id"]

    def _decide(self, op: str, who: Principal, action_id: str) -> None:
        before = self.gw.repo.get(action_id).state
        try:
            after = getattr(self.gw.svc, op)(who, action_id)["state"]
            event(f"{op} by {who.kind}/{who.role}: {before} -> {after}")
        except ApiError as e:
            event(f"{op} by {who.kind}/{who.role}: {e.status} {e.error}")
            if who not in OWNERS:
                assert (e.status, e.error) == (403, "permission_denied")
                after = self.gw.repo.get(action_id).state
                assert after == before, f"a refused {op} by {who} moved {before} -> {after}"
            else:
                assert e.status == 409, e
            return
        assert who in OWNERS, f"{op} by {who} was not refused"

    # Owners and everyone else get separate rules so owner decisions are as frequent as refusals.
    @rule(who=st.sampled_from(OWNERS), action_id=actions)
    def owner_approves(self, who, action_id):
        self._decide("approve", who, action_id)

    @rule(who=st.sampled_from(NOT_OWNERS), action_id=actions)
    def someone_else_approves(self, who, action_id):
        self._decide("approve", who, action_id)

    @rule(who=st.sampled_from(OWNERS), action_id=actions)
    def owner_denies(self, who, action_id):
        self._decide("deny", who, action_id)

    @rule(who=st.sampled_from(NOT_OWNERS), action_id=actions)
    def someone_else_denies(self, who, action_id):
        self._decide("deny", who, action_id)

    @rule(seconds=st.sampled_from([1, 61, 61, 3600, 3 * 86400]))
    def time_passes(self, seconds):
        self.gw.clock.advance(seconds)

    @rule(outcome=st.sampled_from(["succeeded", "failed", "outcome_unknown"]), crash=st.booleans())
    def executor_behaves(self, outcome, crash):
        self.gw.executor.outcome, self.gw.executor.raise_exc = outcome, crash

    @rule()
    def gateway_restarts(self):
        self.gw.start()

    @rule()
    def someone_lists_actions(self):
        self.gw.svc.list()  # lazy expiry happens here

    # -- invariants --
    @invariant()
    def states_follow_the_table(self):
        for a in self.gw.repo.list():
            assert a.state in STATES
            prev = self.seen.get(a.id, "awaiting_approval")
            assert a.state in reachable(prev), f"{a.id}: {prev} -> {a.state}"
            self.seen[a.id] = a.state
            assert a.state not in ("accepted", "dispatched"), "left half-dispatched"

    @invariant()
    def only_owners_decide(self):
        listed = [a.to_json() for a in self.gw.repo.list()]
        assert decision_problems(self.gw.audit_records(), listed) == []
        for a in self.gw.repo.list():
            if a.state in APPROVED or a.state == "cancelled":
                assert a.decided_by is not None
                assert (a.decided_by["kind"], a.decided_by["role"]) == ("person", "owner"), a.decided_by
            else:
                assert a.decided_by is None
        for rec in self.gw.audit_records():
            p = rec["principal"] or {}
            if rec["event"] in ("action.approved", "action.denied"):
                assert (p.get("kind"), p.get("role")) == ("person", "owner"), rec
            if rec["event"] == "authz.denied":
                assert (p.get("kind"), p.get("role")) != ("person", "owner"), rec

    @invariant()
    def executor_ran_once_per_owner_approved_dispatch(self):
        dispatched = [r["action_id"] for r in self.gw.audit_records() if r["event"] == "action.dispatched"]
        assert len(dispatched) == len(set(dispatched)) == len(self.gw.executor.calls)
        assert decision_problems(self.gw.audit_records(), [a.to_json() for a in self.gw.repo.list()]) == []

    @invariant()
    def agent_token_live_exactly_while_installed(self):
        with self.gw.repo.engine.connect() as c:
            row = c.execute(select(AgentTokenRow).where(AgentTokenRow.principal_id == "agent:hermes-like")).first()
        live = row is not None and row.revoked_at is None
        state = self.gw.repo.get_app_state("hermes-like")
        assert live == (state is not None and state.status == "installed"), (live, state)

    @invariant()
    def audit_chain_verifies(self):
        ok, _, reason = verify(self.gw.audit_path)
        assert ok, reason


TestActionStateMachine = ActionMachine.TestCase
TestActionStateMachine.settings = budget(40, stateful_step_count=30)


# ---- 3. any expiry --------------------------------------------------------------------------------

offsets = st.timedeltas(min_value=timedelta(hours=-23, minutes=-59), max_value=timedelta(hours=23, minutes=59))


# Most draws land within two days of either end of the datetime range, where a UTC offset can
# carry the instant out of it.
naive = (st.datetimes(min_value=datetime.max - timedelta(days=2))
         | st.datetimes(max_value=datetime.min + timedelta(days=2))
         | st.datetimes())


@budget(100)
@given(expires=st.builds(lambda dt, off: dt.replace(tzinfo=timezone(off)), naive, offsets),
       who=st.sampled_from([OWNER, PRINCIPALS[4]]))
@example(expires=datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone(-timedelta(hours=23, minutes=59))), who=OWNER)
@example(expires=datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=23, minutes=59))), who=PRINCIPALS[4])
def test_any_expiry_gets_an_answer_not_a_crash(expires, who):
    """Finding F-API-1: 9999-12-31T23:59:59-23:59 overflowed to year 10000 in utc() and the
    gateway answered 500 (owner and agent alike), with nothing in the audit log."""
    try:
        req = ActionRequest(type="app.install", params={"app_id": "uptime-kuma"}, idempotency_key="k", expires_at=expires)
    except ValidationError:
        return  # refused by the request model: HTTP 422
    gw = Gateway()
    try:
        try:
            action, _ = gw.svc.create(who, req)
        except ApiError as e:
            assert e.status in (404, 409), e
        else:
            assert action["expires_at"].endswith("Z")
    finally:
        gw.close()


# ---- 4. idempotency keys -----------------------------------------------------------------------

@dataclass(frozen=True)
class Req:
    who: Principal
    type: str
    app: str
    key: str
    expires_in: int  # seconds from the start of the run
    tz_hours: int  # the same instant written with another UTC offset is the same request
    wait: int  # seconds that pass before this request


REQS = st.builds(
    Req,
    who=st.sampled_from(PRINCIPALS),
    type=st.sampled_from(["app.install", "app.remove"]),
    app=st.sampled_from(APPS),
    key=st.sampled_from(["a", "b", "c", "d"]),
    expires_in=st.sampled_from([30, 600, 86400]),
    tz_hours=st.integers(-12, 14),
    wait=st.sampled_from([0, 0, 45, 700]),
)


@budget(60)
@given(reqs=st.lists(REQS, min_size=1, max_size=12))
def test_idempotency_keys(reqs):
    gw = Gateway()
    start = gw.clock.now
    first: dict[str, tuple[Req, str]] = {}  # key -> (the request that created it, action id)
    try:
        for r in reqs:
            gw.clock.advance(r.wait)
            expires = (start + timedelta(seconds=r.expires_in)).astimezone(timezone(timedelta(hours=r.tz_hours)))
            req = ActionRequest(type=r.type, params={"app_id": r.app}, idempotency_key=r.key, expires_at=expires)
            requested_before = sum(rec["event"] == "action.requested" for rec in gw.audit_records())
            try:
                action, created = gw.svc.create(r.who, req)
                error = None
            except ApiError as e:
                action, created, error = None, None, (e.status, e.error)

            if r.who not in REQUESTERS:
                assert error == (403, "permission_denied")
            elif r.key in first:
                orig, action_id = first[r.key]
                if (orig.who.id, orig.type, orig.app, orig.expires_in) == (r.who.id, r.type, r.app, r.expires_in):
                    assert error is None and created is False and action["id"] == action_id
                else:
                    assert error == (409, "conflict")
            elif utc(expires) <= gw.clock.now:
                assert error == (409, "expired")
            elif r.app == "no-such-app":
                assert error == (404, "not_found")
            elif r.type == "app.remove":  # nothing is installed in this run
                assert error == (409, "stale_precondition")
            else:
                assert error is None and created is True
                assert action["id"] not in {aid for _, aid in first.values()}
                first[r.key] = (r, action["id"])

            records = gw.audit_records()
            requested_after = sum(rec["event"] == "action.requested" for rec in records)
            assert requested_after - requested_before == (1 if created else 0)
            if error is not None:  # every refusal is in the audit log, with who asked
                assert records[-1]["event"] == ("authz.denied" if error[0] == 403 else "action.rejected")
                assert records[-1]["principal"] == r.who.as_dict()
        assert sorted(a.idempotency_key for a in gw.repo.list()) == sorted(first)
    finally:
        gw.close()
