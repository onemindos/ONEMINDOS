# SPDX-License-Identifier: Apache-2.0
"""#682 notify-read-state: unread state kept on the hub, one summary call, and private read events.

A read on one device must clear the bell on the person's other devices within 2 s. The read
endpoints already store read_at per person; what was missing is (a) one summary call a badge can
read and (b) a typed stream event for a read, sent only to that person's own streams (live and on
replay), so every client refreshes the moment it happens instead of on its next poll.
"""
import json
import time

import httpx
import pytest

from conftest import ADULT, AGENT, GUEST, OWNER
from test_contract_drift import domain_events, event_server, until_health  # noqa: F401 (fixture)
from test_notify import nclient, publish, svc  # noqa: F401 (fixture)

READ_TYPES = ('notification.read', 'notification.read_all')


def notes_for(c, people, severity='info', n=1):
    out = {}
    for pid in people:
        out[pid] = [nid for _ in range(n) for nid in svc(c)._fanout(
            [pid], severity=severity, topic='system', title='private-title', body='private-body',
            link=None, source='test', action_id=None, alert_id=None, inapp_only=True)]
    return out


def summary(c, headers):
    r = c.get('/v1/notifications/summary', headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_summary_is_the_callers_unread_state_on_the_hub(nclient, clock):
    assert summary(nclient, OWNER) == {
        'unread': 0, 'by_severity': {'info': 0, 'warning': 0, 'critical': 0},
        'latest_created_at': None, 'last_read_at': None}
    owner = notes_for(nclient, ['owner'], 'warning', n=2)['owner'] + notes_for(nclient, ['owner'], 'critical')['owner']
    notes_for(nclient, ['adult'], 'info', n=3)
    first = summary(nclient, OWNER)
    assert first['unread'] == 3 and first['by_severity'] == {'info': 0, 'warning': 2, 'critical': 1}
    assert first['latest_created_at'] and first['last_read_at'] is None
    assert summary(nclient, ADULT)['by_severity'] == {'info': 3, 'warning': 0, 'critical': 0}
    clock.advance(5)
    assert nclient.post(f'/v1/notifications/{owner[0]}/read', headers=OWNER).status_code == 200
    after = summary(nclient, OWNER)
    assert after['unread'] == 2 and after['by_severity']['warning'] == 1
    assert after['last_read_at'] and after['last_read_at'] > first['latest_created_at']
    assert nclient.post('/v1/notifications/read-all', headers=OWNER).json() == {'marked': 2}
    assert summary(nclient, OWNER)['unread'] == 0
    assert summary(nclient, ADULT)['unread'] == 3  # another person's inbox is untouched
    assert summary(nclient, GUEST)['unread'] == 0
    assert nclient.get('/v1/notifications/summary', headers=AGENT).status_code == 403  # people only
    assert nclient.get('/v1/notifications/summary').status_code == 401


def test_a_read_records_one_private_event_and_a_repeat_records_none(nclient):
    nids = notes_for(nclient, ['owner'], n=3)['owner']
    nclient.post(f'/v1/notifications/{nids[0]}/read', headers=OWNER)
    nclient.post(f'/v1/notifications/{nids[0]}/read', headers=OWNER)  # already read: no change, no event
    assert nclient.post('/v1/notifications/read-all', headers=OWNER).json() == {'marked': 2}
    assert nclient.post('/v1/notifications/read-all', headers=OWNER).json() == {'marked': 0}
    reads = [e for e in domain_events(nclient) if e['type'] in READ_TYPES]
    assert [(e['type'], e['subject'], e['data']) for e in reads] == [
        ('notification.read', {'notification_id': nids[0]}, {}),
        ('notification.read_all', {'person_id': 'owner'}, {}),
    ]
    assert all(e['actor_id'] == 'owner' for e in reads)
    assert 'private-title' not in json.dumps(reads)


@pytest.mark.parametrize('replay', [False, True])
@pytest.mark.parametrize('headers', [OWNER, ADULT, GUEST, AGENT])
def test_read_events_reach_only_the_readers_own_streams(event_server, nclient, headers, replay):
    notes = notes_for(nclient, ['owner', 'adult'], n=2)
    reader = {OWNER['Authorization']: 'owner', ADULT['Authorization']: 'adult'}.get(headers['Authorization'])

    def produce():
        nclient.post(f"/v1/notifications/{notes['owner'][0]}/read", headers=OWNER)
        nclient.post('/v1/notifications/read-all', headers=OWNER)
        nclient.post(f"/v1/notifications/{notes['adult'][1]}/read", headers=ADULT)
        publish(nclient, 'app', 'unhealthy', {'app_id': 'whoami'}, 'warning')  # end-of-test canary

    if replay:
        produce()
    with httpx.Client(base_url=event_server, timeout=5) as c:
        with c.stream('GET', '/v1/events?types=notification.*,app.*,audit.*' + ('&since_id=0' if replay else ''),
                      headers=headers) as r:
            assert r.status_code == 200
            if not replay:
                produce()
            got = until_health(r)
    reads = [(e['type'], e['subject']) for e in got if e['type'] in READ_TYPES]
    expected = {
        'owner': [('notification.read', {'notification_id': notes['owner'][0]}),
                  ('notification.read_all', {'person_id': 'owner'})],
        'adult': [('notification.read', {'notification_id': notes['adult'][1]})],
    }.get(reader, [])
    assert reads == expected
    # Audit access must not reveal another person's read either, not even as a generic audit line.
    read_seqs = {e['id'] for e in domain_events(nclient) if e['type'] in READ_TYPES}
    mine = {e['id'] for e in got if e['type'] in READ_TYPES}
    assert not [e for e in got if e['id'] in read_seqs - mine]
    assert 'private-title' not in json.dumps(got)


def test_a_read_on_one_device_reaches_the_other_within_two_seconds(event_server, nclient):
    nid = notes_for(nclient, ['adult'])['adult'][0]
    with httpx.Client(base_url=event_server, timeout=5) as c:
        with c.stream('GET', '/v1/events?types=notification.read', headers=ADULT) as r:
            assert r.status_code == 200
            started = time.monotonic()
            assert nclient.post(f'/v1/notifications/{nid}/read', headers=ADULT).status_code == 200  # "the phone"
            for line in r.iter_lines():  # "the dashboard"
                if line.startswith('data: '):
                    ev = json.loads(line[6:])
                    break
    assert ev['type'] == 'notification.read' and ev['subject'] == {'notification_id': nid}
    assert time.monotonic() - started < 2.0
    assert summary(nclient, ADULT)['unread'] == 0
