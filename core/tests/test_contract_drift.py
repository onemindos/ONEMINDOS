# SPDX-License-Identifier: Apache-2.0
"""DR2-01/02/04 regressions on the merged lifecycle, not a parallel Action model."""
import asyncio
import json
import threading
import time

import httpx
import pytest
import uvicorn

from conftest import ADULT, AGENT, GUEST, OWNER, action_body
from test_devsurface_api import _free_port, _read_events
from test_notify import nclient, publish, svc
from test_identity_notify import hc
from test_identity import csrf, enrol, setup_owner
from onemind_core.auditread import iter_records
from onemind_core.eventstream import events_for_record


def domain_events(client):
    return [ev for _, rec in iter_records(client.app.state.gateway.settings.audit_path)
            for ev in events_for_record(rec) if not ev['type'].startswith('audit.')]


def test_real_alert_and_notification_producers(nclient):
    publish(nclient, 'node', 'offline', {'node_id': 'n1', 'hostname': 'box', 'age_s': 300}, 'warning')
    publish(nclient, 'node', 'offline', {'node_id': 'n1', 'hostname': 'box', 'age_s': 301}, 'warning')
    publish(nclient, 'node', 'online', {'node_id': 'n1', 'hostname': 'box'})
    evs = domain_events(nclient)
    assert [e['type'] for e in evs if e['type'].startswith('alert.')] == [
        'alert.opened', 'alert.updated', 'alert.resolved']
    notices = [e for e in evs if e['type'] == 'notification.created']
    assert notices
    assert all(svc(nclient).repo.get_notification(e['subject']['notification_id']) for e in notices)
    assert all(set(e['data']) <= {'state'} for e in evs)
    assert [int(e['id']) for e in evs] == sorted(int(e['id']) for e in evs)



