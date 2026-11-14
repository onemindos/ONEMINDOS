# SPDX-License-Identifier: Apache-2.0
"""Execute the pinned fuzz checks against real ASGI requests, including a faulty guard."""
import pytest

from conftest import OWNER


@pytest.mark.parametrize('method,path,parameters', [
    ('POST', '/v1/tokens', {}),
    ('PUT', '/v1/apps/{app_id}/access', {'app_id': 'uptime-kuma'}),
])
@pytest.mark.parametrize('mode', ['positive', 'negative'])
def test_schemathesis_payload_checks_execute(property_resources, monkeypatch, tmp_path,
                                              method, path, parameters, mode):
    schemathesis = pytest.importorskip('schemathesis')
    from schemathesis.config import SchemathesisConfig
    from schemathesis.core.parameters import ParameterLocation
    from schemathesis.core.failures import FailureGroup
    from schemathesis.generation.meta import (
        CaseMetadata, ComponentInfo, FuzzingPhaseData, GenerationInfo, GenerationMode, PhaseInfo, TestPhase,
    )
    from schemathesis.specs.openapi.checks import negative_data_rejection, positive_data_acceptance
    import api_fuzz_check
    from api_fuzz_hooks import genuine_payload_rejection
    from onemind_core.errors import error_response

    # Only seed discovery is replaced: use the production config generator unchanged.
    monkeypatch.setenv('OWNER_TOKEN', 'unit-owner')
    monkeypatch.setenv('AGENT_TOKEN', 'unit-agent')
    monkeypatch.setattr(api_fuzz_check, 'call', lambda gateway, token, route, *args:
                        [{'id': 'unit-app'}] if route == '/v1/apps' else {'id': 'unit-action'})
    config_path = tmp_path / 'fuzz.toml'
    assert api_fuzz_check.prepare('http://unit.invalid', config_path) == 0
    config = SchemathesisConfig.from_path(config_path)
    meta = CaseMetadata(generation=GenerationInfo(time=0, mode=GenerationMode(mode)),
                        components={ParameterLocation.BODY: ComponentInfo(GenerationMode(mode))},
                        phase=PhaseInfo(TestPhase.FUZZING, FuzzingPhaseData(None, None, None, None)))
    checks = [positive_data_acceptance if mode == 'positive' else negative_data_rejection,
              genuine_payload_rejection]
    with property_resources.example() as sample, sample.http() as client:
        schema = schemathesis.openapi.from_asgi('/openapi.json', client.app, config=config)
        operation = schema[path][method]
        large_body = ({'name': 'wire control', 'padding': 'x' * 262145} if mode == 'positive'
                      else ['x' * 262145])
        from jsonschema import Draft202012Validator
        spec = client.get('/openapi.json').json()
        body_schema = spec['paths'][path][method.lower()]['requestBody']['content']['application/json']['schema']
        validator = Draft202012Validator(dict(body_schema, components=spec['components']))
        assert validator.is_valid(large_body) == (mode == 'positive')
        case = schemathesis.Case(operation, method, path, path_parameters=parameters, headers=OWNER,
                                 body=large_body, media_type='application/json', meta=meta)
        response = case.call_and_validate(checks=checks)
        assert response.status_code == 413
        assert len(response.request.body) > 262144

        # An injected broken guard really answers 413 to a small serialized request.
        # Run the SAME framework checks: accepting 413 in ST201 must not hide this bug.
        async def false_guard(scope, receive, send):
            if scope['type'] == 'http' and scope['path'] != '/openapi.json':
                await error_response(413, 'payload_too_large', 'injected broken guard')(scope, receive, send)
            else:
                await client.app(scope, receive, send)

        faulty = schemathesis.openapi.from_asgi('/openapi.json', false_guard, config=config)
        small = schemathesis.Case(faulty[path][method], method, path, path_parameters=parameters,
                                  headers=OWNER, body={'name': 'wire control'} if mode == 'positive' else [],
                                  media_type='application/json', meta=meta.copy())
        with pytest.raises(FailureGroup, match='within the configured byte budget'):
            small.call_and_validate(checks=checks)
