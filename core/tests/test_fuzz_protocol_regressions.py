# SPDX-License-Identifier: Apache-2.0
"""Protocol regressions reproduced from the real API fuzz report, not exemptions."""
import json

import pytest
from jsonschema import Draft202012Validator, ValidationError

from onemind_core.eventstream import events_for_record, sse
from conftest import OWNER


def test_fuzz_payload_oracle_rejects_false_413_and_accepts_real_overflow():
    from types import SimpleNamespace
    from fuzz_payload_check import payload_limit_response
    def response(body):
        return SimpleNamespace(status_code=413, request=SimpleNamespace(body=body),
                               content=b'{"error":"payload_too_large"}')
    payload_limit_response(response(b'x' * 262145))
    for body in (b'', b'x' * 262144, 'x' * 262144):
        with pytest.raises(AssertionError, match='within the configured byte budget'):
            payload_limit_response(response(body))



def test_payload_status_adaptation_only_adds_413_for_reproduced_operations(monkeypatch, tmp_path):
    """A config-generation unit control, not fabricated HTTP/backend evidence."""
    import tomllib
    import api_fuzz_check

    monkeypatch.setenv('OWNER_TOKEN', 'unit-owner')
    monkeypatch.setenv('AGENT_TOKEN', 'unit-agent')
    monkeypatch.setattr(api_fuzz_check, 'call', lambda gateway, token, path, *args:
                        [{'id': 'unit-app'}] if path == '/v1/apps' else {'id': 'unit-action'})
    config = tmp_path / 'fuzz.toml'
    assert api_fuzz_check.prepare('http://unit.invalid', config) == 0
    operations = tomllib.loads(config.read_text())['operations']
    adapted = {(op.get('include-path'), op.get('include-method')): op['checks']
               for op in operations if 'checks' in op}
    assert set(adapted) == {('/v1/tokens', 'POST'), ('/v1/apps/{app_id}/access', 'PUT')}
    negative = {400, 401, 403, 404, 405, 406, 409, 415, 422, 428, 429, '5xx'}
    positive = {'2xx', '3xx', 401, 403, 404, 409, 429, '5xx'}
    for checks in adapted.values():
        assert set(checks['negative_data_rejection']['expected-statuses']) == negative | {413}
        assert set(checks['positive_data_acceptance']['expected-statuses']) == positive | {413}


@pytest.mark.parametrize('method', ['GET', 'DELETE'])
def test_mcp_transport_authentication_precedes_method_refusal(property_resources, method):
    from conftest import AGENT
    with property_resources.example() as sample, sample.http() as client:
        assert client.request(method, '/mcp').status_code == 401
        assert client.request(method, '/mcp', headers=AGENT).status_code == 405


@pytest.mark.parametrize('method,path', [
    ('POST', '/v1/tokens'), ('PUT', '/v1/apps/uptime-kuma/access'),
])
def test_body_limit_is_documented_and_not_a_blanket_refusal(property_resources, method, path):
    with property_resources.example() as sample, sample.http() as client:
        spec_path = '/v1/apps/{app_id}/access' if method == 'PUT' else path
        responses = client.get('/openapi.json').json()['paths'][spec_path][method.lower()]['responses']
        assert '413' in responses
        response = client.request(method, path, content=b'x' * 262145, headers=OWNER)
        assert response.status_code == 413 and response.json()['error'] == 'payload_too_large'
        # An ordinary small malformed body still reaches validation, not the body guard.
        assert client.request(method, path, content=b'{', headers=OWNER).status_code == 422


@pytest.mark.parametrize('value,valid', [
    ('1', True), ('300s', True), ('30m', True), ('24h', True),
    ('2026-11-11T21:00:00Z', True), ('0' * 40, False), ('0', False),
    ('25h', False), ('86401', False), ('not-a-time', False),
])
def test_metrics_window_syntax_and_runtime_bounds(property_resources, value, valid):
    with property_resources.example() as sample, sample.http() as client:
        parameters = client.get('/openapi.json').json()['paths']['/v1/nodes/{node_id}/metrics']['get']['parameters']
        schema = next(p['schema'] for p in parameters if p['name'] == 'window')
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        assert validator.is_valid(value) == valid
        response = client.get('/v1/nodes/missing/metrics', params={'window': value}, headers=OWNER)
        assert response.status_code == (404 if valid else 422)



@pytest.mark.parametrize('name', ['since', 'until'])
def test_audit_timestamp_schema_matches_positive_and_invalid_inputs(property_resources, name):
    with property_resources.example() as sample, sample.http() as client:
        parameters = client.get('/openapi.json').json()['paths']['/v1/audit/events']['get']['parameters']
        schema = next(p['schema'] for p in parameters if p['name'] == name)
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        valid = '2026-11-11T21:00:00Z'
        validator.validate(valid)
        assert client.get('/v1/audit/events', params={name: valid}, headers=OWNER).status_code == 200
        invalid = '0' * 40
        with pytest.raises(ValidationError):
            validator.validate(invalid)
        assert client.get('/v1/audit/events', params={name: invalid}, headers=OWNER).status_code == 422



@pytest.mark.parametrize('path,allowed', [
    ('/v1/auth/passkeys/register', {'POST'}),
    ('/v1/notifications/read-all', {'POST'}),
    ('/v1/notifications/send', {'POST'}),
    ('/v1/actions', {'GET', 'POST'}),
])
def test_static_resources_do_not_inherit_parameter_sibling_methods(property_resources, path, allowed):
    with property_resources.example() as sample, sample.http() as client:
        response = client.options(path, headers=OWNER)
        assert response.status_code == 405
        assert set(response.headers['allow'].split(', ')) == allowed
        # Every nonadvertised method must actually refuse, not reach a sibling template.
        for method in {'GET', 'POST', 'DELETE', 'PATCH'} - allowed:
            assert client.request(method, path, headers=OWNER).status_code == 405



def test_sse_schema_describes_the_parsed_frame_and_embedded_envelope(property_resources):
    with property_resources.example() as sample, sample.http() as client:
        media = client.get('/openapi.json').json()['paths']['/v1/events']['get']['responses']['200']['content']
    assert 'text/event-stream' in media
    schema = media['text/event-stream']['schema']
    event = events_for_record({'seq': 1, 'event': 'action.requested', 'ts': '2026-11-12T00:00:00Z',
                               'action_id': 'a', 'principal': {'id': 'agent'}})[0]
    # Parse the actual production encoder's bytes into standard SSE fields.
    frame = dict(line.split(': ', 1) for line in sse(event).decode().splitlines() if line)
    Draft202012Validator(schema).validate(frame)
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate({'data': frame['data']})
    data_schema = schema['properties']['data']['contentSchema']
    Draft202012Validator(data_schema).validate(json.loads(frame['data']))
    with pytest.raises(ValidationError):
        Draft202012Validator(data_schema).validate({'schema': 'wrong'})