@pytest.fixture
def event_server(request):
    nclient = request.getfixturevalue(getattr(request, 'param', 'nclient'))
    server = uvicorn.Server(uvicorn.Config(nclient.app, host='127.0.0.1', port=_free_port(),
                                          log_level='warning', lifespan='off'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.01)
        assert server.started
        yield f'http://127.0.0.1:{server.config.port}'
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_sse_real_delivery_ownership_replay_and_order(event_server, nclient, clock):
    # A private approval alert, followed by a shared app-health alert and per-person inbox rows.
    nclient.post('/v1/actions', headers=AGENT, json=action_body(clock))
    publish(nclient, 'app', 'unhealthy', {'app_id': 'whoami', 'reason': 'private text'}, 'warning')
    shared = next(a for a in nclient.get('/v1/alerts', headers=ADULT).json()
                  if a['type'] == 'app.unhealthy')
    adult_notices = nclient.get('/v1/notifications', headers=ADULT).json()
    assert len(adult_notices) == 1
    notice_id = adult_notices[0]['id']
    # Audit access must not turn adult streams into everybody's inbox or private approval feed.
    with httpx.Client(base_url=event_server, timeout=3) as c:
        with c.stream('GET', '/v1/events?types=alert.*,notification.*,app.*&since_id=0', headers=ADULT) as r:
            got = _read_events(r, 3)
        events = [json.loads(e['data']) for e in got]
        assert [e['type'] for e in events] == ['app.health', 'alert.opened', 'notification.created']
        assert events[0]['data'] == {'state': 'unhealthy'}
        assert events[1]['subject'] == {'alert_id': shared['id']}
        assert events[2]['subject'] == {'notification_id': notice_id}
        assert 'private text' not in json.dumps(events)
        ids = [int(e['id']) for e in got]
        assert ids == sorted(ids) and len(set(ids)) == len(ids)
        with c.stream('GET', '/v1/events?types=alert.*,notification.*,app.*',
                      headers={**ADULT, 'Last-Event-ID': str(ids[0])}) as r:
            again = _read_events(r, 2)
        assert again == got[1:]
        # since_id explicitly takes precedence over Last-Event-ID.
        with c.stream('GET', '/v1/events?types=notification.created&since_id=0',
                      headers={**ADULT, 'Last-Event-ID': str(ids[-1])}) as r:
            assert _read_events(r, 1) == [got[-1]]
        assert c.get('/v1/events').status_code == 401


@pytest.mark.parametrize('outcome', ['succeeded', 'failed', 'outcome_unknown'])
def test_app_events_follow_real_executor_outcome(nclient, clock, executor, outcome):
    install = nclient.post('/v1/actions', headers=AGENT, json=action_body(clock)).json()
    assert not [e for e in domain_events(nclient) if e['type'].startswith('app.')]
    nclient.post(f"/v1/actions/{install['id']}/approve", headers=OWNER)
    assert [e['data'] for e in domain_events(nclient) if e['type'] == 'app.status'] == [
        {'status': 'installed', 'data_kept': False}]
    restart = nclient.post('/v1/actions', headers=AGENT,
                          json=action_body(clock, type_='app.restart', key='restart')).json()
    assert not [e for e in domain_events(nclient) if e['type'] == 'app.restarted']
    executor.outcome = outcome
    response = nclient.post(f"/v1/actions/{restart['id']}/approve", headers=OWNER)
    assert response.status_code == 200 and response.json()['state'] == outcome
    evs = [e for e in domain_events(nclient) if e['subject'].get('action_id') == restart['id']]
    status = next(e for e in evs if e['type'] == 'app.status')
    assert status['data']['status'] == {'succeeded': 'installed', 'failed': 'failed',
                                       'outcome_unknown': 'unknown'}[outcome]
    assert len([e for e in evs if e['type'] == 'app.restarted']) == (outcome == 'succeeded')
    assert executor.calls == [('app.install', 'uptime-kuma'), ('app.restart', 'uptime-kuma')]


def test_approved_by_is_additive_and_not_the_denier(client, clock):
    a = client.post('/v1/actions', headers=AGENT, json=action_body(clock)).json()
    assert a['approved_by'] is None
    plan = {k: a[k] for k in ('risk', 'plan', 'plan_sha256')}
    approved = client.post(f"/v1/actions/{a['id']}/approve", headers=OWNER,
                           json={'plan_sha256': a['plan_sha256']}).json()
    assert approved['state'] == 'succeeded'
    assert approved['approved_by'] == approved['decided_by']['id'] == 'owner'
    assert approved['decided_at'] is not None
    assert {k: approved[k] for k in plan} == plan
    assert client.get(f"/v1/actions/{a['id']}", headers=OWNER).json() == approved
    b = client.post('/v1/actions', headers=AGENT,
                    json=action_body(clock, app_id='whoami', key='denied')).json()
    denied = client.post(f"/v1/actions/{b['id']}/deny", headers=OWNER).json()
    assert denied['state'] == 'cancelled' and denied['decided_by']['id'] == 'owner'
    assert denied['approved_by'] is None and denied['decided_at'] is not None


@pytest.mark.parametrize('outcome', ['succeeded', 'failed', 'outcome_unknown'])
def test_feature_approval_is_durable_before_dispatch(client, clock, outcome):
    from datetime import timedelta
    from onemind_core.actions import FeatureAction
    from onemind_core.auth import Principal
    from onemind_core.executors import ExecResult

    actions = client.app.state.actions
    observed = []

    def run(action, finish):
        stored = client.app.state.repo.get(action.id)
        observed.append((stored.state, stored.approved_by, stored.decided_by['id']))
        finish(ExecResult(outcome, 'feature result'))

    actions.register_type('backup.test', FeatureAction(risk='write', run=run))
    owner = Principal('owner', 'person', 'owner')
    pending, _ = actions.request_feature(owner, 'backup.test', {}, idempotency_key='feature-approval',
                                         expires_at=clock() + timedelta(minutes=5))
    assert pending['approved_by'] is None
    result = client.post(f"/v1/actions/{pending['id']}/approve", headers=OWNER)
    assert result.status_code == 200 and result.json()['state'] == outcome
    assert observed == [('dispatched', 'owner', 'owner')]
    assert result.json()['approved_by'] == 'owner'
    assert client.get(f"/v1/actions/{pending['id']}", headers=OWNER).json()['approved_by'] == 'owner'


@pytest.mark.parametrize('approval', ['person', 'policy'])
@pytest.mark.parametrize('outcome', ['succeeded', 'failed', 'outcome_unknown'])
def test_merged_app_approval_is_atomic_and_survives_outcome(client, clock, executor, monkeypatch, approval, outcome):
    """Main's owner-set policies retain the same durable acceptance boundary as manual approval."""
    from test_automation import install, policy

    install(client, clock)
    expected = 'owner'
    if approval == 'policy':
        response = policy(client, clock, requested_by=('agent:hermes',))
        assert response.status_code == 201
        expected = f"policy:{response.json()['id']}@1"
    repo = client.app.state.repo
    accept = repo.accept_and_claim
    run = executor.run
    observed = []
    accepted_ids = []
    dispatched = []

    def observe_accept(action_id, *args, **kwargs):
        result = accept(action_id, *args, **kwargs)
        stored = repo.get(action_id)
        observed.append((stored.state, stored.approved_by, stored.decided_by['id']))
        assert stored.state == 'accepted' and stored.approved_by == expected
        accepted_ids.append(action_id)
        return result

    def observe_dispatch(*args, **kwargs):
        assert len(accepted_ids) == 1
        stored = repo.get(accepted_ids[0])
        assert stored.state == 'dispatched' and stored.approved_by == expected
        assert observed == [('accepted', expected, expected)]
        dispatched.append(stored.id)
        return run(*args, **kwargs)

    monkeypatch.setattr(repo, 'accept_and_claim', observe_accept)
    monkeypatch.setattr(executor, 'run', observe_dispatch)
    executor.outcome = outcome
    response = client.post('/v1/actions', headers=AGENT,
                           json=action_body(clock, app_id='whoami', type_='app.remove', key='approval-merge'))
    assert response.status_code == 201
    action = response.json()
    if approval == 'person':
        assert action['state'] == 'awaiting_approval' and action['approved_by'] is None
        assert client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
        response = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
        assert response.status_code == 200
        action = response.json()
    assert observed == [('accepted', expected, expected)]
    assert dispatched == [action['id']]
    assert action['state'] == outcome and action['approved_by'] == expected
    assert action['decided_by']['id'] == expected
    durable = client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()
    assert durable['approved_by'] == expected and durable['state'] == outcome


@pytest.mark.parametrize('state', ['accepted', 'dispatched', 'succeeded', 'failed', 'outcome_unknown'])
def test_historical_decider_is_not_approval_proof(client, clock, state):
    from onemind_core.ledger import Action
    a = Action('old', 'app.install', {}, state, {}, 'old', clock(), clock(), clock(),
               decided_by={'id': 'someone', 'kind': 'person', 'role': 'owner'})
    assert a.to_json()['approved_by'] is None


@pytest.mark.parametrize('outcome', ['succeeded', 'failed', 'outcome_unknown'])
def test_durable_approval_survives_outcome(client, clock, executor, outcome):
    executor.outcome = outcome
    a = client.post('/v1/actions', headers=AGENT, json=action_body(clock)).json()
    result = client.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).json()
    assert result['state'] == outcome
    assert result['approved_by'] == 'owner'
    records = [r for _, r in iter_records(client.app.state.gateway.settings.audit_path)
               if r['event'] == 'action.approved' and r.get('action_id') == a['id']]
    assert records[0]['data']['approved_by'] == result['approved_by']
    assert client.get(f"/v1/actions/{a['id']}", headers=OWNER).json()['approved_by'] == 'owner'


