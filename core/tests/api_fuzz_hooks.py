# SPDX-License-Identifier: Apache-2.0
"""Loaded only by the pinned Schemathesis fuzz job (test-only dependency group)."""
from schemathesis import check
from fuzz_payload_check import payload_limit_response


@check
def genuine_payload_rejection(ctx, response, case):
    payload_limit_response(response)
