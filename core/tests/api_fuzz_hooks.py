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
    "invalid_subject", "expiry_too_far", "invalid_quota", "invalid_kubeconfig",
    "invalid_settings", "confirm_mismatch", "invalid_root", "invalid_request",
    # Judged against the clock, the hub's stored chunks, the time zone database or other items in the
    # same list. A schema cannot practically express these (generators do not follow them). Tests:
    # test_fuzz_landing_regressions.py for invalid_scopes and bad_quick_add, test_files_shares.py for
    # invalid_expiry, test_sync_transfer.py for invalid_manifest, test_home.py for unknown_item.
    "invalid_expiry",    # files shares: between 5 minutes and 30 days from now
    "invalid_manifest",  # sync commit: the chunk sizes add up to the file size, a stored manifest is whole records
                         # (NOT the chunks-or-manifest rule: that is in the schema as a oneOf)
    "invalid_scopes",    # app passwords: each space (home, shared) at most once (expressible with contains +
                         # maxContains, but generators follow that poorly)
    "bad_quick_add",     # work quick-add: the free-text grammar and a known time zone
    "unknown_item",      # home: an item or default app this person can see (installed and shared to them)
}
UNAVAILABLE_REASONS ={"backups_disabled", "target_unreachable", "agent_refused", "agent_failed"}


@check
def semantic_refusal_names_its_reason(ctx, response, case):
    meta = case.meta
    if response.status_code != 422 or meta is None or not meta.generation.mode.is_positive:
        return
    reason = response.json().get("reason")
    # Only sync.commit verifies the declared file digest against the assembled bytes.
    if reason == "hash_mismatch" and case.operation.path == "/v1/sync/commit" and case.operation.method.lower() == "post":
        return
    assert reason in FILES_SEMANTIC_REFUSALS, f"schema-valid request refused 422 with reason {reason!r}"


@check
def unavailable_is_the_documented_envelope(ctx, response, case):
    """§12.2: a switched-off or unreachable backup agent answers 503 unavailable, never anything else."""
    if response.status_code != 503:
        return
    body = response.json()
    assert case.operation.path.startswith(("/v1/backups", "/v1/restores", "/v1/onboarding/restore")), "503 outside the backup routes"
    assert body.get("error") == "unavailable" and body.get("reason") in UNAVAILABLE_REASONS, body
    retry_after = response.headers.get("retry-after")
    assert body.get("retry_after_s") == 30 and retry_after in ("30", ["30"]), (body, retry_after)
