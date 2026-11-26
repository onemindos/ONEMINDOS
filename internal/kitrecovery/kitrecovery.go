// SPDX-License-Identifier: Apache-2.0

// Package kitrecovery is the box's console menu for recovering owner access with
// the printed emergency kit (gateway permissions design 25c, D-028, path 2 of
// "never lose your data").
//
// It runs only on the box: `onemindd recover-owner` on tty2 (a screen and
// keyboard plugged into the box) and `onemind recovery kit` in a root shell on
// the box. It asks the gateway on loopback and proves it is the box's own
// console with the console key, a 0600 file only the gateway's user and root can
// read. The gateway checks the kit key and limits wrong tries; this program only
// asks and shows. Nothing here deletes data, resets the box or shows a key.
package kitrecovery

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Defaults on the image.
const (
	DefaultGateway = "http://127.0.0.1:8080"                      // the gateway's loopback-only HTTP port
	DefaultKeyFile = "/data/onemind/gateway/console-recovery.key" // made by the gateway at start
)

var group = regexp.MustCompile(`\b[A-Z2-7]{4}\b`)

// Console is one recovery session at the box.
type Console struct {
	Gateway string
	KeyFile string
	In      io.Reader
	Out     io.Writer
	HTTP    *http.Client
	// ReadSecret reads a password without echo; nil reads a plain line (tests, a serial line).
	ReadSecret func() (string, error)

	in      *bufio.Reader
	key     string
	session string
}

type owner struct {
	UserID        string `json:"user_id"`
	Username      string `json:"username"`
	DisplayName   string `json:"display_name"`
	Authenticator bool   `json:"authenticator"`
	Passkeys      []struct {
		CredentialID string `json:"credential_id"`
		Label        string `json:"label"`
	} `json:"passkeys"`
}

type apiError struct {
	Status  int
	Message string `json:"message"`
	Reason  string `json:"reason"`
	Retry   int    `json:"retry_after_s"`
}

func (e *apiError) Error() string { return e.Message }

func (c *Console) say(format string, a ...any) { fmt.Fprintf(c.Out, format+"\n", a...) }

func (c *Console) line(prompt string) (string, error) {
	fmt.Fprint(c.Out, prompt)
	s, err := c.in.ReadString('\n')
	if err != nil && (s == "" || !errors.Is(err, io.EOF)) {
		return "", err
	}
	return strings.TrimSpace(s), nil
}

func (c *Console) secret(prompt string) (string, error) {
	if c.ReadSecret == nil {
		return c.line(prompt)
	}
	fmt.Fprint(c.Out, prompt)
	s, err := c.ReadSecret()
	fmt.Fprintln(c.Out)
	return strings.TrimSpace(s), err
}

func (c *Console) call(ctx context.Context, method, path string, body, out any) error {
	var rd io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		rd = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, strings.TrimRight(c.Gateway, "/")+path, rd)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("OneMind-Console", c.key)
	if c.session != "" {
		req.Header.Set("OneMind-Kit-Session", c.session)
	}
	hc := c.HTTP
	if hc == nil {
		hc = &http.Client{Timeout: 30 * time.Second}
	}
	resp, err := hc.Do(req)
	if err != nil {
		return fmt.Errorf("the gateway on this box did not answer (%v); wait a minute and try again", err)
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode >= 300 {
		e := &apiError{Status: resp.StatusCode}
		_ = json.Unmarshal(raw, e)
		if e.Message == "" {
			e.Message = resp.Status
		}
		return e
	}
	if out != nil && len(raw) > 0 {
		return json.Unmarshal(raw, out)
	}
	return nil
}

// Run asks for the kit key, then offers the menu until the owner is done or the
// 15-minute kit session ends.
func (c *Console) Run(ctx context.Context) error {
	c.in = bufio.NewReader(c.In)
	b, err := os.ReadFile(c.KeyFile)
	if err != nil {
		return fmt.Errorf("this runs only on the box itself, as root (could not read %s: %w)", c.KeyFile, err)
	}
	c.key = strings.TrimSpace(string(b))
	c.say("OneMind: recover owner access with your emergency kit.")
	c.say("This changes how you sign in. It deletes nothing and never shows a key.")
	c.say("")
	keyText, err := c.line("Type the 13 groups of the owner recovery key from your kit, then Enter:\n> ")
	if err != nil {
		return err
	}
	groups := group.FindAllString(strings.ToUpper(keyText), -1)
	if len(groups) != 13 {
		return fmt.Errorf("that has %d groups of 4 letters; the kit's key has 13", len(groups))
	}
	check, err := c.line("Check group (printed after the key): ")
	if err != nil {
		return err
	}
	var opened struct {
		Session string  `json:"session"`
		Owners  []owner `json:"owners"`
	}
	if err := c.call(ctx, http.MethodPost, "/v1/auth/recovery/kit", map[string]any{"groups": groups, "check": strings.ToUpper(check)}, &opened); err != nil {
		var e *apiError
		if errors.As(err, &e) && e.Retry > 0 {
			return fmt.Errorf("%s (try again in %s; nothing was deleted)", e.Message, (time.Duration(e.Retry) * time.Second).Round(time.Minute))
		}
		return err
	}
	c.session = opened.Session
	c.say("Kit accepted. You have 15 minutes. Every owner device is told this happened.")
	return c.menu(ctx, opened.Owners)
}

