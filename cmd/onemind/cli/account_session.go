// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	onemind "github.com/onemindos/onemindos/sdk/go"
	"golang.org/x/term"
)

type accountCredential struct {
	Hub          string    `yaml:"hub" json:"-"`
	AccessToken  string    `yaml:"access-token" json:"access_token"`
	RefreshToken string    `yaml:"refresh-token" json:"refresh_token"`
	Expires      time.Time `yaml:"expires-at" json:"expires_at"`
}

type accountSession struct {
	accountCredential
	Principal struct {
		ID string `json:"id"`
	} `json:"principal"`
}

func secureAccountHub(hub string) (*url.URL, error) {
	u, err := url.Parse(strings.TrimRight(strings.TrimSpace(hub), "/"))
	if err != nil || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" ||
		(u.Scheme != "https" && !(u.Scheme == "http" && (u.Hostname() == "localhost" || net.ParseIP(u.Hostname()).IsLoopback()))) {
		return nil, exitWith(ExitUsage, "usage", "account commands need an HTTPS --hub URL or a loopback HTTP URL")
	}
	return u, nil
}

func (a *App) accountClient(t *target) (*onemind.Client, error) {
	if _, err := secureAccountHub(t.hub); err != nil {
		return nil, err
	}
	return a.clientFor(t, onemind.WithNoRedirects())
}

// accountAccess renews a CLI account session only when its access token expires.
func (a *App) accountAccess(cfg *Config, t *target) (string, error) {
	cr, err := cfg.loadCreds()
	if err != nil {
		return "", err
	}
	session, ok := cr.Sessions[t.name]
	if !ok || session.Hub != strings.TrimRight(t.hub, "/") {
		return "", nil
	}
	if session.Expires.After(time.Now()) {
		return session.AccessToken, nil
	}
	cfg, unlock, err := loadConfigForWrite(a.G.ConfigFile)
	if err != nil {
		return "", err
	}
	defer unlock()
	cr, err = cfg.loadCreds()
	if err != nil {
		return "", err
	}
	// A concurrent login or refresh may already have saved another credential.
	session, ok = cr.Sessions[t.name]
	if !ok || session.Hub != strings.TrimRight(t.hub, "/") {
		return "", nil
	}
	if session.Expires.After(time.Now()) {
		return session.AccessToken, nil
	}
	c, err := a.accountClient(&target{hub: session.Hub})
	if err != nil {
		return "", err
	}
	next := accountCredential{Hub: session.Hub}
	if err := c.Do(bg(), http.MethodPost, "/v1/auth/refresh", map[string]string{"refresh_token": session.RefreshToken}, &next); err != nil {
		return "", err
	}
	if next.AccessToken == "" || next.RefreshToken == "" || next.Expires.IsZero() {
		return "", fmt.Errorf("the box returned an incomplete account session")
	}
	cr.Sessions[t.name] = next
	if err := cfg.saveCreds(cr); err != nil {
		return "", err
	}
	return next.AccessToken, nil
}

func (a *App) saveAccountSession(hub, name string, session accountSession) (string, error) {
	u, err := secureAccountHub(hub)
	if err != nil {
		return "", err
	}
	if name == "" {
		name = strings.NewReplacer(":", "-", ".", "-").Replace(u.Hostname())
	}
	if !ctxName.MatchString(name) {
		return "", exitWith(ExitUsage, "usage", "the context name must contain only letters, digits, '.', '_' and '-' and start with a letter or digit")
	}
	if session.AccessToken == "" || session.RefreshToken == "" || session.Expires.IsZero() || session.Principal.ID == "" {
		return "", fmt.Errorf("the box returned an incomplete account session")
	}
	cfg, unlock, err := loadConfigForWrite(a.G.ConfigFile)
	if err != nil {
		return "", err
	}
	defer unlock()
	cr, err := cfg.loadCreds()
	if err != nil {
		return "", err
	}
	session.Hub = u.String()
	cfg.CurrentContext = name
	cfg.Contexts[name] = &Context{Hub: session.Hub, Principal: session.Principal.ID, Credential: "file", InsecureHTTP: u.Scheme == "http"}
	delete(cr.Tokens, name)
	cr.Sessions[name] = session.accountCredential
	if err := cfg.saveCreds(cr); err != nil {
		return "", err
	}
	return name, cfg.save()
}

func (a *App) accountSecret(prompt string, fromStdin bool) (string, error) {
	if fromStdin {
		line, err := a.readLine()
		if err != nil && err != io.EOF {
			return "", err
		}
		line = strings.TrimSuffix(strings.TrimSuffix(line, "\n"), "\r")
		if line == "" {
			return "", exitWith(ExitUsage, "usage", "missing "+prompt+" on stdin")
		}
		return line, nil
	}
	f, ok := a.Stdin.(*os.File)
	if !ok || !a.Interactive() {
		return "", exitWith(ExitUsage, "usage", "use a terminal or pass --secrets-stdin")
	}
	fmt.Fprintf(a.Stderr, "%s: ", prompt)
	value, err := term.ReadPassword(int(f.Fd()))
	fmt.Fprintln(a.Stderr)
	if err == nil && len(value) == 0 {
		return "", exitWith(ExitUsage, "usage", prompt+" cannot be empty")
	}
	return string(value), err
}

func (a *App) loginAccount(name, username string, stdin, totp bool) error {
	c, err := a.accountClient(&target{hub: a.G.Hub})
	if err != nil {
		return err
	}
	password, err := a.accountSecret("Password", stdin)
	if err != nil {
		return err
	}
	body := map[string]string{"username": username, "password": password, "client": "cli"}
	var session accountSession
	login := func() error { return c.Do(bg(), http.MethodPost, "/v1/auth/login", body, &session) }
	if !totp {
		err = login()
		var authErr *onemind.Error
		if errors.As(err, &authErr) && authErr.Reason == "totp_required" {
			totp = true
		}
	}
	if totp {
		code, e := a.accountSecret("Authenticator code", stdin)
		if e != nil {
			return e
		}
		body["totp"] = strings.TrimSpace(code)
		err = login()
	}
	if err != nil {
		return err
	}
	name, err = a.saveAccountSession(c.BaseURL(), name, session)
	if err != nil {
		return err
	}
	return a.accountResult("Signed in. Saved context "+name+".", map[string]string{"context": name, "hub": c.BaseURL()})
}