def until_health(response):
    out = []
    for line in response.iter_lines():
        if line.startswith('data: '):
            ev = json.loads(line[6:])
            out.append(ev)
            if ev['type'] == 'app.health':
                return out
    raise AssertionError('health canary missing')


@pytest.mark.parametrize('headers', [OWNER, ADULT, AGENT])
@pytest.mark.parametrize('replay', [False, True])
def test_sse_private_inbox_and_generic_audit_do_not_leak(event_server, nclient, headers, replay):
    def produce():
        svc(nclient)._fanout(['adult'], severity='info', topic='system', title='private-title',
                             body='private-body', link=None, source='test', action_id=None,
                             alert_id=None, inapp_only=True)
        publish(nclient, 'app', 'unhealthy', {'app_id': 'whoami'}, 'warning')
    if replay:
        produce()
    with httpx.Client(base_url=event_server, timeout=3) as c:
        with c.stream('GET', '/v1/events?types=notification.*,app.*,audit.*' +
                      ('&since_id=0' if replay else ''), headers=headers) as r:
            assert r.status_code == 200
            if not replay:
                produce()
            got = until_health(r)
    ids = {r['seq'] for _, r in iter_records(nclient.app.state.gateway.settings.audit_path)
           if r['event'] == 'notification.created'}
    notice_events = [e for e in got if e['type'] == 'notification.created']
    assert len(notice_events) == (headers == ADULT)
    if headers != ADULT:
        assert not any(int(e['id']) in ids for e in got)
    assert 'private-title' not in json.dumps(got) and 'private-body' not in json.dumps(got)
    assert len({e['id'] for e in got}) == len(got)


