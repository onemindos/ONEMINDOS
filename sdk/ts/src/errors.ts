// SPDX-License-Identifier: Apache-2.0
// Typed errors (SDK.md §3.8). `code` is exactly the gateway's `error` value; an unknown code from a
// newer gateway is a plain OneMindError with that code, never a crash.

export class OneMindError extends Error {
  readonly status: number;
  readonly code: string;
  readonly reason?: string;
  readonly retryAfterS?: number;
  constructor(status: number, code: string, message: string, extra: { reason?: string; retryAfterS?: number } = {}) {
    super(status ? `HTTP ${status} ${code}: ${message}` : `${code}: ${message}`);
    this.name = new.target.name;
    this.status = status;
    this.code = code;
    this.reason = extra.reason;
    this.retryAfterS = extra.retryAfterS;
  }
}

export class UnauthenticatedError extends OneMindError {}
export class PermissionDeniedError extends OneMindError {}
export class NotFoundError extends OneMindError {}
export class StalePreconditionError extends OneMindError {}
export class ExpiredError extends OneMindError {}
export class ConflictError extends OneMindError {}
export class OutcomeUnknownError extends OneMindError {}
export class RateLimitedError extends OneMindError {}
export class NetworkError extends OneMindError {
  readonly timedOut: boolean;
  constructor(message: string, timedOut = false) {
    super(0, "network", message);
    this.timedOut = timedOut;
  }
}
export class UnexpectedResponseError extends OneMindError {}
/** An approve or deny was sent but the reply was lost and read-back could not confirm it. */
export class AmbiguousResultError extends OneMindError {
  readonly action?: unknown;
  constructor(message: string, action?: unknown) {
    super(0, "ambiguous_result", message);
    this.action = action;
  }
}

const BY_CODE: Record<string, typeof OneMindError> = {
  unauthenticated: UnauthenticatedError,
  permission_denied: PermissionDeniedError,
  not_found: NotFoundError,
  stale_precondition: StalePreconditionError,
  expired: ExpiredError,
  conflict: ConflictError,
  outcome_unknown: OutcomeUnknownError,
  rate_limited: RateLimitedError,
  unexpected_response: UnexpectedResponseError,
};

export function errorFor(
  status: number,
  code: string,
  message: string,
  extra: { reason?: string; retryAfterS?: number } = {},
): OneMindError {
  const Cls = BY_CODE[code] ?? OneMindError;
  return new Cls(status, code, message, extra);
}
