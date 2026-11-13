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