@pytest.mark.parametrize('event_server', ['hc'], indirect=True)
@pytest.mark.parametrize('read_scopes', [[], ['audit:read:own', 'actions:read:own']])
def test_sse_household_scope_and_role_refusal(event_server, hc, read_scopes):
    setup_owner(hc)
    guest, child = enrol(hc, 'guest', 'visitor'), enrol(hc, 'child', 'junior')
    token = hc.post('/v1/tokens', headers=csrf(hc),
                    json={'name': 'stream-only', 'scopes': ['events:read', *read_scopes]}).json()['one_time']['token']
    publish(hc, 'app', 'unhealthy', {'app_id': 'whoami'}, 'warning')
    with httpx.Client(base_url=event_server, timeout=1) as c:
        for person in (guest, child):
            with c.stream('GET', '/v1/events', cookies=dict(person.cookies)) as r:
                assert r.status_code == 403
        with c.stream('GET', '/v1/events?since_id=0&types=app.*,alert.*,notification.*,audit.*',
                      headers={'Authorization': 'Bearer ' + token}) as r:
            assert r.status_code == 200
            # No resource-read scopes: not even an audit alias may disclose resource activity.
            with pytest.raises(httpx.ReadTimeout):
                _read_events(r, 1)


def test_approval_upgrade_does_not_infer_historical_facts(tmp_path):
    from sqlalchemy import create_engine, text
    from onemind_core.store import _core_v3
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as c:
        c.execute(text('CREATE TABLE actions (id TEXT, state TEXT, decided_by JSON)'))
        c.execute(text("INSERT INTO actions VALUES ('old', 'failed', '{\"id\":\"owner\"}')"))
        _core_v3(c)
        _core_v3(c)
        assert c.execute(text('SELECT approved_by FROM actions')).scalar() is None
    engine.dispose()


def test_sse_manual_alert_transitions_and_reconnect(event_server, nclient):
    publish(nclient, 'node', 'offline', {'node_id': 'manual', 'age_s': 300}, 'warning')
    alert = nclient.get('/v1/alerts', headers=OWNER).json()[0]
    assert nclient.post(f"/v1/alerts/{alert['id']}/ack", headers=OWNER).status_code == 200
    publish(nclient, 'node', 'online', {'node_id': 'manual'})
    with httpx.Client(base_url=event_server, timeout=3) as c:
        with c.stream('GET', '/v1/events?types=alert.*&since_id=0', headers=OWNER) as r:
            got = _read_events(r, 3)
        assert [e['event'] for e in got] == ['alert.opened', 'alert.updated', 'alert.resolved']
        for i in range(2):
            with c.stream('GET', '/v1/events?types=alert.*',
                          headers={**OWNER, 'Last-Event-ID': got[i]['id']}) as r:
                assert _read_events(r, 2-i) == got[i+1:]


def test_sse_app_filter_applies_to_live_and_replay(event_server, nclient):
    nclient.app.state.gateway.app_filters.append(lambda request, p, app_id: app_id != 'whoami')
    for replay in (False, True):
        def produce():
            publish(nclient, 'app', 'unhealthy', {'app_id': 'whoami'}, 'warning')
            publish(nclient, 'app', 'unhealthy', {'app_id': 'uptime-kuma'}, 'warning')
        if replay:
            produce()
        with httpx.Client(base_url=event_server, timeout=3) as c:
            with c.stream('GET', '/v1/events?types=app.*,audit.*' +
                          ('&since_id=0' if replay else ''), headers=OWNER) as r:
                if not replay:
                    produce()
                got = until_health(r)
        assert got[-1]['subject'] == {'app_id': 'uptime-kuma'}
        hidden = {str(r['seq']) for _, r in iter_records(nclient.app.state.gateway.settings.audit_path)
                  if r['event'] == 'app.unhealthy' and r['data']['payload']['app_id'] == 'whoami'}
        assert not any(e['id'] in hidden for e in got)


