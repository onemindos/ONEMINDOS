# SPDX-License-Identifier: Apache-2.0
"""DR2 merge preservation: FILES uses its existing request and audit attribution."""
from onemind_core.eventstream import events_for_record

from files_support import (  # noqa: F401
    AGENT, OWNER, audit_events, fc, files_root, files_settings, mkdir, ok,
)
from test_files_grants import grant_body


def test_files_approval_keeps_request_identity_and_audit_actor(fc, settings):
    mkdir(fc, OWNER, 'shared', '/Media')
    request = ok(fc.post('/v1/files/grants', headers=AGENT, json=grant_body()), 202)
    assert request['state'] == 'awaiting_approval' and request['approved_by'] is None
    assert fc.post(f"/v1/files/requests/{request['id']}/approve", headers=AGENT).status_code == 403
    assert fc.get('/v1/files/list', headers=AGENT,
                  params={'root': 'shared', 'path': '/Media'}).status_code == 403
    done = ok(fc.post(f"/v1/files/requests/{request['id']}/approve", headers=OWNER))
    assert done['state'] == 'succeeded' and done['approved_by'] == 'owner'
    assert ok(fc.get(f"/v1/files/requests/{request['id']}", headers=AGENT))['approved_by'] == 'owner'
    assert fc.get('/v1/files/list', headers=AGENT,
                  params={'root': 'shared', 'path': '/Media'}).status_code == 200
    rows = [r for r in audit_events(settings) if r['event'] == 'files.request.approved']
    assert len(rows) == 1
    row = rows[0]
    assert row['principal']['id'] == 'owner'
    assert row['data']['payload']['request_id'] == request['id']
    assert row['data']['payload']['approved_by'] == 'owner'
    envelopes = events_for_record(row)
    assert len(envelopes) == 1
    assert envelopes[0]['type'] == 'audit.appended'
    assert envelopes[0]['actor_id'] == 'owner'
    assert request['id'] not in str(envelopes[0]['data'])
    # FILES has its own request ledger; do not invent a second Action for the same operation.
    assert fc.get('/v1/actions', headers=OWNER).json() == []
