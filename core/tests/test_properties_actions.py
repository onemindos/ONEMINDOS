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
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st
from pydantic import ValidationError
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, invariant, multiple, rule, run_state_machine_as_test
from sqlalchemy import select

from conftest import Clock, ScriptedExecutor
from onemind_core.actions import ActionRequest, ActionService
from onemind_core.audit import AuditLog, verify
from onemind_core.auth import Principal
from onemind_core.catalog import Catalog
from onemind_core.errors import ApiError
from onemind_core.ledger import ALLOWED, STATES, TERMINAL, AgentTokenRow, utc
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

# Contract §3 lifecycle plus pre-dispatch cancellation/failure and interrupted
# acceptance recovery. Pin the reviewed edges independently of production ALLOWED.
EXPECTED_EDGES = {
    "requested": {"awaiting_approval", "cancelled", "expired"},
    "awaiting_approval": {"accepted", "cancelled", "expired"},
    "accepted": {"dispatched", "failed", "outcome_unknown"},
    "dispatched": {"succeeded", "failed", "outcome_unknown"},
}


def reachable(src: str) -> set[str]:
    seen, todo = {src}, [src]
    while todo:
        for nxt in EXPECTED_EDGES.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


# ---- 1. the table ------------------------------------------------------------------------------

def test_transition_table_shape():
    assert ALLOWED == EXPECTED_EDGES
    assert set(ALLOWED) | {s for v in ALLOWED.values() for s in v} <= set(STATES)
    assert not TERMINAL & set(ALLOWED), "a terminal state has an outgoing edge"
    assert all(TERMINAL & reachable(s) for s in STATES), "a state that can never finish"
    entering = {s: {src for src, dst in ALLOWED.items() if s in dst} for s in STATES}
    assert entering["accepted"] == {"awaiting_approval"}
    assert entering["requested"] == set() and entering["awaiting_approval"] == {"requested"}
    assert all("awaiting_approval" not in reachable(s) for s in APPROVED | TERMINAL)


@budget(100)
@given(src=st.sets(st.sampled_from(STATES), min_size=1, max_size=3), dst=st.sampled_from(STATES))
def test_repository_refuses_every_transition_the_table_does_not_list(property_resources, src, dst):
    with property_resources.example() as sample:
        repo = sample.repo
        legal = all(dst in EXPECTED_EDGES.get(s, set()) for s in src)
        if legal:  # a legal pair on a missing action is a lost compare-and-swap, not an error
            assert repo.transition("missing", src, dst, Clock()()) is None
        else:
            with pytest.raises(ValueError, match="illegal transition"):
                repo.transition("missing", src, dst, Clock()())



# ---- 2. the stateful model ---------------------------------------------------------------------