@pytest.fixture
def progress_client(settings, clock):
    from conftest import make_client
    with make_client(settings, clock) as c:
        yield c


@pytest.mark.parametrize('event_server', ['progress_client'], indirect=True)
def test_sse_bridges_existing_progress(event_server, progress_client, clock):
    a = progress_client.post('/v1/actions', headers=AGENT, json=action_body(clock)).json()
    assert progress_client.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).status_code == 200
    with httpx.Client(base_url=event_server, timeout=3) as c:
        with c.stream('GET', '/v1/events?types=action.progress&since_id=0', headers=OWNER) as r:
            got = _read_events(r, 1)
    ev = json.loads(got[0]['data'])
    assert ev['subject'] == {'action_id': a['id'], 'app_id': 'uptime-kuma'}
    assert set(ev['data']) == {'step', 'pct'}


def test_unfiltered_agent_alert_audience_and_private_refusal(event_server, nclient, clock):
    a = nclient.post('/v1/actions', headers=OWNER, json=action_body(clock)).json()
    public = nclient.get('/v1/alerts', headers=AGENT).json()[0]
    assert public['type'] == 'approval.requested'  # existing REST permits owner-addressed system alerts
    publish(nclient, 'node', 'offline', {'node_id': 'private', 'age_s': 300}, 'warning')
    private = next(r for r in svc(nclient).repo.list_alerts(None) if r.type == 'node.offline')
    private.audience_json = json.dumps({'persons': ['adult'], 'roles': []})
    svc(nclient).repo.save_alert(private)
    svc(nclient)._fanout(['adult'], severity='info', topic='system', title='private', body='private',
                         link=None, source='test', action_id=None, alert_id=None, inapp_only=True)
    publish(nclient, 'app', 'unhealthy', {'app_id': 'whoami'}, 'warning')
    with httpx.Client(base_url=event_server, timeout=3) as c:
        with c.stream('GET', '/v1/events?since_id=0', headers=AGENT) as r:
            got = until_health(r)
    assert any(e['type'] == 'alert.opened' and e['subject'] == {'alert_id': public['id']} for e in got)
    assert not any(e['type'].startswith(('audit.', 'notification.', 'action.')) for e in got)
    assert private.id not in json.dumps(got) and a['id'] not in json.dumps(got)


def test_automatic_and_manual_audit_actor_are_explicit(nclient):
    publish(nclient, 'node', 'offline', {'node_id': 'actor', 'age_s': 300}, 'warning')
    alert = nclient.get('/v1/alerts', headers=OWNER).json()[0]
    nclient.post(f"/v1/alerts/{alert['id']}/ack", headers=OWNER)
    publish(nclient, 'node', 'online', {'node_id': 'actor'})
    rows = [r for _, r in iter_records(nclient.app.state.gateway.settings.audit_path)
            if r['event'].startswith('alert.')]
    assert [r['data']['payload']['by'] for r in rows] == [None, 'owner', None]
    assert all('by' not in e['data'] for r in rows for e in events_for_record(r))


@pytest.mark.parametrize('kind,role', [('agent', 'agent'), ('plugin', 'agent'), ('person', 'guest'), ('person', 'child')])
@pytest.mark.parametrize('event', ['app.status', 'app.restarted'])
def test_domain_action_metadata_requires_action_visibility(clock, kind, role, event):
    from pathlib import Path
    from onemind_core.auth import Principal
    from onemind_core.eventstream import EventStream
    stream = EventStream(Path('unused'), lambda: [], lambda pid: {'mine'}, clock)
    principal = Principal('reader', kind, role)
    check = stream._allowed(principal, lambda ev: True)
    ev = events_for_record({'seq': 1, 'event': event, 'ts': 't', 'action_id': 'foreign',
                            'data': {'app_id': 'whoami', 'status': 'installed'}})[0]
    assert not check(ev)
    ev['subject']['action_id'] = 'mine'
    assert check(ev) == (kind == 'agent')


