# SPDX-License-Identifier: Apache-2.0
"""Replay Home ST201 through pinned Schemathesis, not just TOML assertions."""
import copy

import pytest
from jsonschema import Draft202012Validator

from conftest import OWNER


@pytest.mark.parametrize('stale_tag', ['', '"stale"'])
def test_negative_home_precondition_is_rejection(client, monkeypatch, tmp_path, stale_tag):
    schemathesis = pytest.importorskip('schemathesis')
    from schemathesis.config import SchemathesisConfig
    from schemathesis.core.failures import FailureGroup
    from schemathesis.core.parameters import ParameterLocation
    from schemathesis.generation.meta import (
        CaseMetadata, ComponentInfo, FuzzingPhaseData, GenerationInfo, GenerationMode, PhaseInfo, TestPhase,
    )
    from schemathesis.specs.openapi.checks import negative_data_rejection
    import api_fuzz_check

    # Replace only catalog/action seed discovery; HTTP requests below hit the real gateway.
    monkeypatch.setenv('OWNER_TOKEN', 'unit-owner')
    monkeypatch.setenv('AGENT_TOKEN', 'unit-agent')
    monkeypatch.setattr(api_fuzz_check, 'call', lambda gateway, token, path, *args:
                        [{'id': 'unit-app'}] if path == '/v1/apps' else {'id': 'unit-action'})
    config_path = tmp_path / 'fuzz.toml'
    assert api_fuzz_check.prepare('http://unit.invalid', config_path) == 0
    config = SchemathesisConfig.from_path(config_path)
    schema = schemathesis.openapi.from_asgi('/openapi.json', client.app, config=config)
    path = '/v1/me/home'
    operation = schema[path]['PUT']
    before = client.get(path, headers=OWNER)
    body = copy.deepcopy(before.json())
    # The exact CI mutation: JSON Schema rejects integer 0 as a boolean, while
    # Pydantic coerces it. A stale If-Match still refuses the write before save.
    body['appearance']['reduce_transparency'] = 0
    spec = client.get('/openapi.json').json()
    body_schema = spec['paths'][path]['put']['requestBody']['content']['application/json']['schema']
    validator = Draft202012Validator(dict(body_schema, components=spec['components']))
    assert not validator.is_valid(body)
    meta = CaseMetadata(generation=GenerationInfo(time=0, mode=GenerationMode.NEGATIVE),
                        components={ParameterLocation.BODY: ComponentInfo(GenerationMode.NEGATIVE)},
                        phase=PhaseInfo(TestPhase.FUZZING, FuzzingPhaseData(None, None, None, None)))

    def case(op, headers):
        return schemathesis.Case(op, 'PUT', path, headers={**OWNER, **headers}, body=body,
                                 media_type='application/json', meta=meta.copy())

    response = case(operation, {'If-Match': stale_tag}).call_and_validate(checks=[negative_data_rejection])
    assert response.status_code == 412
    assert response.json()['reason'] == 'etag_mismatch'
    after = client.get(path, headers=OWNER)
    assert after.json() == before.json() and after.headers['etag'] == before.headers['etag']
    # Missing-header behavior remains 428, not an accepted write.
    assert case(operation, {}).call_and_validate(checks=[negative_data_rejection]).status_code == 428

    # Real framework operation matching: no new 412 allowance on Home GET or
    # any unrelated operation (the existing tus family retains its own rule).
    for result in schema.get_all_operations():
        op = result.ok()
        statuses = schema.config.operations.get_for_operation(op).checks.negative_data_rejection.expected_statuses
        if op.label == 'PUT /v1/me/home' or op.path.startswith('/v1/files/uploads'):
            assert '412' in statuses
        else:
            assert '412' not in statuses

    # Negative control: an injected server that incorrectly accepts this same
    # invalid request MUST still fail ST201. No framework check is disabled.
    async def accepts_invalid(scope, receive, send):
        if scope['type'] == 'http' and scope['path'] == path and scope['method'] == 'PUT':
            from starlette.responses import JSONResponse
            await JSONResponse(body)(scope, receive, send)
        else:
            await client.app(scope, receive, send)

    faulty = schemathesis.openapi.from_asgi('/openapi.json', accepts_invalid, config=config)
    with pytest.raises(FailureGroup, match='Schema-violating request accepted'):
        case(faulty[path]['PUT'], {'If-Match': stale_tag}).call_and_validate(checks=[negative_data_rejection])
