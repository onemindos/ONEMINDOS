// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"errors"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// Exit codes (CLI.md §4.2). Public interface: a number is never reused for another meaning.
const (
	ExitOK               = 0
	ExitError            = 1
	ExitUsage            = 2
	ExitUnauthenticated  = 3
	ExitPermissionDenied = 4
	ExitNotFound         = 5
	ExitConflict         = 6
	ExitUnreachable      = 7
	ExitVerifyFailed     = 8
	ExitPending          = 9
	ExitRefused          = 10
	ExitActionFailed     = 11
	ExitOutcomeUnknown   = 12
	ExitTooManyRequests  = 13
	ExitUnsupported      = 14
)

// exitError carries an explicit exit code and its name.
type exitError struct {
	code int
	name string
	msg  string
}

func (e *exitError) Error() string { return e.msg }

func exitWith(code int, name, msg string) error { return &exitError{code, name, msg} }

// exitFor maps any error to (exit code, error name for --json).
func exitFor(err error) (int, string) {
	var ee *exitError
	if errors.As(err, &ee) {
		return ee.code, ee.name
	}
	var ue *usageError
	if errors.As(err, &ue) {
		return ExitUsage, "usage"
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return ExitUnreachable, "network"
	}
	switch onemind.Code(err) {
	case "unauthenticated":
		return ExitUnauthenticated, "unauthenticated"
	case "permission_denied":
		return ExitPermissionDenied, "permission_denied"
	case "not_found":
		return ExitNotFound, "not_found"
	case "conflict", "stale_precondition", "expired":
		return ExitConflict, onemind.Code(err)
	case "network":
		return ExitUnreachable, "network"
	case "rate_limited":
		return ExitTooManyRequests, "rate_limited"
	case "outcome_unknown":
		return ExitOutcomeUnknown, "outcome_unknown"
	case "":
		return ExitError, "error"
	}
	return ExitError, onemind.Code(err)
}

// exitForState maps a terminal action state to an exit code (for --wait and the owner flow).
func exitForState(state string) error {
	switch state {
	case "succeeded":
		return nil
	case "cancelled", "expired":
		return exitWith(ExitRefused, "refused", "the action ended "+state)
	case "failed":
		return exitWith(ExitActionFailed, "action_failed", "the action failed")
	case "outcome_unknown":
		return exitWith(ExitOutcomeUnknown, "outcome_unknown", "the action's outcome is unknown; check the box")
	case "awaiting_approval", "requested":
		return exitWith(ExitPending, "pending", "still waiting for approval")
	}
	return exitWith(ExitError, "error", "the action is "+state)
}
