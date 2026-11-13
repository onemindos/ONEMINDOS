# SPDX-License-Identifier: Apache-2.0
"""Independent wire-size oracle for the fuzz gateway's unchanged 256 KiB guard."""
import json


def payload_limit_response(response):
    if response.status_code != 413:
        return
    body = response.request.body
    if isinstance(body, str):
        body = body.encode('utf-8')
    assert isinstance(body, bytes), '413 without a measurable transmitted body'
    assert len(body) > 262144, '413 for a body within the configured byte budget'
    assert json.loads(response.content)['error'] == 'payload_too_large'