@pytest.mark.parametrize('replay', [False, True])
def test_sse_app_outcomes_do_not_leak_foreign_action_ids(event_server, nclient, clock, replay):
    foreign, own = [], []
    minted = nclient.post('/v1/tokens', headers=OWNER, json={
        'name': 'other-agent', 'principal': {'kind': 'agent', 'id': 'agent:other'},
        'scopes': ['actions:request', 'actions:read:own', 'events:read', 'apps:read']})
    assert minted.status_code == 201, minted.text
    other_agent = {'Authorization': 'Bearer ' + minted.json()['one_time']['token']}
    def produce():
        for who, type_, key, bucket in [(OWNER, 'app.install', 'foreign-install', foreign),
                                         (OWNER, 'app.restart', 'foreign-restart', foreign),
                                         (other_agent, 'app.restart', 'other-agent-restart', foreign),
                                         (AGENT, 'app.restart', 'mine-restart', own)]:
            a = nclient.post('/v1/actions', headers=who,
                             json=action_body(clock, type_=type_, key=key)).json()
            bucket.append(a['id'])
            approved = nclient.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
            assert approved.status_code == 200 and approved.json()['state'] == 'succeeded'
        publish(nclient, 'app', 'unhealthy', {'app_id': 'whoami'}, 'warning')
    if replay:
        produce()
    with httpx.Client(base_url=event_server, timeout=5) as c:
        with c.stream('GET', '/v1/events?types=app.*,audit.*' +
                      ('&since_id=0' if replay else ''), headers=AGENT) as r:
            assert r.status_code == 200
            if not replay:
                produce()
            got = until_health(r)
    encoded = json.dumps(got)
    assert all(aid not in encoded for aid in foreign)
    mine = [e for e in got if e['subject'].get('action_id') == own[0]]
    assert [e['type'] for e in mine] == ['app.status', 'app.restarted']
    assert got[-1]['type'] == 'app.health' and 'action_id' not in got[-1]['subject']
    assert not any(e['type'].startswith('audit.') for e in got)
    assert len({e['id'] for e in got}) == len(got)


@pytest.mark.parametrize('event_server', ['hc'], indirect=True)
@pytest.mark.parametrize('action_read', [False, True])
@pytest.mark.parametrize('types', ['app.*,audit.*', 'audit.*'])
def test_sse_app_action_scope_is_required_even_for_audit_fallback(event_server, hc, clock, action_read, types):
    setup_owner(hc)
    scopes = ['events:read', 'apps:read', 'audit:read'] + (['actions:read'] if action_read else [])
    minted = hc.post('/v1/tokens', headers=csrf(hc), json={'name': 'app-reader', 'scopes': scopes})
    assert minted.status_code == 201
    headers = {'Authorization': 'Bearer ' + minted.json()['one_time']['token']}
    a = hc.post('/v1/actions', headers=OWNER, json=action_body(clock)).json()
    assert hc.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).status_code == 200
    publish(hc, 'app', 'unhealthy', {'app_id': 'whoami'}, 'warning')
    records = [r for _, r in iter_records(hc.app.state.gateway.settings.audit_path)]
    final_cursor = str(next(r['seq'] for r in reversed(records) if r['event'] == 'app.unhealthy'))
    outcome_cursor = str(next(r['seq'] for r in records if r['event'] == 'app.status'))
    with httpx.Client(base_url=event_server, timeout=3) as c:
        with c.stream('GET', '/v1/events?since_id=0&types=' + types, headers=headers) as r:
            got = []
            for line in r.iter_lines():
                if line.startswith('data: '):
                    ev = json.loads(line[6:])
                    got.append(ev)
                    if ev['id'] == final_cursor:
                        break
    assert got[-1]['id'] == final_cursor  # safe health remains visible without action-read
    assert any(e['id'] == outcome_cursor for e in got) == action_read
    if not action_read:
        assert a['id'] not in json.dumps(got)


def test_plugin_principal_cannot_mint_a_stream_credential(nclient):
    r = nclient.post('/v1/tokens', headers=OWNER, json={
        'name': 'unsupported-plugin', 'principal': {'kind': 'plugin', 'id': 'plugin:other'},
        'scopes': ['events:read', 'apps:read', 'actions:read:own']})
    assert r.status_code == 422