func (c *Console) pickOwner(owners []owner) (owner, error) {
	if len(owners) == 1 {
		return owners[0], nil
	}
	for i, o := range owners {
		c.say("  %d) %s (%s)", i+1, o.DisplayName, o.Username)
	}
	s, err := c.line("Which owner? ")
	if err != nil {
		return owner{}, err
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 || n > len(owners) {
		return owner{}, errors.New("no such owner")
	}
	return owners[n-1], nil
}

func (c *Console) menu(ctx context.Context, owners []owner) error {
	if len(owners) == 0 {
		return errors.New("this box has no owner account yet; finish the setup instead")
	}
	o, err := c.pickOwner(owners)
	if err != nil {
		return err
	}
	for {
		c.say("")
		c.say("Owner: %s (%s), %d passkey(s), authenticator code %s", o.DisplayName, o.Username, len(o.Passkeys), map[bool]string{true: "on", false: "off"}[o.Authenticator])
		c.say("  1) Set a new password")
		c.say("  2) Turn off the authenticator code")
		c.say("  3) Remove a lost passkey")
		c.say("  4) Make a code to add a passkey on your phone or laptop")
		c.say("  5) Done")
		choice, err := c.line("> ")
		if err != nil {
			return err
		}
		err = c.do(ctx, choice, &o)
		var e *apiError
		switch {
		case err == errDone:
			c.say("Done. Sign in with your new password or passkey.")
			return nil
		case errors.As(err, &e) && e.Reason == "kit_session_ended":
			return errors.New("the 15 minutes are over; start again with your kit")
		case err != nil:
			c.say("That did not work: %v", err)
		}
	}
}

var errDone = errors.New("done")

func (c *Console) do(ctx context.Context, choice string, o *owner) error {
	who := map[string]any{"user_id": o.UserID}
	switch choice {
	case "1":
		p1, err := c.secret("New password (at least 10 characters): ")
		if err != nil {
			return err
		}
		p2, err := c.secret("Type it again: ")
		if err != nil {
			return err
		}
		if p1 != p2 {
			return errors.New("the two passwords differ")
		}
		if err := c.call(ctx, http.MethodPost, "/v1/auth/recovery/kit/password", map[string]any{"user_id": o.UserID, "password": p1}, nil); err != nil {
			return err
		}
		c.say("Password set. Every device that was signed in must sign in again.")
	case "2":
		if err := c.call(ctx, http.MethodPost, "/v1/auth/recovery/kit/authenticator/clear", who, nil); err != nil {
			return err
		}
		o.Authenticator = false
		c.say("Authenticator code turned off. Set it up again after you sign in.")
	case "3":
		if len(o.Passkeys) == 0 {
			return errors.New("this owner has no passkeys")
		}
		for i, k := range o.Passkeys {
			c.say("  %d) %s", i+1, k.Label)
		}
		s, err := c.line("Which one is lost? ")
		if err != nil {
			return err
		}
		n, err := strconv.Atoi(s)
		if err != nil || n < 1 || n > len(o.Passkeys) {
			return errors.New("no such passkey")
		}
		k := o.Passkeys[n-1]
		if err := c.call(ctx, http.MethodPost, "/v1/auth/recovery/kit/passkeys/remove", map[string]any{"user_id": o.UserID, "credential_id": k.CredentialID}, nil); err != nil {
			return err
		}
		o.Passkeys = append(o.Passkeys[:n-1], o.Passkeys[n:]...)
		c.say("Removed %q. It no longer signs in or approves anything.", k.Label)
	case "4":
		var code struct {
			Code string `json:"code"`
		}
		if err := c.call(ctx, http.MethodPost, "/v1/auth/recovery/kit/sign-in-code", who, &code); err != nil {
			return err
		}
		c.say("On your phone or laptop, open this box's sign-in page (/signin), choose")
		c.say("\"I have a code from the box\" and type:")
		c.say("")
		c.say("    %s", code.Code)
		c.say("")
		c.say("It works once, for 15 minutes, and lets that device add a passkey.")
	case "5", "q":
		return errDone
	default:
		return errors.New("pick 1 to 5")
	}
	return nil
}
