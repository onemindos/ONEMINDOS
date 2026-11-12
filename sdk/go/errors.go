// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"errors"
	"fmt"
	"time"
)

// Error is a failed call: the contract §3/§12.2 error envelope plus the HTTP status. Code is
// exactly the gateway's `error` value ("network" and "unexpected_response" are the SDK's own).
// Use errors.Is(err, onemind.ErrExpired) to branch and errors.As to read the details.
type Error struct {
	Status     int
	Code       string
	Message    string
	Reason     string
	RetryAfter time.Duration
	// Action is the last state seen, for ErrAmbiguousResult.
	Action *Action
	cause  error
}

func (e *Error) Error() string {
	if e.Status == 0 {
		return fmt.Sprintf("%s: %s", e.Code, e.Message)
	}
	return fmt.Sprintf("HTTP %d %s: %s", e.Status, e.Code, e.Message)
}

func (e *Error) Unwrap() error { return e.cause }

// Is matches the sentinels below by code.
func (e *Error) Is(target error) bool {
	t, ok := target.(*Error)
	return ok && t.Status == -1 && t.Code == e.Code
}

func sentinel(code string) *Error { return &Error{Status: -1, Code: code} }

// Sentinels for errors.Is. An unknown code from a newer gateway is still an *Error with that Code.
var (
	ErrUnauthenticated    = sentinel("unauthenticated")
	ErrPermissionDenied   = sentinel("permission_denied")
	ErrNotFound           = sentinel("not_found")
	ErrStalePrecondition  = sentinel("stale_precondition")
	ErrExpired            = sentinel("expired")
	ErrConflict           = sentinel("conflict")
	ErrOutcomeUnknown     = sentinel("outcome_unknown")
	ErrRateLimited        = sentinel("rate_limited")
	ErrNetwork            = sentinel("network")
	ErrUnexpectedResponse = sentinel("unexpected_response")
	// ErrAmbiguousResult: an approve or deny was sent but the reply was lost, and reading the
	// action back could not prove this caller decided it. Never retried blindly (SDK.md §3.7).
	ErrAmbiguousResult = sentinel("ambiguous_result")
)

// Code returns the error code of err, or "" when err is not an *Error.
func Code(err error) string {
	var e *Error
	if errors.As(err, &e) {
		return e.Code
	}
	return ""
}
