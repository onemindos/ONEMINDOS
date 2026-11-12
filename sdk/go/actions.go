// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

// DefaultExpiry is how long a request waits for the owner unless the caller says otherwise.
const DefaultExpiry = 24 * time.Hour

// ActionsService is /v1/actions: request, list, get, approve, deny, and a Wait helper.
type ActionsService struct{ c *Client }

// ActionRequest is what a caller asks for. The SDK fills the idempotency key and expiry.
type ActionRequest struct {
	Type  string
	AppID string
	// ExpiresIn defaults to 24 h and is counted on the hub's clock.
	ExpiresIn time.Duration
	// IdempotencyKey defaults to a fresh UUIDv4, reused on every retry of this one call.
	IdempotencyKey string
}

type actionBody struct {
	Type           string            `json:"type"`
	Params         map[string]string `json:"params"`
	IdempotencyKey string            `json:"idempotency_key"`
	ExpiresAt      string            `json:"expires_at"`
}

// NewIdempotencyKey returns a random UUIDv4.
func NewIdempotencyKey() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// Request is operation actions.create: it files the action in awaiting_approval. It is retried
// safely with one idempotency key: a replay returns the original action.
func (s *ActionsService) Request(ctx context.Context, r ActionRequest) (*Action, error) {
	if r.ExpiresIn <= 0 {
		r.ExpiresIn = DefaultExpiry
	}
	if r.IdempotencyKey == "" {
		r.IdempotencyKey = NewIdempotencyKey()
	}
	if _, err := s.c.Instance.Get(ctx); err != nil { // learn the hub clock first (and fail fast)
		return nil, err
	}
	body := actionBody{
		Type: r.Type, Params: map[string]string{"app_id": r.AppID}, IdempotencyKey: r.IdempotencyKey,
		ExpiresAt: s.c.HubNow().Add(r.ExpiresIn).UTC().Format(time.RFC3339),
	}
	var a Action
	_, err := s.c.do(ctx, request{method: http.MethodPost, path: "/v1/actions", body: body, retry: true}, &a)
	if err != nil {
		return nil, err
	}
	return &a, nil
}

// List is operation actions.list.
func (s *ActionsService) List(ctx context.Context) ([]Action, error) {
	var v []Action
	return v, s.c.Do(ctx, http.MethodGet, "/v1/actions", nil, &v)
}

// Get is operation actions.get.
func (s *ActionsService) Get(ctx context.Context, id string) (*Action, error) {
	var v Action
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/actions/"+url.PathEscape(id), nil, &v)
}

// Approve is operation actions.approve (owner only). Never retried blindly: after an ambiguous
// failure the action is read back (SDK.md §3.7).
func (s *ActionsService) Approve(ctx context.Context, id string) (*Action, error) {
	return s.decide(ctx, id, "approve")
}

// Deny is operation actions.deny (owner only), with the same read-back rule as Approve.
func (s *ActionsService) Deny(ctx context.Context, id string) (*Action, error) {
	return s.decide(ctx, id, "deny")
}

func (s *ActionsService) decide(ctx context.Context, id, verb string) (*Action, error) {
	var a Action
	_, err := s.c.do(ctx, request{method: http.MethodPost, path: "/v1/actions/" + url.PathEscape(id) + "/" + verb}, &a)
	if err == nil {
		return &a, nil
	}
	var e *Error
	if !errors.As(err, &e) || (e.Status != 0 && e.Status < 500) {
		return nil, err // a clear answer from the gateway
	}
	// Sent, then lost: read back. Only a decision recorded for this very principal is success.
	got, rerr := s.Get(ctx, id)
	if rerr != nil {
		return nil, &Error{Code: "ambiguous_result", Message: verb + " may or may not have been applied; check the action", cause: err}
	}
	if got.State != "awaiting_approval" && got.DecidedBy != nil && s.c.principal != "" && got.DecidedBy.Id == s.c.principal {
		return got, nil
	}
	return nil, &Error{Code: "ambiguous_result", Message: fmt.Sprintf("%s may or may not have been applied; the action is now %s", verb, got.State), Action: got, cause: err}
}

// Wait polls the action until it is terminal or ctx ends, calling onChange on each new state.
func (s *ActionsService) Wait(ctx context.Context, id string, every time.Duration, onChange func(*Action)) (*Action, error) {
	if every <= 0 {
		every = 2 * time.Second
	}
	last := ""
	for {
		a, err := s.Get(ctx, id)
		if err != nil {
			return nil, err
		}
		if a.State != last {
			last = a.State
			if onChange != nil {
				onChange(a)
			}
		}
		if Terminal(a.State) {
			return a, nil
		}
		if err := s.c.sleep(ctx, every); err != nil {
			return a, err
		}
	}
}