class Gateway:
    """One real backend namespace per machine; restart retains its history."""

    def __init__(self, resources):
        self.handle = resources.example()
        self.sample = self.handle.__enter__()
        self.apps, self.clock = self.sample.apps, self.sample.clock
        self.audit_path, self.repo = self.sample.audit_path, self.sample.repo
        self.executor = ScriptedExecutor()
        try:
            self.start()
        except BaseException:
            self.handle.__exit__(*sys.exc_info())
            raise

    def start(self) -> None:
        """(Re)start: a fresh AuditLog resumes the chain, then the service reconciles."""
        self.audit = AuditLog(self.audit_path, self.clock)
        self.svc = ActionService(self.repo, Catalog(self.apps), self.executor, self.audit, self.clock)
        self.svc.reconcile_interrupted()

    def close(self) -> None:
        self.handle.__exit__(None, None, None)

    def audit_records(self) -> list[dict]:
        if not self.audit_path.exists():  # nothing audited yet
            return []
        return [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").split("\n") if line]


class ActionMachine(RuleBasedStateMachine):
    actions = Bundle("actions")

    def __init__(self, resources):
        super().__init__()
        self.gw = Gateway(resources)
        self.seen: dict[str, str] = {}
        self.keys = 0
        self.model: dict[str, dict] = {}
        self.app_states: dict[str, str] = {}
        self.expected_calls: list[tuple[str, str]] = []
        self.expected_dispatches: list[str] = []

    def teardown(self):
        self.gw.close()

    def _expire_model(self, action):
        if action["state"] == "awaiting_approval" and self.gw.clock.now >= action["expires"]:
            action["state"] = "expired"

    def _app_allowed(self, type_, app):
        status = self.app_states.get(app)
        if type_ == "app.install":
            return status in (None, "failed", "unknown")
        return status in ("installed", "failed", "unknown")

    @initialize(target=actions)
    def mandatory_authorized_decisions(self):
        """Every machine must prove functional success, not only universal refusal."""
        denied = self.request(OWNER, "hermes-like", "app.install", 600)
        approved = self.request(SECOND_OWNER, "uptime-kuma", "app.install", 600)
        self._decide("approve", PRINCIPALS[4], approved)
        self._decide("deny", PRINCIPALS[4], denied)
        self._decide("deny", OWNER, denied)
        self._decide("approve", SECOND_OWNER, approved)
        self._decide("approve", SECOND_OWNER, approved)  # no duplicate dispatch
        return multiple(denied, approved)

    # -- rules --
    @rule(target=actions, who=st.sampled_from(PRINCIPALS), app=st.sampled_from(APPS),
          type_=st.sampled_from(["app.install", "app.install", "app.remove"]),
          ttl=st.sampled_from([-5, 60, 3600, 86400]))
    def request(self, who, app, type_, ttl):
        self.keys += 1
        req = ActionRequest(type=type_, params={"app_id": app}, idempotency_key=f"k{self.keys}",
                            expires_at=self.gw.clock.now + timedelta(seconds=ttl))
        expected_error = None
        if who not in REQUESTERS:
            expected_error = (403, "permission_denied")
        elif ttl <= 0:
            expected_error = (409, "expired")
        else:
            if who not in OWNERS:
                pending = [a for a in self.model.values() if a["who"] == who and a["state"] == "awaiting_approval"]
                for a in pending:
                    self._expire_model(a)
                if sum(a["state"] == "awaiting_approval" for a in pending) >= 10:
                    expected_error = (429, "rate_limited")
            if expected_error is None:
                if app == "no-such-app":
                    expected_error = (404, "not_found")
                elif not self._app_allowed(type_, app):
                    expected_error = (409, "stale_precondition")
        try:
            action, created = self.gw.svc.create(who, req)
        except ApiError as e:
            assert expected_error is not None, f"unexpected request refusal: {e.status} {e.error}"
            assert (e.status, e.error) == expected_error
            return multiple()
        assert expected_error is None, f"request should have failed with {expected_error}"
        assert who in REQUESTERS and created
        assert action["state"] == "awaiting_approval" and action["decided_by"] is None
        self.model[action["id"]] = {"state": "awaiting_approval", "expires": req.expires_at,
                                   "type": type_, "app": app, "who": who, "decider": None}
        return action["id"]

    def _decide(self, op: str, who: Principal, action_id: str) -> None:
        model = self.model[action_id]
        before = model["state"]
        expected_error = None
        if who not in OWNERS:
            expected_error = (403, "permission_denied")
        else:
            self._expire_model(model)
            if model["state"] == "expired":
                expected_error = (409, "expired")
            elif model["state"] != "awaiting_approval":
                expected_error = (409, "conflict")
            elif op == "approve":
                scan_stale = self.gw.clock.now - self.gw.sample.scan_time > timedelta(days=7)
                if (model["type"] == "app.install" and (model["app"] == "whoami" or scan_stale)
                        or not self._app_allowed(model["type"], model["app"])):
                    expected_error = (409, "stale_precondition")
        try:
            after = getattr(self.gw.svc, op)(who, action_id)["state"]
            event(f"{op} by {who.kind}/{who.role}: {before} -> {after}")
        except ApiError as e:
            event(f"{op} by {who.kind}/{who.role}: {e.status} {e.error}")
            assert expected_error is not None, f"unexpected owner refusal: {e.status} {e.error}"
            assert (e.status, e.error) == expected_error
            if who not in OWNERS:
                after = self.gw.repo.get(action_id).state
                assert after == before, f"a refused {op} by {who} moved {before} -> {after}"
            return
        assert expected_error is None, f"{op} should have failed with {expected_error}"
        model["decider"] = who.as_dict()
        model["decision"] = "action.denied" if op == "deny" else "action.approved"
        if op == "deny":
            model["state"] = "cancelled"
        else:
            self.expected_calls.append((model["type"], model["app"]))
            self.expected_dispatches.append(action_id)
            model["state"] = "outcome_unknown" if self.gw.executor.raise_exc else self.gw.executor.outcome
            if model["state"] == "succeeded":
                if model["type"] == "app.install":
                    self.app_states[model["app"]] = "installed"
                else:
                    self.app_states.pop(model["app"], None)
            else:
                self.app_states[model["app"]] = "failed" if model["state"] == "failed" else "unknown"
        assert after == model["state"]

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
        for action in self.model.values():
            self._expire_model(action)

    # -- invariants --
    @invariant()
    def states_follow_the_table(self):
        assert set(self.model) == {a.id for a in self.gw.repo.list()}
        assert {k: v.status for k, v in self.gw.repo.list_app_states().items()} == self.app_states
        for a in self.gw.repo.list():
            assert a.state == self.model[a.id]["state"]
            assert a.decided_by == self.model[a.id]["decider"]
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
        assert dispatched == self.expected_dispatches
        assert self.gw.executor.calls == self.expected_calls
        assert decision_problems(self.gw.audit_records(), [a.to_json() for a in self.gw.repo.list()]) == []

    @invariant()
    def each_action_audit_matches_independent_model(self):
        """Compare kind, actor, outcome and order per id, not only global totals."""
        relevant = {"action.approved", "action.denied", "action.dispatched", "action.expired",
                    "action.succeeded", "action.failed", "action.outcome_unknown"}
        observed = {}
        for record in self.gw.audit_records():
            if record["event"] in relevant:
                observed.setdefault(record["action_id"], []).append((record["event"], record.get("principal")))
        expected = {}
        for action_id, action in self.model.items():
            events = []
            if action["decider"]:
                events.append((action["decision"], action["decider"]))
                if action["decision"] == "action.approved":
                    events.extend([("action.dispatched", None), ("action." + action["state"], None)])
            elif action["state"] == "expired":
                events.append(("action.expired", None))
            if events:
                expected[action_id] = events
        assert observed == expected, "per-action audit/model mismatch"
        # Map each observed dispatch id to its independently requested type/app,
        # in order, then compare the real executor's call stream.
        calls = [(self.model[aid]["type"], self.model[aid]["app"]) for aid in self.expected_dispatches]
        assert self.gw.executor.calls == calls

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


def test_action_state_machine(property_resources):
    run_state_machine_as_test(lambda: ActionMachine(property_resources),
                              settings=budget(40, stateful_step_count=30))


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
def test_any_expiry_gets_an_answer_not_a_crash(property_resources, expires, who):
    """Finding F-API-1: 9999-12-31T23:59:59-23:59 overflowed to year 10000 in utc() and the
    gateway answered 500 (owner and agent alike), with nothing in the audit log."""
    try:
        req = ActionRequest(type="app.install", params={"app_id": "uptime-kuma"}, idempotency_key="k", expires_at=expires)
    except ValidationError:
        return  # refused by the request model: HTTP 422
    gw = Gateway(property_resources)
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
def test_idempotency_keys(property_resources, reqs):
    gw = Gateway(property_resources)
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
