// SPDX-License-Identifier: Apache-2.0

package mesh

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"strings"
	"time"
)

// Runner runs the tailscale CLI with args and returns its stdout. It is the
// only way this package touches the system; tests replace it with a fake.
type Runner interface {
	Run(ctx context.Context, args ...string) ([]byte, error)
}

// ErrNotInstalled means the tailscale CLI is not on this machine: the mesh is
// not part of this install (state "none").
var ErrNotInstalled = errors.New("tailscale is not installed")

// ExecRunner runs the real binary. Bin defaults to "tailscale" on PATH.
type ExecRunner struct {
	Bin string
}

// Run executes the CLI. stderr is folded into the error (the CLI never prints
// the auth key: it is passed as file:<path>).
func (r ExecRunner) Run(ctx context.Context, args ...string) ([]byte, error) {
	bin := r.Bin
	if bin == "" {
		bin = "tailscale"
	}
	path, err := exec.LookPath(bin)
	if err != nil {
		return nil, ErrNotInstalled
	}
	cmd := exec.CommandContext(ctx, path, args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if len(msg) > 500 {
			msg = msg[:500] + "…"
		}
		if msg == "" {
			return stdout.Bytes(), fmt.Errorf("tailscale %s: %w", args[0], err)
		}
		return stdout.Bytes(), fmt.Errorf("tailscale %s: %w: %s", args[0], err, msg)
	}
	return stdout.Bytes(), nil
}

// tsStatus is the subset of `tailscale status --json` (ipnstate.Status at
// v1.104.6) this package reads. Unknown fields are ignored, so newer clients
// stay compatible as long as these keep their meaning.
type tsStatus struct {
	BackendState string             `json:"BackendState"`
	Self         *tsPeer            `json:"Self"`
	Peer         map[string]*tsPeer `json:"Peer"`
	Health       []string           `json:"Health"`
}

// tsPeer is ipnstate.PeerStatus. CurAddr is the ip:port of a direct UDP path
// and is empty when traffic goes through DERP; Relay is the home DERP region
// code; PeerRelay is set when a peer relay carries the traffic.
type tsPeer struct {
	HostName      string    `json:"HostName"`
	DNSName       string    `json:"DNSName"`
	OS            string    `json:"OS"`
	TailscaleIPs  []string  `json:"TailscaleIPs"`
	Tags          []string  `json:"Tags"`
	CurAddr       string    `json:"CurAddr"`
	Relay         string    `json:"Relay"`
	PeerRelay     string    `json:"PeerRelay"`
	Online        bool      `json:"Online"`
	Active        bool      `json:"Active"`
	LastHandshake time.Time `json:"LastHandshake"`
}

// Client wraps the tailscale CLI.
type Client struct {
	Runner Runner
	// Now is the clock (tests set it).
	Now func() time.Time
}

// NewClient returns a Client for the system tailscale CLI.
func NewClient() *Client { return &Client{Runner: ExecRunner{}, Now: time.Now} }

func (c *Client) now() time.Time {
	if c.Now == nil {
		return time.Now()
	}
	return c.Now()
}

func (c *Client) rawStatus(ctx context.Context) (*tsStatus, error) {
	out, err := c.Runner.Run(ctx, "status", "--json")
	// `tailscale status` exits non-zero when the backend is not Running but
	// still prints JSON; use the JSON when there is any.
	if len(bytes.TrimSpace(out)) == 0 {
		if err == nil {
			err = errors.New("tailscale status printed nothing")
		}
		return nil, err
	}
	var st tsStatus
	if jerr := json.Unmarshal(out, &st); jerr != nil {
		if err != nil {
			return nil, err
		}
		return nil, fmt.Errorf("tailscale status: invalid JSON: %w", jerr)
	}
	return &st, nil
}

// Status reads the mesh state. It never fails: a missing tailscale binary is
// State "none", and an unreachable or broken tailscaled is State "down" with
// the reason in Error.
func (c *Client) Status(ctx context.Context) *State {
	st, err := c.rawStatus(ctx)
	if errors.Is(err, ErrNotInstalled) {
		return &State{State: StateNone, Path: PathNone, Peers: []Peer{}}
	}
	if err != nil {
		return &State{State: StateDown, Path: PathNone, Peers: []Peer{}, Error: err.Error()}
	}
	return fromStatus(st, c.now())
}
