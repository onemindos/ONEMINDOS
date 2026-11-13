# SPDX-License-Identifier: Apache-2.0
"""Independent wire-size oracle for the fuzz gateway's unchanged 256 KiB guard."""
import json

# A 413 about something the request declares (an upload's size) or the disk, not the size of the body.
DECLARED_LIMITS = {"upload_too_large", "chunk_too_large", "quota_exceeded", "insufficient_space"}


def payload_limit_response(response):
    if response.status_code != 413:
        return
    body_json = json.loads(response.content)
    if body_json.get("reason") in DECLARED_LIMITS:
        assert body_json["error"] == "payload_too_large", body_json
        return
    body = response.request.body
    if isinstance(body, str):
        body = body.encode('utf-8')
    assert isinstance(body, bytes), '413 without a measurable transmitted body'
    assert len(body) > 262144, '413 for a body within the configured byte budget'
    assert body_json['error'] == 'payload_too_large'
