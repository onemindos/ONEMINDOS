# SPDX-License-Identifier: Apache-2.0
"""Loaded only by the pinned Schemathesis fuzz job (test-only dependency group)."""
from schemathesis import check
from fuzz_payload_check import payload_limit_response


@check
def genuine_payload_rejection(ctx, response, case):
    payload_limit_response(response)


# Values the OpenAPI document cannot describe: a file name's Unicode rules, an opaque cursor, whether a
# subject or a date is acceptable. For these the server refuses with 422 and one of these reasons. A 422
# without a reason is a schema or model disagreement (what ST202 exists to catch) and still fails.
FILES_SEMANTIC_REFUSALS = {
    "invalid_path", "invalid_cursor", "invalid_metadata", "invalid_digest",
    "invalid_subject", "expiry_too_far", "invalid_quota",
}
SEMANTIC_PATHS = ("/v1/files", "/v1/backups", "/v1/restores", "/v1/migrate")
UNAVAILABLE_REASONS ={"backups_disabled", "target_unreachable", "agent_refused", "agent_failed"}


@check
def semantic_refusal_names_its_reason(ctx, response, case):
    meta = case.meta
    if response.status_code != 422 or meta is None or not meta.generation.mode.is_positive:
        return
    if not case.operation.path.startswith(SEMANTIC_PATHS):
        return
    reason = response.json().get("reason")
    assert reason in FILES_SEMANTIC_REFUSALS, f"schema-valid request refused 422 with reason {reason!r}"


@check
def unavailable_is_the_documented_envelope(ctx, response, case):
    """§12.2: a switched-off or unreachable backup agent answers 503 unavailable, never anything else."""
    if response.status_code != 503:
        return
    body = response.json()
    assert case.operation.path.startswith(("/v1/backups", "/v1/restores")), "503 outside the backup routes"
    assert body.get("error") == "unavailable" and body.get("reason") in UNAVAILABLE_REASONS, body
    assert body.get("retry_after_s") == 30 and response.headers.get("retry-after") == "30", body
