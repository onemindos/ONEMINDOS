// SPDX-License-Identifier: Apache-2.0

package cli

// Shared plumbing for the commands that call existing gateway routes (`users`, `backup`, `care`,
// `update policy`, `update apply`). Writes that need approval only FILE a request: no command here
// ever approves one, so nothing here can actuate on its own (AI never actuates without human
// approval). The gateway decides who may do what and answers 403 to anyone else: it refuses agent
// tokens for backup restore and os.update.install, which only a person may request.

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

// gwDo calls one gateway route and returns its JSON as is. A sign-in step the gateway wants a
// passkey for is explained, because a token on a command line cannot do that step.
func (a *App) gwDo(method, path string, body any) (any, error) {
	if a.gw == nil {
		c, _, err := a.client()
		if err != nil {
			return nil, err
		}
		a.gw = c
	}
	c := a.gw
	var raw any
	if err := c.Do(bg(), method, path, body, &raw); err != nil {
		return nil, explainGateway(err)
	}
	return raw, nil
}

// gwDoKeyed is gwDo for a write with an Idempotency-Key header (see idemKey).
func (a *App) gwDoKeyed(method, path, key string, body any) (any, error) {
	if a.gw == nil {
		c, _, err := a.client()
		if err != nil {
			return nil, err
		}
		a.gw = c
	}
	var raw any
	if err := a.gw.DoIdempotent(bg(), method, path, key, body, &raw); err != nil {
		return nil, explainGateway(err)
	}
	return raw, nil
}

// explainGateway adds plain words to the two gateway answers a person cannot decode alone: the
// passkey step-up, and a 409 saying the idempotency key was already used for a different request.
func explainGateway(err error) error {
	var e *onemind.Error
	if !errors.As(err, &e) {
		return err
	}
	if e.Reason == "step_up_required" {
		// D-028: owner changes need a passkey confirmation bound to the exact change (a proven key once the
		// household holds one; before that, N-1 b, a passkey plus the code on the box's own screen). Only a
		// browser can make it, so signing in again here won't help.
		return fmt.Errorf("%w\nThis step needs a passkey confirmation, which the CLI cannot make. Do it in the dashboard (it asks for your passkey in place, and for the code on the box's own screen until you add a proven key), or approve the request there", err)
	}
	if e.Status == http.StatusConflict && strings.Contains(e.Message, "idempotency_key") {
		return fmt.Errorf("%w\nThis exact request was already filed today by someone else, or with different details, so the box will not file it twice. See what is waiting with `onemind actions list`", err)
	}
	return err
}

// freshKey is a random Idempotency-Key for one invocation. It stays fixed across the SDK's own
// retries of that one call, so a network retry is safe, but a second run is a real new request.
func freshKey() string { return "cli-" + onemind.NewIdempotencyKey() }

// idemKey builds an Idempotency-Key from stable inputs only (what is asked for, on what, and the UTC
// day), never from a clock reading or a random number, so running the same command again files
// nothing new: the gateway replays the request that is already waiting.
func idemKey(prefix string, parts ...string) string {
	sum := sha256.Sum256([]byte(strings.Join(parts, "\x00") + "\x00" + time.Now().UTC().Format("2006-01-02")))
	return prefix + hex.EncodeToString(sum[:12])
}

// obj reads a JSON object field-by-field without panicking on a surprise shape.
func obj(v any) map[string]any {
	m, _ := v.(map[string]any)
	if m == nil {
		return map[string]any{}
	}
	return m
}

func str(v any) string {
	switch x := v.(type) {
	case string:
		return x
	case nil:
		return ""
	case float64, bool:
		return fmt.Sprint(x)
	}
	return ""
}

func list(v any) []any {
	l, _ := v.([]any)
	return l
}

// printRequested says that an action now waits for an owner, or prints the action's JSON. A repeat
// request with a key the gateway already knows comes back as the stored action in whatever state it
// reached; if that is not a waiting one nothing new was filed, so say so and exit ExitConflict.
func (a *App) printRequested(what string, v any) error {
	id := str(obj(v)["id"])
	state := str(obj(v)["state"])
	done := state != "" && state != "awaiting_approval" && state != "requested"
	if a.G.JSON {
		if err := printJSON(a.Stdout, v); err != nil {
			return err
		}
	} else if a.G.Quiet {
		fmt.Fprintln(a.Stdout, id)
	}
	if done {
		return exitWith(ExitConflict, "conflict", fmt.Sprintf("%s: already %s, nothing filed (%s). Ask again tomorrow, or see `onemind actions list`", what, state, id))
	}
	if a.G.JSON || a.G.Quiet {
		return nil
	}
	if a.G.Quiet {
		fmt.Fprintln(a.Stdout, id)
		return nil
	}
	fmt.Fprintf(a.Stdout, "Requested %s (%s). Waiting for an owner: onemind actions approve %s\n", what, id, id)
	return nil
}

// withJSONOrText runs a read: --json prints the gateway's JSON unchanged, else text prints a summary.
func (a *App) withJSONOrText(v any, text func(io.Writer, any) error) error {
	if a.G.JSON {
		return printJSON(a.Stdout, v)
	}
	return text(a.Stdout, v)
}

func (a *App) read(path string, text func(io.Writer, any) error) error {
	v, err := a.gwDo(http.MethodGet, path, nil)
	if err != nil {
		return err
	}
	return a.withJSONOrText(v, text)
}
