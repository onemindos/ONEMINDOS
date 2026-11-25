// SPDX-License-Identifier: Apache-2.0

package cli

// Shared plumbing for the commands that call existing gateway routes (`users`, `backup`, `care`,
// `update policy`, `update apply`). Writes that need approval only FILE a request: no command here
// ever approves one, so nothing here can actuate on its own (AI never actuates without human
// approval). The gateway decides who may do what and answers 403 to anyone else: it refuses agent
// tokens for backup restore and os.update.install, which only a person may request.

import (
	"errors"
	"fmt"
	"io"
	"net/http"

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
		var e *onemind.Error
		if errors.As(err, &e) && e.Reason == "step_up_required" {
			return nil, fmt.Errorf("%w\nThis step needs a passkey sign-in, which the CLI cannot do. Do it in the dashboard, or approve the request there", err)
		}
		return nil, err
	}
	return raw, nil
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

// printRequested says that an action now waits for an owner, or prints the action's JSON.
func (a *App) printRequested(what string, v any) error {
	if a.G.JSON {
		return printJSON(a.Stdout, v)
	}
	id := str(obj(v)["id"])
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
