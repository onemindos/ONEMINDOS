// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"context"
	"net/http"
)

// KeyboardService is /v1/system/keyboard (P-11): the keyboard layout of the text console and the box's own screen.
type KeyboardService struct{ c *Client }

// Get is operation system.keyboard.get: the layout chosen now and every layout the image offers, with its variants.
// Owner only. Available is false, with a Reason, when the host service cannot be reached.
func (s *KeyboardService) Get(ctx context.Context) (*KeyboardView, error) {
	var v KeyboardView
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/system/keyboard", nil, &v)
}

// KeyboardRequest is what Set asks for. Variant is empty for the plain layout.
type KeyboardRequest struct {
	Layout         string `json:"layout"`
	Variant        string `json:"variant,omitempty"`
	Reason         string `json:"reason,omitempty"`
	IdempotencyKey string `json:"idempotency_key,omitempty"`
}

// Set is operation system.keyboard.set: it files a system.set_keymap action that waits for an owner's approval
// (never approved here). Retrying with the same IdempotencyKey returns the same action.
func (s *KeyboardService) Set(ctx context.Context, r KeyboardRequest) (*Action, error) {
	var a Action
	return &a, s.c.Do(ctx, http.MethodPost, "/v1/system/keyboard", r, &a)
}
